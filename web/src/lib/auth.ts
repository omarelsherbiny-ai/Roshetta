'use client';

import { persistLanguage } from '@/lib/i18n';

/** Client-side auth helpers. The server validates the signed token and membership. */

export interface ParsedToken {
  userId: number;
  pharmacyId: number | null;
  role: string;
}

/** Returns true when a valid token exists in sessionStorage. */
export function isAuthenticated(): boolean {
  if (typeof window === 'undefined') return false;
  const token = sessionStorage.getItem('roshetta_token');
  return !!token;
}

/** Reads cached display context; these values must never be used for authorization. */
export function parseToken(): ParsedToken | null {
  if (typeof window === 'undefined') return null;
  const raw = sessionStorage.getItem('roshetta_auth_context');
  if (!raw) return null;
  try { return JSON.parse(raw) as ParsedToken; } catch { return null; }
}

/** Clears all Roshetta auth state. */
export function clearAuth(): void {
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem('roshetta_token');
  sessionStorage.removeItem('roshetta_user');
  sessionStorage.removeItem('roshetta_role');
  sessionStorage.removeItem('roshetta_pharmacy');
  sessionStorage.removeItem('roshetta_auth_context');
  localStorage.removeItem('roshetta_user');
}

/** Replaces only the access token (after a PIN change the server revokes the old one); user, role and pharmacy stay. */
export function replaceToken(token: string): void {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem('roshetta_token', token);
}

/** Saves an account-scoped session before the user selects or creates a pharmacy. */
export function saveAccountAuth(payload: { token: string; user: { id: number; language_pref?: string | null } }): void {
  if (typeof window === 'undefined') return;
  if (payload.user.language_pref === 'ar' || payload.user.language_pref === 'en') {
    persistLanguage(payload.user.language_pref);
  }
  sessionStorage.setItem('roshetta_token', payload.token);
  sessionStorage.setItem('roshetta_user', JSON.stringify(payload.user));
  sessionStorage.setItem('roshetta_role', 'account');
  sessionStorage.removeItem('roshetta_pharmacy');
  sessionStorage.setItem('roshetta_auth_context', JSON.stringify({
    userId: payload.user.id,
    pharmacyId: null,
    role: 'account',
  }));
}

/** Saves a full login response to sessionStorage. */
export function saveAuth(payload: {
  token: string;
  user: object;
  role: string;
  pharmacy: object;
}): void {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem('roshetta_token', payload.token);
  sessionStorage.setItem('roshetta_user', JSON.stringify(payload.user));
  sessionStorage.setItem('roshetta_role', payload.role);
  sessionStorage.setItem('roshetta_pharmacy', JSON.stringify(payload.pharmacy));
  const pharmacyData = payload.pharmacy as { id?: number };
  const userData = payload.user as { id?: number };
  sessionStorage.setItem('roshetta_auth_context', JSON.stringify({
    userId: userData.id,
    pharmacyId: pharmacyData.id,
    role: payload.role,
  }));
}