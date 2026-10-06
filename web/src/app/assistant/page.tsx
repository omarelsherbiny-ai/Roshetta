// web/src/app/assistant/page.tsx (route: /assistant — chat assistant with action proposals)
'use client';

import React, { useState, useEffect, useRef, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { ToastStack, useToasts } from '@/components/ui/Toast';
import { sendChatMessage, confirmActionProposal, cancelActionProposal, ActionConfirmError } from '@/lib/api';
import { ChatMessage, ActionProposal, ProposedItem, ProductDraft } from '@/types';
import { useLanguage } from '@/lib/i18n';
import { localeOf, pickLocalizedName } from '@/lib/languages';
import { usePharmacyName } from '@/hooks/usePharmacyName';
import { getSpeechRecognition } from '@/lib/speech';
import { ChatText } from '@/components/assistant/ChatText';

/** The few members of the browser's speech recognizer this page uses (kept local on purpose). */
interface VoiceRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onresult: ((event: { results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

const joinWords = (...parts: string[]): string => parts.map((part) => part.trim()).filter(Boolean).join(' ');

interface ProductEditForm {
  name: string;
  buy: string;
  sell: string;
  qty: string;
  min: string;
  category: string;
}

function toEditForm(lang: string, draft: ProductDraft): ProductEditForm {
  return {
    name: pickLocalizedName(lang, draft.name_ar, draft.name_en),
    buy: String(draft.unit_buy_price),
    sell: String(draft.unit_sell_price),
    qty: String(draft.stock_qty),
    min: String(draft.min_threshold),
    category: draft.category ?? '',
  };
}

/** The draft the server receives, or null when a field is empty or not a valid number. */
function formToDraft(form: ProductEditForm): ProductDraft | null {
  const name = form.name.trim();
  const buy = Number(form.buy);
  const sell = Number(form.sell);
  const qty = Number(form.qty);
  const min = Number(form.min);
  if (!name || form.buy.trim() === '' || form.sell.trim() === '' || form.qty.trim() === '' || form.min.trim() === '') return null;
  if (![buy, sell, qty, min].every(Number.isFinite)) return null;
  if (buy < 0 || sell <= 0 || qty < 0 || min < 0 || !Number.isInteger(qty) || !Number.isInteger(min)) return null;
  return {
    name_ar: name,
    name_en: name,
    unit_buy_price: buy,
    unit_sell_price: sell,
    stock_qty: qty,
    min_threshold: min,
    category: form.category.trim() || null,
  };
}

/** What the card shows: the edited values when they are valid, otherwise the card's own product. */
function shownProductOf(proposal: ActionProposal, edits: Record<string, ProductEditForm>): ProductDraft {
  const form = edits[proposal.id];
  return (form && formToDraft(form)) || (proposal.product as ProductDraft);
}

/** Card types that carry no sale lines: a short change summary is shown, never the item list or the total. */
const ITEMLESS_TYPES: readonly string[] = ['update_product', 'create_category', 'create_invite'];
const isItemless = (proposal: ActionProposal): boolean => ITEMLESS_TYPES.includes(proposal.action_type);

/** Sale, expense and restock cards: the lines can be edited in place (quantity and unit price). */
interface ItemEditRow { quantity: string; price: string }

const round2 = (value: number): number => Math.round((value + Number.EPSILON) * 100) / 100;

function toItemEdits(items: ProposedItem[]): ItemEditRow[] {
  return items.map((item) => ({ quantity: String(item.quantity), price: String(item.unit_price) }));
}

/** The lines the server receives, or null when a quantity or a price is empty or not a valid number. */
function editsToItems(items: ProposedItem[], rows: ItemEditRow[] | undefined): ProposedItem[] | null {
  if (!rows || rows.length !== items.length) return null;
  const result: ProposedItem[] = [];
  for (let index = 0; index < items.length; index += 1) {
    const { quantity: rawQuantity, price: rawPrice } = rows[index];
    if (rawQuantity.trim() === '' || rawPrice.trim() === '') return null;
    const quantity = Number(rawQuantity);
    const price = round2(Number(rawPrice));
    if (!Number.isFinite(quantity) || !Number.isFinite(price)) return null;
    if (quantity <= 0 || quantity > 1_000_000 || price < 0 || price > 100_000_000) return null;
    result.push({ ...items[index], quantity, unit_price: price, subtotal: round2(quantity * price) });
  }
  return result;
}

/** What the card shows: the edited lines when they are valid, otherwise the card's own lines. */
function shownItemsOf(proposal: ActionProposal, edits: Record<string, ItemEditRow[]>): ProposedItem[] {
  return editsToItems(proposal.items, edits[proposal.id]) ?? proposal.items;
}

const CHANGE_LABELS: Record<string, string> = {
  name_ar: 'pc_name',
  name_en: 'pc_name',
  unit_buy_price: 'pc_buy',
  unit_sell_price: 'pc_sell',
  min_threshold: 'pc_min',
  category: 'pc_category',
};

const showValue = (value: unknown): string => (value === null || value === undefined || value === '' ? '—' : String(value));

interface ChangeRow { field: string; label: string; from: string; to: string }

/** The rows of a change card: old value to new value per changed field, from the server's own card data. */
function changeRowsOf(proposal: ActionProposal): ChangeRow[] {
  if (proposal.action_type === 'update_product') {
    const now = (proposal.product ?? {}) as unknown as Record<string, unknown>;
    const before = proposal.before ?? {};
    return (proposal.changed_fields ?? [])
      .filter((field) => field in CHANGE_LABELS)
      .map((field) => ({ field, label: CHANGE_LABELS[field], from: showValue(before[field]), to: showValue(now[field]) }));
  }
  if (proposal.action_type === 'create_category' && proposal.category_name) {
    return [{ field: 'category_name', label: 'pc_category', from: '', to: proposal.category_name }];
  }
  return [];
}

/** The invitation link the confirm answer carries, or null when it has none (a relative path only). */
function inviteLinkOf(answer: unknown): { path: string; expires: string | null } | null {
  if (!answer || typeof answer !== 'object') return null;
  // The confirm answer is { success, message, proposal }, and the link sits inside `proposal`.
  const body = answer as { proposal?: unknown; join_path?: unknown; invite_expires_at?: unknown };
  const inner = body.proposal && typeof body.proposal === 'object' ? body.proposal : body;
  const card = inner as { join_path?: unknown; invite_expires_at?: unknown };
  if (typeof card.join_path !== 'string' || !card.join_path.startsWith('/')) return null;
  return { path: card.join_path, expires: typeof card.invite_expires_at === 'string' ? card.invite_expires_at : null };
}

/** The server sends UTC times without a zone letter; add it before parsing. */
function parseServerTime(value: string): Date {
  return new Date(/[zZ]$|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

function AssistantContent() {
  const { lang, dir, t } = useLanguage();
  const pharmacyName = usePharmacyName();
  const formatTime = (value?: string | number | Date) =>
    new Date(value ?? Date.now()).toLocaleTimeString(localeOf(lang), { hour: '2-digit', minute: '2-digit' });
  const searchParams = useSearchParams();
  const initialPrompt = searchParams.get('prompt');

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'msg-welcome-ai',
      sender: 'assistant',
      text: t('as_welcome'),
      timestamp: formatTime(),
    },
  ]);

  const [inputVal, setInputVal] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [confirmedIds, setConfirmedIds] = useState<Record<string, boolean>>({});
  const [cancelledIds, setCancelledIds] = useState<Record<string, boolean>>({});
  const [busyActionId, setBusyActionId] = useState<string | null>(null);
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});
  // Product cards: the values being edited (text, so a field can be empty while typing)
  // and the cards where the server said a product with that name already exists.
  const [productEdits, setProductEdits] = useState<Record<string, ProductEditForm>>({});
  const [editingIds, setEditingIds] = useState<Record<string, boolean>>({});
  // Sale, expense and restock cards: the quantity and price being edited per line (text while typing).
  const [itemEdits, setItemEdits] = useState<Record<string, ItemEditRow[]>>({});
  const [duplicateIds, setDuplicateIds] = useState<Record<string, boolean>>({});
  // Invitation cards: the link the server returns once, when the person confirms (kept in memory
  // only, never in storage), and which link was just copied.
  const [inviteLinks, setInviteLinks] = useState<Record<string, { path: string; expires: string | null }>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  // One random id per open chat, kept only in memory (no storage). The server mixes it with the
  // user, pharmacy and role to name the assistant's memory, so a reload starts a new chat.
  const chatIdRef = useRef<string | null>(null);
  const getChatId = (): string => {
    if (!chatIdRef.current) {
      chatIdRef.current = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `chat-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    }
    return chatIdRef.current;
  };
  const { toasts, push, dismiss } = useToasts();

  useEffect(() => {
    setMessages((current) => current.map((message) => message.id === 'msg-welcome-ai'
      ? { ...message, text: t('as_welcome') }
      : message));
  }, [lang]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Handle URL prompt if redirected from Dashboard
  useEffect(() => {
    if (initialPrompt && initialPrompt.trim()) {
      handleSend(initialPrompt.trim());
    }
  }, [initialPrompt]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend ?? inputVal).trim();
    if (!text || isLoading) return;

    if (listeningRef.current) {
      discardRef.current = true;
      stopVoiceRecording();
    }
    setInputVal('');

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text,
      timestamp: formatTime(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await sendChatMessage(text, getChatId(), lang);
      // The server sends a UTC ISO time; show it like every other message time.
      setMessages((prev) => [...prev, { ...response, timestamp: formatTime(response.timestamp) }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'assistant',
          text: `${t('as_err_prefix')} ${(err instanceof Error && err.message) || t('as_err_connect')}`,
          timestamp: formatTime(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = async (proposal: ActionProposal, allowDuplicate = false) => {
    if (busyActionId) return;
    const proposalId = proposal.id;
    let product: ProductDraft | undefined;
    if (proposal.action_type === 'create_product') {
      // Send the edited values when the card was edited, otherwise the card's own product.
      const form = productEdits[proposalId];
      const draft = form ? formToDraft(form) : proposal.product ?? null;
      if (!draft) {
        setActionErrors((current) => ({ ...current, [proposalId]: t('pc_bad_values') }));
        return;
      }
      product = draft;
    }
    let lines: ProposedItem[] | undefined;
    if (!product && !isItemless(proposal)) {
      // Send the edited lines when the card was edited (and are valid), otherwise the card's own lines.
      const rows = itemEdits[proposalId];
      lines = rows ? editsToItems(proposal.items, rows) ?? undefined : proposal.items;
      if (!lines) {
        setActionErrors((current) => ({ ...current, [proposalId]: t('pc_bad_values') }));
        return;
      }
    }
    setBusyActionId(proposalId);
    setActionErrors((current) => { const next = { ...current }; delete next[proposalId]; return next; });
    try {
      const answer: unknown = await confirmActionProposal(proposalId, lines, undefined, product, allowDuplicate || undefined);
      if (proposal.action_type === 'create_invite') {
        const link = inviteLinkOf(answer);
        if (link) setInviteLinks((current) => ({ ...current, [proposalId]: link }));
      }
      setConfirmedIds((prev) => ({ ...prev, [proposalId]: true }));
      setEditingIds((current) => ({ ...current, [proposalId]: false }));
    } catch (e) {
      if (e instanceof ActionConfirmError && e.status === 409 && product) {
        setDuplicateIds((current) => ({ ...current, [proposalId]: true }));
      }
      setActionErrors((current) => ({ ...current, [proposalId]: `${t('as_confirm_failed')}: ${e instanceof Error ? e.message : ''}` }));
    } finally {
      setBusyActionId(null);
    }
  };

  const handleCancel = async (proposalId: string) => {
    if (busyActionId) return;
    setBusyActionId(proposalId);
    setActionErrors((current) => { const next = { ...current }; delete next[proposalId]; return next; });
    try {
      await cancelActionProposal(proposalId);
      setCancelledIds((prev) => ({ ...prev, [proposalId]: true }));
    } catch (e) {
      setActionErrors((current) => ({ ...current, [proposalId]: `${t('as_cancel_failed')}: ${e instanceof Error ? e.message : ''}` }));
    } finally {
      setBusyActionId(null);
    }
  };

  const handleCopyInvite = async (proposalId: string, url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedId(proposalId);
    } catch {
      // No clipboard permission: the link stays selectable in the box for a manual copy.
      setCopiedId(null);
    }
  };

  const handleRevise = async (proposal: ActionProposal) => {
    if (busyActionId) return;
    if (proposal.action_type === 'create_product' && proposal.product) {
      // A product card is edited in place: nothing is cancelled and the card stays.
      const product = proposal.product;
      setProductEdits((current) => current[proposal.id] ? current : { ...current, [proposal.id]: toEditForm(lang, product) });
      setEditingIds((current) => ({ ...current, [proposal.id]: !current[proposal.id] }));
      return;
    }
    if (isItemless(proposal)) return;
    // A sale, expense or restock card is edited in place too: nothing is cancelled and the card stays.
    setItemEdits((current) => current[proposal.id] ? current : { ...current, [proposal.id]: toItemEdits(proposal.items) });
    setEditingIds((current) => ({ ...current, [proposal.id]: !current[proposal.id] }));
  };

  // ── Voice dictation: keeps listening until the person stops it ──
  // One recognizer runs in continuous mode with interim results, so words show in the box as they
  // are heard. The browser ends a session by itself after a pause; while the person has not pressed
  // stop, a new session starts at once. Nothing is sent automatically: stop (mic again) keeps the
  // text in the box, Escape drops the dictated text, send stops listening and sends.
  const recognitionRef = useRef<VoiceRecognitionLike | null>(null);
  const listeningRef = useRef(false);
  const discardRef = useRef(false);
  const baseTextRef = useRef('');
  const committedRef = useRef('');
  const sessionFinalRef = useRef('');
  const startedAtRef = useRef(0);
  const quickEndsRef = useRef(0);
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearRestartTimer = () => {
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
  };

  const stopVoiceRecording = () => {
    listeningRef.current = false;
    clearRestartTimer();
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      try { recognition.stop(); } catch { /* already stopped */ }
    }
    setIsRecording(false);
  };

  const cancelVoiceRecording = () => {
    discardRef.current = true;
    stopVoiceRecording();
    setInputVal(baseTextRef.current);
  };

  const startRecognizer = () => {
    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      listeningRef.current = false;
      setIsRecording(false);
      push('warning', t('as_voice_unsupported'));
      return;
    }
    const recognition = new SpeechRecognition() as unknown as VoiceRecognitionLike;
    recognition.lang = lang === 'ar' ? 'ar-EG' : localeOf(lang);
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => {
      startedAtRef.current = Date.now();
      setIsRecording(true);
    };
    recognition.onresult = (event) => {
      if (discardRef.current) return;
      quickEndsRef.current = 0;
      let finalText = '';
      let interimText = '';
      for (let i = 0; i < event.results.length; i += 1) {
        const piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText = joinWords(finalText, piece);
        else interimText = joinWords(interimText, piece);
      }
      sessionFinalRef.current = finalText;
      setInputVal(joinWords(baseTextRef.current, committedRef.current, finalText, interimText));
    };
    recognition.onerror = (event) => {
      const code = event.error ?? '';
      // A pause with no speech or a restart ends the session; onend starts the next one.
      if (code === 'no-speech' || code === 'aborted') return;
      // Denied microphone, no microphone, or the browser's speech service is unreachable.
      listeningRef.current = false;
      push('warning', t('as_voice_unsupported'));
    };
    recognition.onend = () => {
      // A session the person already stopped (or that was replaced) changes nothing.
      if (recognitionRef.current !== recognition) return;
      recognitionRef.current = null;
      committedRef.current = joinWords(committedRef.current, sessionFinalRef.current);
      sessionFinalRef.current = '';
      if (!listeningRef.current) {
        setIsRecording(false);
        return;
      }
      // Sessions that end almost at once without any words: give up after 5 in a row.
      quickEndsRef.current = Date.now() - startedAtRef.current < 1000 ? quickEndsRef.current + 1 : 0;
      if (quickEndsRef.current >= 5) {
        listeningRef.current = false;
        setIsRecording(false);
        push('warning', t('as_voice_unsupported'));
        return;
      }
      clearRestartTimer();
      restartTimerRef.current = setTimeout(() => {
        restartTimerRef.current = null;
        if (listeningRef.current) startRecognizer();
      }, 200);
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      listeningRef.current = false;
      setIsRecording(false);
    }
  };

  const toggleVoiceRecording = () => {
    if (listeningRef.current) {
      stopVoiceRecording();
      return;
    }
    if (!getSpeechRecognition()) {
      push('warning', t('as_voice_unsupported'));
      return;
    }
    listeningRef.current = true;
    discardRef.current = false;
    baseTextRef.current = inputVal.trim();
    committedRef.current = '';
    sessionFinalRef.current = '';
    quickEndsRef.current = 0;
    startRecognizer();
  };

  // Leaving the page switches the microphone off.
  useEffect(() => () => {
    listeningRef.current = false;
    if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      recognition.onresult = null;
      recognition.onend = null;
      recognition.onerror = null;
      try { recognition.abort(); } catch { /* already stopped */ }
    }
  }, []);

  return (
    <div className="flex flex-col min-h-screen bg-surface text-on-surface">
      <TopHeader
        pharmacyName={pharmacyName}
        subtitle={t('assistant')}
        showBack={true}
      />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-28 bg-surface">
        <div className="flex flex-col w-full px-margin-mobile pb-6 pt-2" dir={dir}>

          {/* ── Status & Context Pill ── */}
          <div className="flex items-center justify-center mb-space-md mt-2">
            <div className="inline-flex items-center gap-2 bg-surface-container-high px-3.5 py-1.5 rounded-full shadow-sm">
              <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">
                {t('as_pill')}
              </span>
            </div>
          </div>

          {/* ── Chat Stream Container ── */}
          <div className="flex flex-col gap-space-lg w-full">

            {/* Timestamp Divider */}
            <div className="flex items-center justify-center my-1">
              <span className="font-label-sm text-label-sm text-outline bg-surface-container-low px-3 py-1 rounded-full">
                {t('as_today')} {formatTime()}
              </span>
            </div>

            {/* Messages Iteration */}
            {messages.map((msg) => {
              const isAssistant = msg.sender === 'assistant';

              return (
                <div key={msg.id} className="flex flex-col gap-3">
                  {/* Bubble */}
                  <div
                    className={`flex items-start gap-space-sm w-full ${
                      isAssistant
                        ? 'max-w-[92%] self-start'
                        : 'max-w-[88%] self-end flex-row-reverse'
                    }`}
                  >
                    <div
                      className={`w-9 h-9 rounded-full flex items-center justify-center shadow-sm flex-shrink-0 mt-0.5 ${
                        isAssistant
                          ? 'bg-primary-container text-on-primary-container'
                          : 'bg-surface-container-high text-on-surface'
                      }`}
                    >
                      <span className="material-symbols-outlined text-[20px] icon-filled">
                        {isAssistant ? 'medical_services' : 'person'}
                      </span>
                    </div>

                    <div className={`flex min-w-0 flex-col gap-1 w-full ${!isAssistant ? 'items-end' : ''}`}>
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-label-md text-label-md font-bold ${
                            isAssistant ? 'text-primary' : 'text-on-surface'
                          }`}
                        >
                          {isAssistant ? 'Roshetta' : t('as_user_label')}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant">
                          {msg.timestamp}
                        </span>
                      </div>

                      <div
                        className={`min-w-0 max-w-full p-space-md rounded-xl shadow-sm text-on-surface ${
                          isAssistant
                            ? 'bg-surface-container-lowest rounded-tr-none shadow-[0px_2px_8px_-1px_rgba(26,36,32,0.05)]'
                            : 'bg-surface-container rounded-tl-none'
                        }`}
                      >
                        {isAssistant ? (
                          <ChatText text={msg.text} />
                        ) : (
                          <p className="font-body-md text-body-md leading-relaxed whitespace-pre-wrap text-start">
                            {msg.text}
                          </p>
                        )}

                        {!isAssistant && (
                          <div className="flex items-center justify-end gap-1 mt-1 text-primary">
                            <span className="material-symbols-outlined text-[15px]">done_all</span>
                            <span className="font-label-sm text-label-sm">{t('as_sent')}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* ── STANDOUT CONFIRMATION CARD (Stitch Design) ── */}
                  {msg.proposal && !cancelledIds[msg.proposal.id] && (
                    <div
                      className="w-full bg-surface-container-lowest rounded-xl shadow-[0px_8px_20px_-4px_rgba(26,36,32,0.1)] p-4 flex flex-col gap-3.5 relative overflow-hidden transition-all duration-300 mt-1"
                    >
                      {/* Ambient Visual Bar */}
                      <div className="absolute top-0 right-0 left-0 h-1.5 bg-secondary" />

                      {/* Card Header */}
                      <div className="flex items-center justify-between mt-1">
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-8 rounded-full bg-secondary-fixed flex items-center justify-center text-on-secondary-fixed">
                            <span className="material-symbols-outlined text-[19px]">{msg.proposal.action_type === 'create_product' ? 'add_box' : msg.proposal.action_type === 'update_product' ? 'edit_note' : msg.proposal.action_type === 'create_category' ? 'category' : msg.proposal.action_type === 'create_invite' ? 'person_add' : 'point_of_sale'}</span>
                          </div>
                          <div>
                            <h3 className="font-headline-sm text-headline-sm text-on-surface leading-tight">
                              {msg.proposal.title || t('as_review_op')}
                            </h3>
                            <span className="font-label-sm text-label-sm text-on-surface-variant">
                              {t('as_request')} #{msg.proposal.id.slice(0, 8).toUpperCase()}
                            </span>
                          </div>
                        </div>

                        {confirmedIds[msg.proposal.id] ? (
                          <div className="flex items-center gap-1 bg-primary-container/50 text-primary px-2.5 py-1 rounded-full">
                            <span className="material-symbols-outlined text-[14px]">check_circle</span>
                            <span className="font-label-sm text-label-sm font-bold">{t('as_saved')}</span>
                          </div>
                        ) : actionErrors[msg.proposal.id] ? (
                          <div className="flex items-center gap-1 bg-error-container text-on-error-container px-2.5 py-1 rounded-full">
                            <span className="material-symbols-outlined text-[14px]">error</span>
                            <span className="font-label-sm text-label-sm font-bold">{t('as_confirm_failed')}</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 bg-secondary-container/30 text-secondary px-2.5 py-1 rounded-full">
                            <span className={`material-symbols-outlined text-[14px] ${busyActionId === msg.proposal.id ? 'animate-spin' : ''}`}>hourglass_top</span>
                            <span className="font-label-sm text-label-sm font-bold">
                              {busyActionId === msg.proposal.id ? t('as_executing') : t('as_awaiting')}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Safety Clearance / Warning Pill */}
                      {msg.proposal.warnings && msg.proposal.warnings.length > 0 ? (
                        <div className="flex items-center gap-2 bg-error-container text-on-error-container px-3 py-1.5 rounded-lg">
                          <span className="material-symbols-outlined text-error text-[18px] icon-filled">warning</span>
                          <span className="font-label-sm text-label-sm font-medium">
                            {msg.proposal.warnings.join(' • ')}
                          </span>
                        </div>
                      ) : msg.proposal.action_type === 'log_sale' ? (
                        <div className="flex items-center gap-2 bg-surface-container-low px-3 py-1.5 rounded-lg">
                          <span className="material-symbols-outlined text-tertiary text-[18px] icon-filled">info</span>
                          <span className="font-label-sm text-label-sm text-on-surface font-medium">
                            {t('as_no_interaction_check')}
                          </span>
                        </div>
                      ) : null}

                      {/* Items Breakdown List */}
                      {msg.proposal.action_type === 'create_product' && msg.proposal.product && (
                        editingIds[msg.proposal.id] && productEdits[msg.proposal.id] ? (
                          <div className="grid grid-cols-2 gap-2 bg-surface-container-low/70 p-3 rounded-xl">
                            {([
                              ['name', 'pc_name', 'text', true],
                              ['buy', 'pc_buy', 'decimal', false],
                              ['sell', 'pc_sell', 'decimal', false],
                              ['qty', 'pc_qty', 'numeric', false],
                              ['min', 'pc_min', 'numeric', false],
                              ['category', 'pc_category', 'text', false],
                            ] as const).map(([field, label, mode, wide]) => (
                              <label key={field} className={`flex flex-col gap-1 ${wide ? 'col-span-2' : ''}`}>
                                <span className="font-label-sm text-label-sm text-on-surface-variant">{t(label)}</span>
                                <input
                                  type="text"
                                  inputMode={mode}
                                  value={productEdits[msg.proposal!.id][field]}
                                  disabled={busyActionId !== null}
                                  onChange={(e) => {
                                    const id = msg.proposal!.id;
                                    const value = e.target.value;
                                    setProductEdits((current) => ({ ...current, [id]: { ...current[id], [field]: value } }));
                                    if (field === 'name') setDuplicateIds((current) => ({ ...current, [id]: false }));
                                  }}
                                  className="h-11 w-full bg-surface-container-lowest text-on-surface rounded-lg px-3 outline-none border border-outline-variant focus:border-primary text-start"
                                />
                              </label>
                            ))}
                          </div>
                        ) : (
                          <div className="grid grid-cols-2 gap-x-3 gap-y-2 bg-surface-container-low/70 p-3 rounded-xl">
                            {([
                              ['pc_name', pickLocalizedName(lang, shownProductOf(msg.proposal, productEdits).name_ar, shownProductOf(msg.proposal, productEdits).name_en), true],
                              ['pc_buy', `${shownProductOf(msg.proposal, productEdits).unit_buy_price} ${t('currency')}`, false],
                              ['pc_sell', `${shownProductOf(msg.proposal, productEdits).unit_sell_price} ${t('currency')}`, false],
                              ['pc_qty', String(shownProductOf(msg.proposal, productEdits).stock_qty), false],
                              ['pc_min', String(shownProductOf(msg.proposal, productEdits).min_threshold), false],
                              ['pc_category', shownProductOf(msg.proposal, productEdits).category || '—', false],
                            ] as const).map(([label, value, wide]) => (
                              <div key={label} className={`flex flex-col ${wide ? 'col-span-2' : ''}`}>
                                <span className="font-label-sm text-label-sm text-on-surface-variant">{t(label)}</span>
                                <span className="font-label-lg text-label-lg font-bold text-on-surface">{value}</span>
                              </div>
                            ))}
                          </div>
                        )
                      )}

                      {isItemless(msg.proposal) && (
                        <div className="flex min-w-0 flex-col gap-2 bg-surface-container-low/70 p-3 rounded-xl">
                          {changeRowsOf(msg.proposal).length > 0 ? changeRowsOf(msg.proposal).map((row) => (
                            <div key={row.field} className="flex min-w-0 flex-col">
                              <span className="font-label-sm text-label-sm text-on-surface-variant">{t(row.label)}</span>
                              <span className="flex min-w-0 flex-wrap items-center gap-x-2 font-label-lg text-label-lg font-bold text-on-surface break-words">
                                {row.from && (
                                  <>
                                    <span className="text-on-surface-variant line-through font-normal break-words">{row.from}</span>
                                    <span className="material-symbols-outlined text-[16px] rtl:rotate-180">arrow_forward</span>
                                  </>
                                )}
                                <span className="break-words">{row.to}</span>
                              </span>
                            </div>
                          )) : (
                            <p className="font-label-md text-label-md text-on-surface break-words">
                              {lang === 'ar' ? msg.proposal.summary_ar : msg.proposal.summary_en}
                            </p>
                          )}
                        </div>
                      )}

                      {msg.proposal.action_type !== 'create_product' && !isItemless(msg.proposal) && (<>
                      <div className="flex min-w-0 flex-col gap-2 bg-surface-container-low/70 p-3 rounded-xl">
                        {shownItemsOf(msg.proposal, itemEdits).map((item, idx) => (
                          <React.Fragment key={idx}>
                            {idx > 0 && <div className="h-[1px] bg-outline-variant/30 w-full my-0.5" />}
                            {editingIds[msg.proposal!.id] && itemEdits[msg.proposal!.id]?.[idx] ? (
                              <div className="flex min-w-0 flex-col gap-2 text-on-surface">
                                <span className="font-label-lg text-label-lg font-bold break-words">{item.item_name}</span>
                                <div className="grid grid-cols-2 gap-2">
                                  {([
                                    ['quantity', 'as_quantity', 'decimal'],
                                    ['price', 'as_quantity', 'decimal'],
                                  ] as const).map(([field, label, mode]) => (
                                    <label key={field} className="flex min-w-0 flex-col gap-1">
                                      <span className="font-label-sm text-label-sm text-on-surface-variant break-words">
                                        {field === 'price' ? `${t('currency')} ${t('as_per_unit')}` : t(label)}
                                      </span>
                                      <input
                                        type="text"
                                        inputMode={mode}
                                        value={itemEdits[msg.proposal!.id][idx][field]}
                                        disabled={busyActionId !== null}
                                        onChange={(e) => {
                                          const id = msg.proposal!.id;
                                          const value = e.target.value;
                                          setItemEdits((current) => ({
                                            ...current,
                                            [id]: current[id].map((row, rowIndex) => rowIndex === idx ? { ...row, [field]: value } : row),
                                          }));
                                        }}
                                        className="h-11 w-full min-w-0 bg-surface-container-lowest text-on-surface rounded-lg px-3 outline-none border border-outline-variant focus:border-primary text-start"
                                      />
                                    </label>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <div className="flex min-w-0 items-center justify-between gap-3 text-on-surface">
                                <div className="flex min-w-0 flex-col">
                                  <span className="font-label-lg text-label-lg font-bold break-words">
                                    {item.item_name}
                                  </span>
                                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-on-surface-variant font-label-sm text-label-sm">
                                    <span className="bg-surface-container-high px-1.5 py-0.5 rounded font-medium">
                                      {t('as_quantity')} {item.quantity}
                                    </span>
                                    <span>{item.unit_price} {t('currency')} {t('as_per_unit')}</span>
                                  </div>
                                </div>
                                <div className="shrink-0 text-left font-stat-numeric text-[16px] font-bold text-on-surface">
                                  {item.subtotal}{' '}
                                  <span className="font-label-sm text-label-sm font-normal text-on-surface-variant">
                                    {t('currency')}
                                  </span>
                                </div>
                              </div>
                            )}
                          </React.Fragment>
                        ))}
                      </div>

                      {/* Final Total Block */}
                      <div className="flex items-center justify-between px-3 py-2.5 bg-surface-container rounded-xl">
                        <div className="flex items-center gap-2">
                          <span className="material-symbols-outlined text-secondary text-[22px]">payments</span>
                          <div className="flex flex-col">
                            <span className="font-label-md text-label-md text-on-surface font-bold">{t('as_total')}</span>
                            <span className="font-label-sm text-label-sm text-on-surface-variant">
                              {t('as_payment')} {msg.proposal.payment_method === 'cash' ? t('as_cash') : t('as_card')}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-baseline gap-1 text-primary">
                          <span className="font-stat-numeric text-stat-numeric text-primary tracking-tight font-extrabold">
                            {editingIds[msg.proposal.id] ? round2(shownItemsOf(msg.proposal, itemEdits).reduce((sum, item) => sum + item.subtotal, 0)) : msg.proposal.total_amount}
                          </span>
                          <span className="font-label-md text-label-md font-bold text-primary">{t('currency')}</span>
                        </div>
                      </div>

                      </>)}

                      {actionErrors[msg.proposal.id] && (
                        <div role="alert" className="rounded-lg bg-error-container px-3 py-2 text-sm text-on-error-container">
                          {actionErrors[msg.proposal.id]}
                        </div>
                      )}

                      {/* Decision CTAs */}
                      {!confirmedIds[msg.proposal.id] && <div className="flex flex-col gap-2 pt-1">
                        <button
                          type="button"
                          disabled={busyActionId !== null}
                          onClick={() => void handleConfirm(msg.proposal!, duplicateIds[msg.proposal!.id] === true)}
                          className="w-full h-[52px] bg-secondary text-on-secondary rounded-lg font-label-lg text-label-lg font-bold flex items-center justify-center gap-2 shadow-md active:scale-[0.98] transition-transform duration-100 disabled:opacity-60"
                        >
                          <span className="material-symbols-outlined text-[20px]">check_circle</span>
                          <span>{busyActionId === msg.proposal.id ? t('as_executing') : duplicateIds[msg.proposal.id] ? t('pc_save_anyway') : t('as_confirm_op')}</span>
                        </button>

                        <div className={`grid gap-2 ${isItemless(msg.proposal) ? 'grid-cols-1' : 'grid-cols-2'}`}>
                          {!isItemless(msg.proposal) && <button
                            type="button"
                            disabled={busyActionId !== null}
                            onClick={() => void handleRevise(msg.proposal!)}
                            className="h-[46px] bg-surface-container-high text-on-surface rounded-lg font-label-md text-label-md font-bold flex items-center justify-center gap-1.5 active:bg-surface-container-highest transition-colors disabled:opacity-60"
                          >
                            <span className="material-symbols-outlined text-[18px]">edit_note</span>
                            <span>{editingIds[msg.proposal.id] ? t('pc_done_editing') : t('as_revise')}</span>
                          </button>}
                          <button
                            type="button"
                            disabled={busyActionId !== null}
                            onClick={() => void handleCancel(msg.proposal!.id)}
                            className="h-[46px] bg-error-container text-on-error-container rounded-lg font-label-md text-label-md font-bold flex items-center justify-center gap-1.5 active:opacity-90 transition-opacity disabled:opacity-60"
                          >
                            <span className="material-symbols-outlined text-[18px]">cancel</span>
                            <span>{t('as_cancel_op')}</span>
                          </button>
                        </div>
                      </div>}

                      {/* Compact success state */}
                      {confirmedIds[msg.proposal.id] && (
                        <div role="status" className="flex items-center justify-between gap-3 rounded-lg bg-primary-container/50 px-3 py-2 text-on-surface">
                          <span className="inline-flex items-center gap-2 font-label-md text-label-md font-bold">
                            <span className="material-symbols-outlined text-primary">check_circle</span>
                            {t('as_saved')}
                          </span>
                          {!isItemless(msg.proposal) && (
                            <Link href="/records" className="shrink-0 text-primary font-label-sm text-label-sm underline">
                              {t('as_view_records')}
                            </Link>
                          )}
                        </div>
                      )}

                      {/* Invitation link: returned once by the server when the invitation is confirmed */}
                      {confirmedIds[msg.proposal.id] && msg.proposal.action_type === 'create_invite' && (
                        inviteLinks[msg.proposal.id] ? (
                          <div className="flex min-w-0 flex-col gap-2 rounded-xl bg-surface-container-low/70 p-3">
                            <span className="font-label-sm text-label-sm text-on-surface-variant">{t('ia_link')}</span>
                            <input
                              type="text"
                              readOnly
                              dir="ltr"
                              value={`${window.location.origin}${inviteLinks[msg.proposal.id].path}`}
                              onFocus={(e) => e.currentTarget.select()}
                              className="h-11 w-full min-w-0 rounded-lg border border-outline-variant bg-surface-container-lowest px-3 text-start text-on-surface outline-none focus:border-primary"
                            />
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="font-label-sm text-label-sm text-on-surface-variant break-words">
                                {inviteLinks[msg.proposal.id].expires
                                  ? `${t('ia_expires')} ${parseServerTime(inviteLinks[msg.proposal.id].expires as string).toLocaleDateString(localeOf(lang))}. `
                                  : ''}
                                {t('ia_once')}
                              </span>
                              <button
                                type="button"
                                onClick={() => void handleCopyInvite(msg.proposal!.id, `${window.location.origin}${inviteLinks[msg.proposal!.id].path}`)}
                                className="h-11 shrink-0 rounded-lg bg-primary px-4 font-label-md text-label-md font-bold text-on-primary active:scale-95 transition-transform"
                              >
                                {copiedId === msg.proposal.id ? t('ia_copied') : t('ia_copy')}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="rounded-lg bg-surface-container-low/70 px-3 py-2 font-label-md text-label-md text-on-surface-variant break-words">
                            {t('ia_missing')}
                          </p>
                        )
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Typing Loader */}
            {isLoading && (
              <div className="flex items-center gap-2 self-start bg-surface-container-lowest px-4 py-2.5 rounded-xl shadow-sm">
                <span className="material-symbols-outlined text-primary text-[18px] animate-spin">
                  progress_activity
                </span>
                <span className="text-xs text-on-surface-variant font-medium">{t('as_processing')}</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* ── FLOATING CONTEXT CHIPS (Quick Actions) ── */}
          <div className="w-full mt-6 mb-2">
            <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar">
              <button
                type="button"
                onClick={() => setInputVal(t('as_chip_sale_text'))}
                className="flex-shrink-0 bg-surface-container-lowest text-primary px-3.5 py-2 rounded-full font-label-md text-label-md shadow-sm flex items-center gap-1.5 active:scale-95 transition-transform"
              >
                <span className="material-symbols-outlined text-[18px] icon-filled">add_shopping_cart</span>
                <span>{t('as_chip_sale')}</span>
              </button>
              <button
                type="button"
                onClick={() => setInputVal(t('as_chip_med_text'))}
                className="flex-shrink-0 bg-surface-container-lowest text-on-surface-variant px-3.5 py-2 rounded-full font-label-md text-label-md shadow-sm flex items-center gap-1.5 active:scale-95 transition-transform"
              >
                <span className="material-symbols-outlined text-[18px]">biotech</span>
                <span>{t('as_chip_med')}</span>
              </button>
              <button
                type="button"
                onClick={() => setInputVal(t('hm_ex_low_stock'))}
                className="flex-shrink-0 bg-surface-container-lowest text-on-surface-variant px-3.5 py-2 rounded-full font-label-md text-label-md shadow-sm flex items-center gap-1.5 active:scale-95 transition-transform"
              >
                <span className="material-symbols-outlined text-[18px]">inventory</span>
                <span>{t('as_chip_inv')}</span>
              </button>
              <button
                type="button"
                onClick={() => setInputVal(t('as_chip_sum_text'))}
                className="flex-shrink-0 bg-surface-container-lowest text-on-surface-variant px-3.5 py-2 rounded-full font-label-md text-label-md shadow-sm flex items-center gap-1.5 active:scale-95 transition-transform"
              >
                <span className="material-symbols-outlined text-[18px]">history</span>
                <span>{t('as_chip_sum')}</span>
              </button>
            </div>
          </div>

          {/* ── DOCKED BOTTOM INTERACTION BAR (Thumb-Centric) ── */}
          <p className="px-2 text-label-sm text-on-surface-variant">
            {t('as_privacy')}
          </p>
          <div className="w-full bg-surface-container-lowest rounded-xl p-2.5 shadow-[0px_4px_16px_rgba(26,36,32,0.08)] flex items-center gap-2 mt-1">
            {/* Quick OCR Prescription Camera Trigger */}
            <Link
              href="/scan"
              aria-label={t('as_camera_label')}
              className="w-11 h-11 rounded-lg bg-primary-container text-on-primary-container flex items-center justify-center active:scale-95 shadow-sm transition-transform flex-shrink-0"
            >
              <span className="material-symbols-outlined text-[24px]">photo_camera</span>
            </Link>

            {/* Voice Input Mic Button */}
            <button
              type="button"
              aria-label={t('hm_voice_label')}
              onClick={toggleVoiceRecording}
              className={`w-11 h-11 rounded-lg flex items-center justify-center active:scale-95 transition-all flex-shrink-0 ${
                isRecording
                  ? 'bg-error text-on-error animate-pulse'
                  : 'bg-surface-container-high text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[22px]">mic</span>
            </button>

            {/* Chat Message Text Input */}
            <div className="relative flex-1 min-w-0">
              <input
                type="text"
                id="chatInput"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape' && listeningRef.current) cancelVoiceRecording();
                  else if (e.key === 'Enter') handleSend();
                }}
                placeholder={isRecording ? t('as_listening') : t('as_placeholder')}
                className="w-full h-11 bg-surface-container-low text-on-surface placeholder:text-outline font-body-md text-body-md rounded-lg px-3 outline-none focus:bg-surface-container-lowest transition-colors text-start"
              />
            </div>

            {/* Send CTA */}
            <button
              type="button"
              aria-label={t('as_send')}
              onClick={() => handleSend()}
              disabled={isLoading || !inputVal.trim()}
              className="w-11 h-11 rounded-lg bg-primary text-on-primary flex items-center justify-center active:scale-95 transition-transform flex-shrink-0 shadow-sm disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-[22px] rotate-180">send</span>
            </button>
          </div>

        </div>
      </main>

      <BottomNav />

      <ToastStack toasts={toasts} onDismiss={dismiss} dismissLabel={t('rs_dismiss')} />
    </div>
  );
}

export default function AssistantPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-surface flex items-center justify-center">
          <span className="material-symbols-outlined animate-spin text-primary text-3xl">
            progress_activity
          </span>
        </div>
      }
    >
      <AssistantContent />
    </Suspense>
  );
}