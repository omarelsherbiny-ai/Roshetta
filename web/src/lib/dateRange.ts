// Calendar-date helpers for the Records date range picker.
// Dates are plain 'YYYY-MM-DD' strings (the format the ledger API expects) and
// all arithmetic runs in UTC so the browser's own timezone never shifts a day.

export type Ymd = string;
export interface YearMonth { y: number; m: number }
export type PresetId = 'today' | 'yesterday' | 'last7' | 'thisMonth' | 'lastMonth';

const pad = (n: number) => String(n).padStart(2, '0');

export function toYmd(y: number, m: number, d: number): Ymd {
  return `${y}-${pad(m)}-${pad(d)}`;
}

export function parseYmd(value: Ymd): { y: number; m: number; d: number } {
  const [y, m, d] = value.split('-').map(Number);
  return { y, m, d };
}

/** Today's calendar date in Cairo, the business timezone used by the backend. */
export function cairoToday(now: Date = new Date()): Ymd {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Africa/Cairo', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = (type: string) => parts.find((value) => value.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export function addDays(value: Ymd, days: number): Ymd {
  const { y, m, d } = parseYmd(value);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  return toYmd(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
}

/** Number of calendar days from start to end, both included. */
export function daysInclusive(start: Ymd, end: Ymd): number {
  const a = parseYmd(start);
  const b = parseYmd(end);
  return Math.round((Date.UTC(b.y, b.m - 1, b.d) - Date.UTC(a.y, a.m - 1, a.d)) / 86400000) + 1;
}

export function addMonths(ym: YearMonth, delta: number): YearMonth {
  const index = ym.y * 12 + (ym.m - 1) + delta;
  return { y: Math.floor(index / 12), m: (index % 12) + 1 };
}

export function daysInMonth(ym: YearMonth): number {
  return new Date(Date.UTC(ym.y, ym.m, 0)).getUTCDate();
}

/** Cells for one month: leading nulls pad to the first weekday (0=Sun ... 6=Sat). */
export function monthGrid(ym: YearMonth, weekStart: number): (Ymd | null)[] {
  const firstWeekday = new Date(Date.UTC(ym.y, ym.m - 1, 1)).getUTCDay();
  const cells: (Ymd | null)[] = Array((firstWeekday - weekStart + 7) % 7).fill(null);
  for (let d = 1; d <= daysInMonth(ym); d += 1) cells.push(toYmd(ym.y, ym.m, d));
  return cells;
}

export function presetRange(id: PresetId, today: Ymd): [Ymd, Ymd] {
  const { y, m } = parseYmd(today);
  switch (id) {
    case 'today': return [today, today];
    case 'yesterday': { const day = addDays(today, -1); return [day, day]; }
    case 'last7': return [addDays(today, -6), today];
    case 'thisMonth': return [toYmd(y, m, 1), today];
    case 'lastMonth': {
      const prev = addMonths({ y, m }, -1);
      return [toYmd(prev.y, prev.m, 1), toYmd(prev.y, prev.m, daysInMonth(prev))];
    }
  }
}