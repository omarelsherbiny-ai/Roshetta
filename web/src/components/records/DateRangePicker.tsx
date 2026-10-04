// web/src/components/records/DateRangePicker.tsx (date range picker: trigger, presets, calendar popover and mobile sheet)
'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useLanguage } from '@/lib/i18n';
import { localeOf, weekStartOf } from '@/lib/languages';
import {
  addMonths, cairoToday, daysInclusive, monthGrid, parseYmd, presetRange,
  type PresetId, type YearMonth, type Ymd,
} from '@/lib/dateRange';

interface DateRangePickerProps {
  start: Ymd;
  end: Ymd;
  onApply: (start: Ymd, end: Ymd) => void;
}

const PRESETS = [
  { id: 'today', labelKey: 'hm_today' },
  { id: 'yesterday', labelKey: 'dr_preset_yesterday' },
  { id: 'last7', labelKey: 'dr_preset_last7' },
  { id: 'thisMonth', labelKey: 'dr_preset_thismonth' },
  { id: 'lastMonth', labelKey: 'dr_preset_lastmonth' },
] as const;

export function DateRangePicker({ start, end, onApply }: DateRangePickerProps) {
  const { t, lang, dir } = useLanguage();
  const locale = localeOf(lang);
  const weekStart = weekStartOf(lang);

  const [open, setOpen] = useState(false);
  const [today, setToday] = useState<Ymd>(() => cairoToday());
  const [draftStart, setDraftStart] = useState<Ymd | null>(start);
  const [draftEnd, setDraftEnd] = useState<Ymd | null>(end);
  const [invalidEnd, setInvalidEnd] = useState(false);
  const [view, setView] = useState<YearMonth>(() => ({ y: parseYmd(end).y, m: parseYmd(end).m }));
  const [twoMonths, setTwoMonths] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const query = window.matchMedia('(min-width: 768px)');
    const update = () => setTwoMonths(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  const todayYm = { y: parseYmd(today).y, m: parseYmd(today).m };
  const maxView = twoMonths ? addMonths(todayYm, -1) : todayYm; // last month the grid may start on
  const shown = view.y * 12 + view.m > maxView.y * 12 + maxView.m ? maxView : view;
  const months = twoMonths ? [shown, addMonths(shown, 1)] : [shown];
  const atLatest = shown.y * 12 + shown.m >= maxView.y * 12 + maxView.m;

  const fmtDay = (value: Ymd) => {
    const { y, m, d } = parseYmd(value);
    return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
      .format(new Date(Date.UTC(y, m - 1, d)));
  };
  const fmtRange = (a: Ymd, b: Ymd) => (a === b ? fmtDay(a) : `${fmtDay(a)} – ${fmtDay(b)}`);
  const fmtMonth = (ym: YearMonth) =>
    new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric', timeZone: 'UTC' })
      .format(new Date(Date.UTC(ym.y, ym.m - 1, 1)));
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(locale, { weekday: 'short', timeZone: 'UTC' })
      .format(new Date(Date.UTC(2023, 0, 1 + ((weekStart + i) % 7)))));
  // Day counts: separate texts for one, two, three to ten, and more (Arabic needs all four).
  const fmtDays = (n: number) => {
    if (n === 1) return t('dr_day_one');
    if (n === 2) return t('dr_day_two');
    return t(n <= 10 ? 'dr_days_few' : 'dr_days_many').replace('{count}', n.toLocaleString(locale));
  };

  const openPicker = () => {
    setToday(cairoToday());
    setDraftStart(start);
    setDraftEnd(end);
    setInvalidEnd(false);
    const endMonth = { y: parseYmd(end).y, m: parseYmd(end).m };
    setView(addMonths(endMonth, twoMonths ? -1 : 0));
    setOpen(true);
  };

  const closePicker = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const pickDay = (day: Ymd) => {
    if (day > today) return;
    if (draftStart && !draftEnd) {
      if (day < draftStart) { setInvalidEnd(true); return; }
      setDraftEnd(day);
      setInvalidEnd(false);
      return;
    }
    setDraftStart(day);
    setDraftEnd(null);
    setInvalidEnd(false);
  };

  const resetToToday = () => {
    setDraftStart(today);
    setDraftEnd(today);
    setInvalidEnd(false);
    setView(addMonths(todayYm, twoMonths ? -1 : 0));
  };

  const apply = () => {
    if (!draftStart || !draftEnd) return;
    onApply(draftStart, draftEnd);
    closePicker();
  };

  const applyPreset = (id: PresetId) => {
    const [presetStart, presetEnd] = presetRange(id, cairoToday());
    onApply(presetStart, presetEnd);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') { event.stopPropagation(); closePicker(); return; }
    if (event.key !== 'Tab') return;
    const nodes = dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled])');
    if (!nodes || nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === dialogRef.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const renderMonth = (ym: YearMonth) => (
    <div key={`${ym.y}-${ym.m}`} className="min-w-0 flex-1">
      <div className="mb-2 text-center font-label-lg text-label-lg text-on-surface">{fmtMonth(ym)}</div>
      <div className="grid grid-cols-7 py-1 text-center font-label-sm text-label-sm text-on-surface-variant">
        {weekdays.map((name, i) => <span key={i}>{name}</span>)}
      </div>
      <div className="grid grid-cols-7 gap-y-1">
        {monthGrid(ym, weekStart).map((day, idx) => {
          if (!day) return <span key={`blank-${idx}`} />;
          const future = day > today;
          const isStart = day === draftStart;
          const isEnd = day === draftEnd;
          const hasRange = !!draftStart && !!draftEnd && draftStart !== draftEnd;
          const inRange = hasRange && day >= (draftStart as Ymd) && day <= (draftEnd as Ymd);
          const col = idx % 7;
          const round = `${isStart || col === 0 ? 'rounded-s-full ' : ''}${isEnd || col === 6 ? 'rounded-e-full' : ''}`;
          return (
            <div key={day} className={`flex items-center justify-center ${inRange ? `bg-surface-container ${round}` : ''}`}>
              <button
                type="button"
                disabled={future}
                onClick={() => pickDay(day)}
                aria-label={fmtDay(day)}
                aria-pressed={isStart || isEnd}
                className={`flex h-10 w-10 items-center justify-center rounded-full font-stat-numeric text-[13px] transition-colors ${
                  isStart || isEnd
                    ? 'bg-primary font-bold text-on-primary shadow-sm'
                    : future
                      ? 'cursor-not-allowed text-on-surface-variant opacity-30'
                      : 'text-on-surface hover:bg-surface-container-high'
                }`}
              >
                {parseYmd(day).d.toLocaleString(locale)}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );

  const canApply = !!draftStart && !!draftEnd;

  return (
    <div dir={dir} className="flex flex-col gap-2">
      <div className="relative">
        <button
          ref={triggerRef}
          type="button"
          onClick={openPicker}
          aria-haspopup="dialog"
          aria-expanded={open}
          className="flex min-h-12 w-full items-center justify-between gap-2 rounded-xl bg-surface-container-lowest px-3.5 py-2 text-start shadow-sm transition-transform active:scale-[0.99]"
        >
          <span className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-container text-primary">
              <span className="material-symbols-outlined text-[20px]">calendar_month</span>
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="font-label-sm text-label-sm text-on-surface-variant">{t('dr_period')}</span>
              <span className="truncate font-label-lg text-label-lg text-on-surface">{fmtRange(start, end)}</span>
            </span>
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <span className="rounded bg-primary-fixed px-2 py-0.5 font-label-sm text-label-sm font-bold text-primary">
              {fmtDays(daysInclusive(start, end))}
            </span>
            <span className="material-symbols-outlined text-[20px] text-on-surface-variant">expand_more</span>
          </span>
        </button>

        {open && (
          <>
            <div className="fixed inset-0 z-[60] bg-on-surface/40 md:bg-transparent" onClick={closePicker} aria-hidden="true" />
            <div
              ref={dialogRef}
              role="dialog"
              aria-modal="true"
              aria-label={t('dr_select_date_range')}
              tabIndex={-1}
              onKeyDown={onKeyDown}
              className="fixed inset-x-0 bottom-0 z-[70] max-h-[90vh] overflow-y-auto rounded-t-3xl bg-surface-container-lowest px-4 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-xl outline-none md:absolute md:inset-x-auto md:bottom-auto md:start-0 md:top-full md:mt-2 md:w-[680px] md:max-w-[calc(100vw-2rem)] md:rounded-2xl md:p-5"
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="font-headline-sm text-headline-sm text-on-surface">{t('dr_select_date_range')}</h3>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">{t('dr_cairo_time')}</p>
                </div>
                <button
                  type="button"
                  onClick={closePicker}
                  aria-label={t('cat_close')}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-container"
                >
                  <span className="material-symbols-outlined text-[22px]">close</span>
                </button>
              </div>

              <div className="mb-3 flex items-center justify-between gap-2 rounded-xl bg-surface-container px-3.5 py-2.5 text-on-surface">
                <span className="min-w-0 truncate font-label-md text-label-md">
                  {draftStart && draftEnd
                    ? fmtRange(draftStart, draftEnd)
                    : draftStart
                      ? `${fmtDay(draftStart)} – ${t('dr_pick_end_date')}`
                      : t('dr_pick_start_date')}
                </span>
                {draftStart && draftEnd && (
                  <span className="shrink-0 rounded-full bg-primary px-2 py-0.5 font-label-sm text-label-sm font-bold text-on-primary">
                    {fmtDays(daysInclusive(draftStart, draftEnd))}
                  </span>
                )}
              </div>

              {invalidEnd && (
                <div role="alert" className="mb-3 flex items-center gap-2 rounded-xl bg-error-container px-3 py-2 font-label-sm text-label-sm text-error">
                  <span className="material-symbols-outlined text-[18px]">error</span>
                  <span>{t('dr_end_date_cannot_be_earlier')}</span>
                </div>
              )}

              <div className="mb-2 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setView(addMonths(shown, -1))}
                  aria-label={t('dr_previous_month')}
                  className="flex h-10 w-10 items-center justify-center rounded-full text-on-surface hover:bg-surface-container"
                >
                  <span className="material-symbols-outlined text-[22px] rtl:rotate-180">chevron_left</span>
                </button>
                <button
                  type="button"
                  disabled={atLatest}
                  onClick={() => setView(addMonths(shown, 1))}
                  aria-label={t('dr_next_month')}
                  className="flex h-10 w-10 items-center justify-center rounded-full text-on-surface hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <span className="material-symbols-outlined text-[22px] rtl:rotate-180">chevron_right</span>
                </button>
              </div>

              <div className="flex gap-6">{months.map(renderMonth)}</div>

              <div className="flex items-center justify-between gap-2 pt-4">
                <button
                  type="button"
                  onClick={resetToToday}
                  className="min-h-11 px-2 font-label-md text-label-md text-primary"
                >
                  {t('dr_reset_today')}
                </button>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={closePicker}
                    className="min-h-11 rounded-xl px-4 font-label-md text-label-md text-on-surface-variant hover:bg-surface-container"
                  >
                    {t('cancel')}
                  </button>
                  <button
                    type="button"
                    onClick={apply}
                    disabled={!canApply}
                    className="min-h-12 rounded-xl bg-primary px-5 font-label-lg text-label-lg text-on-primary shadow-sm hover:bg-primary-container disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {t('dr_apply')}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="no-scrollbar flex items-center gap-1.5 overflow-x-auto pb-1">
        {PRESETS.map((preset) => {
          const [presetStart, presetEnd] = presetRange(preset.id, today);
          const active = presetStart === start && presetEnd === end;
          return (
            <button
              key={preset.id}
              type="button"
              onClick={() => applyPreset(preset.id)}
              aria-pressed={active}
              className={`shrink-0 rounded-full px-3.5 py-1.5 font-label-sm text-label-sm transition-colors ${
                active
                  ? 'bg-primary font-bold text-on-primary shadow-sm'
                  : 'bg-surface-container text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {t(preset.labelKey)}
            </button>
          );
        })}
      </div>
    </div>
  );
}