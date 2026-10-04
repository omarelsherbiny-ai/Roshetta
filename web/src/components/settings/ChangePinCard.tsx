// web/src/components/settings/ChangePinCard.tsx (card inside /settings/account: change the signed-in person's PIN; texts are the cp_* keys of locales/)
'use client';

import React, { useEffect, useRef, useState } from 'react';
import { InlineBanner } from '@/components/ui/InlineBanner';
import { ToastStack, useToasts } from '@/components/ui/Toast';
import { PinChangeError, changePin } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';

const PIN_MIN = 4;
const PIN_MAX = 6;
/** The server blocks a key for 15 minutes; it sends no Retry-After, so the form stays locked for the same time here. */
const LOCK_MS = 15 * 60 * 1000;

type FieldName = 'current' | 'next' | 'confirm';
type Notice = { kind: 'error' | 'warning'; message: string; retry?: () => void } | null;

/** Digits only: Arabic-Indic and Persian digits from a phone keypad become 0-9, anything else is dropped. */
function cleanPin(raw: string): string {
  return raw
    .replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/\D/g, '')
    .slice(0, PIN_MAX);
}

const cardClass = 'flex flex-col gap-space-md rounded-xl bg-surface-container-lowest p-space-lg shadow-sm';
const labelClass = 'font-label-lg text-label-lg text-on-surface';
const hintClass = 'font-body-sm text-body-sm text-on-surface-variant';
const inputClass =
  'h-touch-target-min w-full rounded-lg bg-surface-container-low pe-12 ps-space-md font-headline-sm text-headline-sm tracking-widest text-on-surface outline-none placeholder:text-on-surface-variant/60 focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-60';

interface PinFieldProps {
  id: string;
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: 'current-password' | 'new-password';
  visible: boolean;
  onToggle: () => void;
  showLabel: string;
  hideLabel: string;
  disabled: boolean;
  error: string | null;
  inputRef?: React.Ref<HTMLInputElement>;
}

