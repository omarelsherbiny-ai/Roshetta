// web/src/lib/roleLabel.ts (new — translated display label for a member's role)
// The server sends role = owner | pharmacist | cashier | viewer | custom, and role_name = the custom
// role's name, or the same raw word for built-in roles. Built-in words are translated here; a custom
// role's own name is always shown as typed. No new locale keys: it reuses existing ones.

import type { Dictionary } from './languages';

const BUILT_IN_KEYS: Record<string, keyof Dictionary> = {
  owner: 'hm_role_owner',
  pharmacist: 'mb_role_pharmacist',
  cashier: 'cashier',
  viewer: 'mb_role_viewer',
};

export function roleLabel(
  t: (key: keyof Dictionary) => string,
  role: string | null | undefined,
  roleName: string | null | undefined,
): string {
  // A custom role is identified by role === 'custom' (members, invitations): show its name untouched.
  if (role === 'custom') return roleName || role;
  // When only role_name is known (the /pharmacies list) it is matched against the built-in words.
  const word = role && role !== 'custom' ? role : roleName;
  const key = word ? BUILT_IN_KEYS[word] : undefined;
  if (key) return t(key);
  return roleName || role || '';
}