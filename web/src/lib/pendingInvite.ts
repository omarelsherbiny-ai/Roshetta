// web/src/lib/pendingInvite.ts
'use client';

/**
 * A person who opens an invitation link may not have an account yet. The token is kept in
 * sessionStorage (this tab only, gone when the tab closes) from the moment the link is
 * opened until the invitation is accepted or the server refuses it, so a reload, the
 * sign-in redirect or the switch between "create account" and "sign in" cannot lose it.
 *
 * New links carry the token in the #fragment (/onboarding#invite=<token>): the browser
 * never sends a fragment to the server, so tunnels and proxies cannot log it. The old
 * ?invite=<token> form is still read, so links created before this change keep working.
 */

const KEY = 'roshetta_pending_invite';
const MAX_TOKEN_LENGTH = 256;

function clean(raw: string | null | undefined): string {
  const value = (raw ?? '').trim();
  return value.length > 0 && value.length <= MAX_TOKEN_LENGTH ? value : '';
}

/** The token in the address bar (fragment first, then the old query form), or ''. */
function readFromUrl(): string {
  const fromHash = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('invite');
  return clean(fromHash) || clean(new URLSearchParams(window.location.search).get('invite'));
}

export function getPendingInvite(): string {
  if (typeof window === 'undefined') return '';
  try {
    return clean(sessionStorage.getItem(KEY));
  } catch {
    return '';
  }
}

export function clearPendingInvite(): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: nothing to clear */
  }
}

/**
 * Call once when a page opens. A token found in the address bar is saved and removed from
 * the address bar (a reload cannot resend it, and it stays out of the history entry);
 * otherwise the saved one is returned. Returns '' when there is no pending invitation.
 */
export function capturePendingInvite(): string {
  if (typeof window === 'undefined') return '';
  const fromUrl = readFromUrl();
  if (fromUrl) {
    try {
      sessionStorage.setItem(KEY, fromUrl);
    } catch {
      /* storage unavailable: the token still works for this page load */
    }
    window.history.replaceState(null, '', window.location.pathname);
    return fromUrl;
  }
  return getPendingInvite();
}