function PinField({
  id, label, hint, value, onChange, autoComplete, visible, onToggle, showLabel, hideLabel, disabled, error, inputRef,
}: PinFieldProps) {
  const describedBy = [hint ? `${id}-hint` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ') || undefined;
  return (
    <div className="flex flex-col gap-space-xs">
      <div className="flex items-center justify-between gap-2">
        <label className={labelClass} htmlFor={id}>{label}</label>
        {hint && <span id={`${id}-hint`} className={hintClass}>{hint}</span>}
      </div>
      <div className="relative flex items-center">
        <input
          ref={inputRef}
          id={id}
          type={visible ? 'text' : 'password'}
          inputMode="numeric"
          autoComplete={autoComplete}
          maxLength={PIN_MAX}
          value={value}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => onChange(cleanPin(event.target.value))}
          className={`${inputClass} ${error ? 'ring-2 ring-error' : ''}`}
        />
        <button
          type="button"
          onClick={onToggle}
          disabled={disabled}
          aria-pressed={visible}
          aria-label={visible ? hideLabel : showLabel}
          className="absolute end-0 flex h-touch-target-min w-touch-target-min items-center justify-center rounded-lg text-on-surface-variant hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
        >
          <span className="material-symbols-outlined text-[22px]" aria-hidden="true">
            {visible ? 'visibility_off' : 'visibility'}
          </span>
        </button>
      </div>
      {error && (
        <p id={`${id}-error`} role="alert" className="flex items-center gap-1 font-body-sm text-body-sm text-error">
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">error</span>
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}

export function ChangePinCard() {
  const { t } = useLanguage();
  const { toasts, push, dismiss } = useToasts();

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [shown, setShown] = useState<Record<FieldName, boolean>>({ current: false, next: false, confirm: false });
  const [submitting, setSubmitting] = useState(false);
  const [wrongPin, setWrongPin] = useState(false);
  const [locked, setLocked] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const currentRef = useRef<HTMLInputElement>(null);
  const lockTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (lockTimer.current) clearTimeout(lockTimer.current);
    };
  }, []);

  // After a wrong current PIN the fields are enabled again: put the cursor where the fix is.
  useEffect(() => {
    if (wrongPin && !submitting) currentRef.current?.focus();
  }, [wrongPin, submitting]);

  const newLengthOk = next.length >= PIN_MIN && next.length <= PIN_MAX;
  const sameAsCurrent = newLengthOk && current.length > 0 && next === current;
  const mismatch = confirm.length > 0 && confirm !== next;
  const valid = current.length >= PIN_MIN && newLengthOk && !sameAsCurrent && confirm === next;

  const newError =
    next.length > 0 && next.length < PIN_MIN ? t('cp_err_length') : sameAsCurrent ? t('cp_err_same') : null;
  const confirmError = mismatch ? t('cp_err_mismatch') : null;
  const currentError = wrongPin ? t('cp_wrong_current') : null;
  const fieldsDisabled = submitting || locked;

  /** Editing anything clears a failure message that no longer matches what is typed (a lockout stays). */
  const edited = () => {
    setWrongPin(false);
    setNotice((previous) => (previous?.kind === 'warning' ? previous : null));
  };

  const toggle = (field: FieldName) => setShown((previous) => ({ ...previous, [field]: !previous[field] }));

  const submit = async () => {
    if (!valid || submitting || locked) return;
    setSubmitting(true);
    setNotice(null);
    setWrongPin(false);
    try {
      await changePin(current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
      setShown({ current: false, next: false, confirm: false });
      push('success', t('cp_changed'));
    } catch (error) {
      const failure = error instanceof PinChangeError ? error.failure : 'other';
      if (failure === 'wrong_pin') {
        setWrongPin(true);
      } else if (failure === 'throttled') {
        setLocked(true);
        setNotice({ kind: 'warning', message: t('cp_throttled') });
        if (lockTimer.current) clearTimeout(lockTimer.current);
        lockTimer.current = setTimeout(() => {
          setLocked(false);
          setNotice(null);
        }, LOCK_MS);
      } else {
        setNotice({
          kind: 'error',
          message: failure === 'network' || !(error instanceof Error) ? t('cp_network') : error.message,
          retry: () => void submit(),
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <form
        className={cardClass}
        noValidate
        aria-busy={submitting}
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[22px] text-primary" aria-hidden="true">lock_reset</span>
          <h2 className="font-headline-sm text-headline-sm text-on-surface">{t('cp_title')}</h2>
        </div>

        {notice && (
          <InlineBanner
            kind={notice.kind}
            message={notice.message}
            retryLabel={t('retry')}
            onRetry={notice.retry}
            dismissLabel={t('rs_dismiss')}
            onDismiss={notice.kind === 'warning' ? undefined : () => setNotice(null)}
          />
        )}

        <div className="grid grid-cols-1 gap-space-md md:grid-cols-3">
          <PinField
            id="cp-current"
            label={t('cp_current')}
            hint={t('cp_hint_digits')}
            value={current}
            onChange={(value) => {
              edited();
              setCurrent(value);
            }}
            autoComplete="current-password"
            visible={shown.current}
            onToggle={() => toggle('current')}
            showLabel={t('cp_show')}
            hideLabel={t('cp_hide')}
            disabled={fieldsDisabled}
            error={currentError}
            inputRef={currentRef}
          />
          <PinField
            id="cp-new"
            label={t('cp_new')}
            hint={t('cp_hint_digits')}
            value={next}
            onChange={(value) => {
              edited();
              setNext(value);
            }}
            autoComplete="new-password"
            visible={shown.next}
            onToggle={() => toggle('next')}
            showLabel={t('cp_show')}
            hideLabel={t('cp_hide')}
            disabled={fieldsDisabled}
            error={newError}
          />
          <PinField
            id="cp-confirm"
            label={t('cp_confirm')}
            value={confirm}
            onChange={(value) => {
              edited();
              setConfirm(value);
            }}
            autoComplete="new-password"
            visible={shown.confirm}
            onToggle={() => toggle('confirm')}
            showLabel={t('cp_show')}
            hideLabel={t('cp_hide')}
            disabled={fieldsDisabled}
            error={confirmError}
          />
        </div>

        <div className="flex items-start gap-space-sm rounded-lg bg-surface-container-low p-space-md">
          <span className="material-symbols-outlined text-[20px] text-primary" aria-hidden="true">info</span>
          <p className={`${hintClass} leading-relaxed`}>{t('cp_helper')}</p>
        </div>

        <div className="flex justify-end pt-space-xs">
          <button
            type="submit"
            disabled={!valid || fieldsDisabled}
            className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-primary px-6 font-label-lg text-label-lg text-on-primary shadow-sm transition hover:bg-primary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
          >
            <span
              className={`material-symbols-outlined text-[20px] ${submitting ? 'animate-spin motion-reduce:animate-none' : ''}`}
              aria-hidden="true"
            >
              {submitting ? 'progress_activity' : 'key'}
            </span>
            <span>{submitting ? t('cp_submitting') : t('cp_submit')}</span>
          </button>
        </div>
      </form>

      <ToastStack toasts={toasts} onDismiss={dismiss} dismissLabel={t('rs_dismiss')} />
    </>
  );
}