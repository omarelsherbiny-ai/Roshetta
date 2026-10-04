// web/src/components/ui/ConfirmDialog.tsx (in-app confirmation that replaces window.confirm)
// Bottom sheet on phones, centered dialog from `sm` up. If the action throws, the dialog stays open and shows the error.
'use client';

import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  retryLabel: string;
  /** Shown on the confirm button while the action runs. */
  busyLabel: string;
  /** Used when the thrown error has no message. */
  fallbackError: string;
  variant?: 'default' | 'destructive';
  /** Runs the action. Throw or reject to keep the dialog open and show the error. */
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  retryLabel,
  busyLabel,
  fallbackError,
  variant = 'default',
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const destructive = variant === 'destructive';

  const close = useCallback(() => {
    if (!busyRef.current) onClose();
  }, [onClose]);

  // A fresh start every time the dialog opens.
  useEffect(() => {
    if (open) {
      busyRef.current = false;
      setBusy(false);
      setError(null);
    }
  }, [open]);

  // Lock page scroll, start on Cancel (the safe choice), and give focus back when closed.
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    cancelRef.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [open]);

  // After a failure the buttons are enabled again: put focus on Retry.
  useEffect(() => {
    if (error) confirmRef.current?.focus();
  }, [error]);

  // Escape closes; Tab stays inside the dialog.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      const panel = panelRef.current;
      if (event.key !== 'Tab' || !panel) return;
      const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const active = document.activeElement;
      if (!panel.contains(active)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, close]);

  const handleConfirm = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      busyRef.current = false;
      setBusy(false);
      onClose();
    } catch (err) {
      busyRef.current = false;
      setBusy(false);
      setError(err instanceof Error && err.message ? err.message : fallbackError);
    }
  };

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-inverse-surface/50" aria-hidden="true" onClick={close} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="relative w-full rounded-t-2xl bg-surface-container-lowest p-space-lg pb-[max(1.5rem,env(safe-area-inset-bottom))] text-on-surface shadow-lg sm:max-w-md sm:rounded-2xl"
      >
        <div className="mx-auto mb-space-md h-1 w-10 rounded-full bg-outline-variant sm:hidden" aria-hidden="true" />
        <div className="flex items-start gap-space-md">
          <div
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
              destructive ? 'bg-error-container text-error' : 'bg-surface-container text-primary'
            }`}
          >
            <span className="material-symbols-outlined text-[26px]" aria-hidden="true">
              {destructive ? 'gpp_bad' : 'task_alt'}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className={`font-headline-sm text-headline-sm ${destructive ? 'text-error' : 'text-on-surface'}`}>
              {title}
            </h2>
            <p id={descriptionId} className="mt-1 font-body-md text-body-md text-on-surface-variant">
              {description}
            </p>
          </div>
        </div>

        {error && (
          <div role="alert" className="mt-space-md flex items-start gap-space-sm rounded-xl bg-error-container p-space-md text-on-error-container">
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">error</span>
            <span className="min-w-0 flex-1 break-words font-label-md text-label-md">{error}</span>
          </div>
        )}

        <div className="mt-space-lg flex items-center gap-space-sm sm:justify-end">
          <button
            ref={cancelRef}
            type="button"
            disabled={busy}
            onClick={close}
            className="h-12 min-h-[48px] flex-1 rounded-lg bg-surface-container-high px-5 font-label-lg text-label-lg text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50 sm:flex-none"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            disabled={busy}
            onClick={() => void handleConfirm()}
            className={`flex h-12 min-h-[48px] flex-1 items-center justify-center gap-space-xs rounded-lg px-5 font-label-lg text-label-lg shadow-sm focus-visible:outline-none focus-visible:ring-2 disabled:opacity-60 sm:flex-none ${
              destructive ? 'bg-error text-on-error focus-visible:ring-error' : 'bg-primary text-on-primary focus-visible:ring-primary'
            }`}
          >
            {busy ? (
              <>
                <span className="material-symbols-outlined animate-spin text-[18px] motion-reduce:animate-none" aria-hidden="true">progress_activity</span>
                <span>{busyLabel}</span>
              </>
            ) : error ? (
              <>
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">refresh</span>
                <span>{retryLabel}</span>
              </>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}