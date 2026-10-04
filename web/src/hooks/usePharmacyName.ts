'use client';

import { useEffect, useState } from 'react';
import { getPharmacyProfile } from '@/lib/api';

/** Fetch the name for the currently selected, authenticated pharmacy context. */
export function usePharmacyName(): string | undefined {
  const [name, setName] = useState<string>();

  useEffect(() => {
    let active = true;
    getPharmacyProfile()
      .then((profile) => {
        if (active) setName(profile.pharmacy_name || undefined);
      })
      .catch(() => {
        if (active) setName(undefined);
      });
    return () => { active = false; };
  }, []);

  return name;
}
