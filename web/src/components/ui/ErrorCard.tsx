// web/src/components/ui/ErrorCard.tsx (replaces numbers that failed to load; never shows zeros as if they were data)
'use client';

import React from 'react';

interface ErrorCardProps {
  message: string;
  retryLabel: string;
  onRetry: () => void;
  retrying?: boolean;
}

export function ErrorCard({ message, retryLabel, onRetry, retrying = false }: ErrorCardProps) {
  return (
    <div
      role="alert"
      className="flex flex-col gap-space-md rounded-xl bg-error-container p-space-md text-on-error-container shadow-sm sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 items-center gap-space-sm">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-on-error text-error">
          <span className="material-symbols-outlined text-[22px]" aria-hidden="true">error</span>
        </div>
        <span className="min-w-0 font-label-lg text-label-lg">{message}</span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        disabled={retrying}
        className="flex min-h-[44px] w-full shrink-0 items-center justify-center gap-space-xs rounded-lg bg-primary px-space-md font-label-md text-label-md text-on-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60 sm:w-auto"
      >
        <span
          className={`material-symbols-outlined text-[18px] ${retrying ? 'animate-spin motion-reduce:animate-none' : ''}`}
          aria-hidden="true"
        >
          {retrying ? 'progress_activity' : 'refresh'}
        </span>
        <span>{retryLabel}</span>
      </button>
    </div>
  );
}