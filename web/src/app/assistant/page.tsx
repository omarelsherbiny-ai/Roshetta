// web/src/app/assistant/page.tsx (route: /assistant — chat assistant with action proposals)
'use client';

import React, { useState, useEffect, useRef, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { ToastStack, useToasts } from '@/components/ui/Toast';
import { sendChatMessage, confirmActionProposal, cancelActionProposal, getPendingActionProposals } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { ChatMessage, ActionProposal, ProposedItem } from '@/types';
import { useLanguage } from '@/lib/i18n';
import { localeOf, pickLocalizedName } from '@/lib/languages';
import { usePharmacyName } from '@/hooks/usePharmacyName';
import { getSpeechRecognition } from '@/lib/speech';

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
  const [pendingActionsNotice, setPendingActionsNotice] = useState<string | null>(null);
  const [busyActionId, setBusyActionId] = useState<string | null>(null);
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});

  const messagesEndRef = useRef<HTMLDivElement>(null);
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

  useEffect(() => {
    if (!isAuthenticated()) return;
    let active = true;
    getPendingActionProposals().then(({ actions, unavailable_count }) => {
      if (!active) return;
      setMessages((current) => {
        const byId = new Map(actions.map((proposal) => [proposal.id, proposal]));
        const refreshed = current.map((message) => {
          if (!message.id.startsWith('pending-') || !message.proposal) return message;
          const latest = byId.get(message.proposal.id);
          return latest ? {
            ...message,
            text: pickLocalizedName(lang, latest.summary_ar, latest.summary_en),
            proposal: latest,
          } : message;
        });
        const knownIds = new Set(refreshed.map((message) => message.proposal?.id).filter(Boolean));
        const recovered = actions
          .filter((proposal) => !knownIds.has(proposal.id))
          .map((proposal) => ({
            id: `pending-${proposal.id}`,
            sender: 'assistant' as const,
            text: pickLocalizedName(lang, proposal.summary_ar, proposal.summary_en),
            timestamp: formatTime(proposal.created_at ?? Date.now()),
            proposal,
          }));
        return [...refreshed, ...recovered];
      });
      setPendingActionsNotice(unavailable_count > 0
        ? t('as_pending_unavailable').replace('{count}', String(unavailable_count))
        : null);
    }).catch(() => {
      if (active) setPendingActionsNotice(t('as_pending_restore_error'));
    });
    return () => { active = false; };
  }, [lang]);

  // Handle URL prompt if redirected from Dashboard
  useEffect(() => {
    if (initialPrompt && initialPrompt.trim()) {
      handleSend(initialPrompt.trim());
    }
  }, [initialPrompt]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend ?? inputVal).trim();
    if (!text || isLoading) return;

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
      const response = await sendChatMessage(text, 'default', lang);
      setMessages((prev) => [...prev, response]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'assistant',
          text: `${t('as_err_prefix')} ${err.message || t('as_err_connect')}`,
          timestamp: formatTime(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = async (proposalId: string, items: ProposedItem[]) => {
    if (busyActionId) return;
    setBusyActionId(proposalId);
    setActionErrors((current) => { const next = { ...current }; delete next[proposalId]; return next; });
    try {
      await confirmActionProposal(proposalId, items);
      setConfirmedIds((prev) => ({ ...prev, [proposalId]: true }));
    } catch (e: any) {
      setActionErrors((current) => ({ ...current, [proposalId]: `${t('as_confirm_failed')}: ${e.message}` }));
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
    } catch (e: any) {
      setActionErrors((current) => ({ ...current, [proposalId]: `${t('as_cancel_failed')}: ${e.message}` }));
    } finally {
      setBusyActionId(null);
    }
  };

  const handleRevise = async (proposal: ActionProposal) => {
    if (busyActionId) return;
    setBusyActionId(proposal.id);
    setActionErrors((current) => { const next = { ...current }; delete next[proposal.id]; return next; });
    try {
      await cancelActionProposal(proposal.id);
      setCancelledIds((current) => ({ ...current, [proposal.id]: true }));
      const firstItem = proposal.items[0]?.item_name ?? '';
      setInputVal(t('as_revise_prefix').replace('{name}', firstItem));
    } catch (error: any) {
      setActionErrors((current) => ({ ...current, [proposal.id]: `${t('as_revise_failed')}: ${error.message}` }));
    } finally {
      setBusyActionId(null);
    }
  };

  const toggleVoiceRecording = () => {
    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      push('warning', t('as_voice_unsupported'));
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = localeOf(lang);
    recognition.interimResults = false;

    if (!isRecording) {
      recognition.onstart = () => setIsRecording(true);
      recognition.onend = () => setIsRecording(false);
      recognition.onerror = () => setIsRecording(false);
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInputVal(transcript);
        handleSend(transcript);
      };
      recognition.start();
    } else {
      setIsRecording(false);
    }
  };

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

            {pendingActionsNotice && (
              <div role="status" className="rounded-lg bg-error-container px-3 py-2 text-sm text-on-error-container">
                {pendingActionsNotice}
              </div>
            )}

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

                    <div className={`flex flex-col gap-1 w-full ${!isAssistant ? 'items-end' : ''}`}>
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
                        className={`p-space-md rounded-xl shadow-sm text-on-surface ${
                          isAssistant
                            ? 'bg-surface-container-lowest rounded-tr-none shadow-[0px_2px_8px_-1px_rgba(26,36,32,0.05)]'
                            : 'bg-surface-container rounded-tl-none'
                        }`}
                      >
                        <p className="font-body-md text-body-md leading-relaxed whitespace-pre-wrap text-start">
                          {msg.text}
                        </p>

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
                            <span className="material-symbols-outlined text-[19px]">point_of_sale</span>
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

                        <div className="flex items-center gap-1 bg-secondary-container/30 text-secondary px-2.5 py-1 rounded-full">
                          <span className="material-symbols-outlined text-[14px] animate-spin">hourglass_top</span>
                          <span className="font-label-sm text-label-sm font-bold">{t('as_awaiting')}</span>
                        </div>
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
                      <div className="flex flex-col gap-2 bg-surface-container-low/70 p-3 rounded-xl">
                        {msg.proposal.items.map((item, idx) => (
                          <React.Fragment key={idx}>
                            {idx > 0 && <div className="h-[1px] bg-outline-variant/30 w-full my-0.5" />}
                            <div className="flex items-center justify-between text-on-surface">
                              <div className="flex flex-col">
                                <span className="font-label-lg text-label-lg font-bold">
                                  {item.item_name}
                                </span>
                                <div className="flex items-center gap-2 text-on-surface-variant font-label-sm text-label-sm">
                                  <span className="bg-surface-container-high px-1.5 py-0.5 rounded font-medium">
                                    {t('as_quantity')} {item.quantity}
                                  </span>
                                  <span>{item.unit_price} {t('currency')} {t('as_per_unit')}</span>
                                </div>
                              </div>
                              <div className="text-left font-stat-numeric text-[16px] font-bold text-on-surface">
                                {item.subtotal}{' '}
                                <span className="font-label-sm text-label-sm font-normal text-on-surface-variant">
                                  {t('currency')}
                                </span>
                              </div>
                            </div>
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
                            {msg.proposal.total_amount}
                          </span>
                          <span className="font-label-md text-label-md font-bold text-primary">{t('currency')}</span>
                        </div>
                      </div>

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
                          onClick={() => void handleConfirm(msg.proposal!.id, msg.proposal!.items)}
                          className="w-full h-[52px] bg-secondary text-on-secondary rounded-lg font-label-lg text-label-lg font-bold flex items-center justify-center gap-2 shadow-md active:scale-[0.98] transition-transform duration-100 disabled:opacity-60"
                        >
                          <span className="material-symbols-outlined text-[20px]">check_circle</span>
                          <span>{busyActionId === msg.proposal.id ? t('as_executing') : t('as_confirm_op')}</span>
                        </button>

                        <div className="grid grid-cols-2 gap-2">
                          <button
                            type="button"
                            disabled={busyActionId !== null}
                            onClick={() => void handleRevise(msg.proposal!)}
                            className="h-[46px] bg-surface-container-high text-on-surface rounded-lg font-label-md text-label-md font-bold flex items-center justify-center gap-1.5 active:bg-surface-container-highest transition-colors disabled:opacity-60"
                          >
                            <span className="material-symbols-outlined text-[18px]">edit_note</span>
                            <span>{busyActionId === msg.proposal.id ? t('as_cancelling') : t('as_revise')}</span>
                          </button>
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
                          <Link href="/records" className="shrink-0 text-primary font-label-sm text-label-sm underline">
                            {t('as_view_records')}
                          </Link>
                        </div>
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
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
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