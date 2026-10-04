// web/src/lib/utils.ts (shared helpers: class names, EGP and date formatting by language code, Eastern Arabic numerals)
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { DEFAULT_LANGUAGE, localeOf } from "@/lib/languages";
import { translations } from "@/lib/i18n";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// `locale` is a language code from the registry (any language, not only ar and en).
// The number format comes from the registry; the money unit from the language's own dictionary.
export function formatEGP(amount: number, locale: string = DEFAULT_LANGUAGE): string {
  const formatted = new Intl.NumberFormat(localeOf(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);

  const unit = (translations as Record<string, { currency: string }>)[locale]?.currency ?? 'EGP';
  return `${formatted} ${unit}`;
}

export function toEasternArabicNumerals(numStr: string | number): string {
  const digitsMap: Record<string, string> = {
    '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
    '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩',
  };
  return String(numStr).replace(/[0-9]/g, (digit) => digitsMap[digit] || digit);
}

export function formatTimestamp(dateIso: string, locale: string = DEFAULT_LANGUAGE): string {
  try {
    const date = new Date(dateIso);
    return new Intl.DateTimeFormat(localeOf(locale), {
      hour: 'numeric',
      minute: 'numeric',
      hour12: true,
    }).format(date);
  } catch {
    return dateIso;
  }
}

export function formatDateTime(dateIso: string | null | undefined, locale: string = DEFAULT_LANGUAGE): string {
  if (!dateIso) return '—';
  const date = new Date(dateIso);
  if (Number.isNaN(date.getTime())) return dateIso;
  return new Intl.DateTimeFormat(localeOf(locale), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Africa/Cairo',
  }).format(date);
}