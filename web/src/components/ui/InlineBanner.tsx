// web/src/components/ui/InlineBanner.tsx (persistent inline success, warning or error message with optional retry; no alert())
'use client';

import React from 'react';

interface InlineBannerProps {
  kind: 'success' | 'error' | 'warning';
  message: string;
  /** Both are optional: a banner without `onDismiss` stays until the page removes it (for example a lockout). */
  dismissLabel?: string;
  onDismiss?: () => void;
  retryLabel?: string;
  onRetry?: () => void;
}

const KIND_STYLE = {
  success: { box: 'bg-surface-container-high text-on-surface', icon: 'check_circle', iconColor: 'text-primary', role: 'status' },
  error: { box: 'bg-error-container text-error', icon: 'error', iconColor: 'text-error', role: 'alert' },
  warning: { box: 'bg-secondary-fixed text-on-secondary-fixed', icon: 'lock_clock', iconColor: 'text-secondary', role: 'alert' },
} as const;

export function InlineBanner({ kind, message, dismissLabel, onDismiss, retryLabel, onRetry }: InlineBannerProps) {
  const style = KIND_STYLE[kind];
  return (
    <div
      role={style.role}
      className={`flex flex-wrap items-center gap-space-sm rounded-xl p-space-md shadow-sm ${style.box}`}
    >
      <span className={`material-symbols-outlined text-[22px] ${style.iconColor}`} aria-hidden="true">
        {style.icon}
      </span>
      <span className="min-w-0 flex-1 font-label-lg text-label-lg">{message}</span>
      {kind === 'error' && onRetry && retryLabel && (
        <button
          type="button"
          onClick={onRetry}
          className="min-h-[44px] rounded-lg px-3 font-label-lg text-label-lg underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error"
        >
          {retryLabel}
        </button>
      )}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={dismissLabel}
          className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-black/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <span className="material-symbols-outlined text-[20px]" aria-hidden="true">close</span>
        </button>
      )}
    </div>
  );
}