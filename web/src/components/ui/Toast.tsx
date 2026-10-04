// web/src/components/ui/Toast.tsx (short messages that replace alert(); state lives in the page through useToasts)
'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';

export type ToastKind = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

const AUTO_HIDE_MS = 5000;

/** Toast state for one page. Errors stay until dismissed; the other kinds hide after a few seconds. */
export function useToasts() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, kind, message }]);
      if (kind !== 'error') {
        timers.current.set(id, setTimeout(() => dismiss(id), AUTO_HIDE_MS));
      }
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
    };
  }, []);

  return { toasts, push, dismiss };
}

const KIND_STYLE: Record<ToastKind, { icon: string; bar: string; badge: string }> = {
  success: { icon: 'check_circle', bar: 'bg-primary', badge: 'bg-primary-fixed text-on-primary-fixed' },
  error: { icon: 'report', bar: 'bg-error', badge: 'bg-error-container text-error' },
  warning: { icon: 'warning', bar: 'bg-secondary', badge: 'bg-secondary-fixed text-on-secondary-fixed' },
  info: { icon: 'info', bar: 'bg-primary-container', badge: 'bg-surface-container-high text-primary' },
};

interface ToastStackProps {
  toasts: ToastItem[];
  onDismiss: (id: number) => void;
  dismissLabel: string;
}

/** Phone: above the bottom bar. Desktop: top corner at the end side (left in Arabic, right in English). */
export function ToastStack({ toasts, onDismiss, dismissLabel }: ToastStackProps) {
  if (toasts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed inset-x-margin-mobile bottom-24 z-[70] flex flex-col gap-space-sm sm:inset-x-auto sm:bottom-auto sm:end-6 sm:top-20 sm:w-96">
      {toasts.map((toast) => {
        const style = KIND_STYLE[toast.kind];
        const urgent = toast.kind === 'error' || toast.kind === 'warning';
        return (
          <div
            key={toast.id}
            role={urgent ? 'alert' : 'status'}
            className="pointer-events-auto relative flex items-center justify-between gap-space-sm overflow-hidden rounded-xl bg-surface-container-lowest p-space-md ps-space-lg text-on-surface shadow-lg"
          >
            <div className={`absolute inset-y-0 start-0 w-1.5 ${style.bar}`} aria-hidden="true" />
            <div className="flex min-w-0 items-center gap-space-sm">
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${style.badge}`}>
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{style.icon}</span>
              </div>
              <span className="min-w-0 break-words font-body-md text-body-md">{toast.message}</span>
            </div>
            <button
              type="button"
              aria-label={dismissLabel}
              onClick={() => onDismiss(toast.id)}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-on-surface-variant hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <span className="material-symbols-outlined text-[20px]" aria-hidden="true">close</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}