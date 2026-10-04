// web/src/app/pharmacies/[id]/members/[userId]/page.tsx (route: /pharmacies/[id]/members/[userId] — shifts, compensation, work summary)
'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { getStaffCompensation, getStaffList, getStaffSchedule, getStaffWorkSummary, replaceStaffSchedule, addStaffCompensation } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { roleLabel } from '@/lib/roleLabel';
import { localeOf } from '@/lib/languages';
import type { PharmacyStaffMember, StaffCompensationRecord, StaffPayType, StaffShiftInput, StaffShiftRecord, StaffWorkSummary } from '@/types';

// Index 0 is Monday, as the server numbers shift days.
const DAY_KEYS = ['sd_day_mon', 'sd_day_tue', 'sd_day_wed', 'sd_day_thu', 'sd_day_fri', 'sd_day_sat', 'sd_day_sun'] as const;

export default function StaffDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const { t, lang, dir } = useLanguage();
  // The server sends pay_type as a fixed word; an unknown word is shown as sent rather than hidden.
  const payTypeLabels: Record<string, string> = {
    monthly: t('sd_monthly'),
    hourly: t('sd_hourly'),
    daily: t('sd_daily'),
    commission: t('sd_commission'),
    other: t('sd_other'),
  };
  const payTypeLabel = (type: string) => payTypeLabels[type] ?? type;
  const pharmacyId = Number(params.id);
  const userId = Number(params.userId);

  const [member, setMember] = useState<PharmacyStaffMember | null>(null);
  const [summary, setSummary] = useState<StaffWorkSummary | null>(null);
  const [summaryDays, setSummaryDays] = useState(30);
  const [scheduleHistory, setScheduleHistory] = useState<StaffShiftRecord[]>([]);
  const [shifts, setShifts] = useState<StaffShiftInput[]>([]);
  const [compensation, setCompensation] = useState<StaffCompensationRecord[]>([]);
  const [payType, setPayType] = useState<StaffPayType>('monthly');
  const [payAmount, setPayAmount] = useState('');
  const [payDetails, setPayDetails] = useState('');
  const [payEffectiveFrom, setPayEffectiveFrom] = useState('');
  const [scheduleEffectiveFrom, setScheduleEffectiveFrom] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    if (!Number.isInteger(pharmacyId) || !Number.isInteger(userId)) {
      router.replace('/pharmacies');
      return;
    }
    void loadPage();
  }, [pharmacyId, userId]);

  async function loadPage() {
    setLoading(true);
    setError('');
    try {
      const [members, schedule, pay] = await Promise.all([
        getStaffList(), getStaffSchedule(pharmacyId, userId), getStaffCompensation(pharmacyId, userId),
      ]);
      setMember(members.find((item) => item.id === userId) ?? null);
      setScheduleHistory(schedule);
      setShifts(schedule.filter((item) => item.is_active && !item.effective_until).map((item) => ({
        day_of_week: item.day_of_week,
        start_time: item.start_time,
        end_time: item.end_time,
        timezone: item.timezone,
        effective_from: item.effective_from,
      })));
      setCompensation(pay);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('sd_could_not_load_staff_details'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!isAuthenticated() || !Number.isInteger(userId) || !Number.isInteger(pharmacyId)) return;
    void getStaffWorkSummary(pharmacyId, userId, summaryDays).then(setSummary).catch((cause) => setError(cause instanceof Error ? cause.message : t('sd_summary_error')));
  }, [pharmacyId, userId, summaryDays]);

  function toggleDay(day: number, enabled: boolean) {
    setShifts((current) => enabled
      ? [...current, { day_of_week: day, start_time: '14:00', end_time: '18:00', timezone: 'Africa/Cairo' }].sort((a, b) => a.day_of_week - b.day_of_week)
      : current.filter((shift) => shift.day_of_week !== day));
  }

  function updateShift(day: number, key: 'start_time' | 'end_time', value: string) {
    setShifts((current) => current.map((shift) => shift.day_of_week === day ? { ...shift, [key]: value } : shift));
  }

  async function saveSchedule() {
    setSaving(true);
    setError('');
    try {
      await replaceStaffSchedule(pharmacyId, userId, shifts.map((shift) => ({ ...shift, effective_from: scheduleEffectiveFrom || undefined })));
      setNotice(t('sd_weekly_schedule_saved'));
      setScheduleEffectiveFrom('');
      await loadPage();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('sd_could_not_save_schedule'));
    } finally {
      setSaving(false);
    }
  }

  async function saveCompensation() {
    setSaving(true);
    setError('');
    try {
      await addStaffCompensation(pharmacyId, userId, {
        pay_type: payType,
        amount: payAmount ? Number(payAmount) : null,
        currency: 'EGP',
        details: payDetails.trim() || null,
        effective_from: payEffectiveFrom || null,
      });
      setNotice(t('sd_compensation_terms_saved'));
      setPayAmount('');
      setPayDetails('');
      setPayEffectiveFrom('');
      setCompensation(await getStaffCompensation(pharmacyId, userId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('sd_could_not_save_compensation'));
    } finally {
      setSaving(false);
    }
  }

  const activeCompensation = compensation.find((row) => row.is_active && !row.effective_until);

  return (
    <div className="min-h-screen bg-surface text-on-surface">
      <TopHeader pharmacyName={member?.name || t('sd_staff_details')} subtitle={t('sd_schedule_compensation_activity')} showBack />
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 pb-12 pt-20" dir={dir}>
        <button type="button" onClick={() => router.back()} className="self-start rounded-lg bg-surface-container px-4 py-2 font-label-md text-label-md">{t('sd_back_team')}</button>
        {error && <p role="alert" className="rounded-xl bg-error-container p-3 text-sm text-on-error-container">{error}</p>}
        {notice && <p role="status" className="rounded-xl bg-primary-fixed p-3 text-sm text-on-primary-fixed-variant">{notice}</p>}
        {loading ? <p className="py-8 text-center text-on-surface-variant">{t('sd_loading')}</p> : !member ? <p className="rounded-xl bg-surface-container-low p-4">{t('sd_no_active_team_member_found')}</p> : <>
          <section className="rounded-2xl bg-surface-container-lowest p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div><h1 className="font-headline-sm text-headline-sm font-bold">{member.name}</h1><p className="mt-1 text-on-surface-variant" dir="ltr">{member.phone} · {roleLabel(t, member.role, member.role_name)}</p></div>
              <label className="flex items-center gap-2 text-sm">
                <span>{t('sd_period')}</span>
                <select value={summaryDays} onChange={(event) => setSummaryDays(Number(event.target.value))} className="h-10 rounded-lg bg-surface-container px-2">
                  <option value={1}>{t('hm_today')}</option><option value={7}>{t('sd_period_7_days')}</option><option value={30}>{t('sd_period_30_days')}</option>
                </select>
              </label>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label={t('sd_sales')} value={summary?.sales_count} />
              <Metric label={t('sd_sales_amount')} value={summary?.sales_amount} currency />
              <Metric label={t('sd_units_sold')} value={summary?.sold_quantity} />
              <Metric label={t('sd_units_restocked')} value={summary?.restocked_quantity} />
            </div>
          </section>

          {member.role !== 'owner' && <section className="rounded-2xl bg-surface-container-lowest p-5 shadow-sm">
            <h2 className="font-headline-sm text-headline-sm font-bold">{t('sd_weekly_shift_schedule')}</h2>
            <p className="mt-1 text-sm text-on-surface-variant">{t('sd_pharmacy_local_time_cairo')}</p>
            <label className="mt-3 flex max-w-xs flex-col gap-1 text-sm">
              <span>{t('sd_schedule_effective_from_optional')}</span>
              <input type="date" value={scheduleEffectiveFrom} onChange={(event) => setScheduleEffectiveFrom(event.target.value)} className="h-10 rounded-lg bg-surface-container-low px-3" />
            </label>
            <div className="mt-4 flex flex-col gap-2">
              {DAY_KEYS.map((dayKey, dayIndex) => {
                const shift = shifts.find((item) => item.day_of_week === dayIndex);
                return <div key={dayIndex} className="grid grid-cols-[1fr_auto_auto] items-center gap-2 rounded-lg bg-surface-container-low p-2">
                  <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={!!shift} onChange={(event) => toggleDay(dayIndex, event.target.checked)} />{t(dayKey)}</label>
                  <input aria-label={`${t(dayKey)} ${t('sd_start')}`} type="time" disabled={!shift} value={shift?.start_time || '14:00'} onChange={(event) => updateShift(dayIndex, 'start_time', event.target.value)} className="h-10 w-28 rounded-lg bg-surface-container-lowest px-2 disabled:opacity-50" />
                  <input aria-label={`${t(dayKey)} ${t('sd_end')}`} type="time" disabled={!shift} value={shift?.end_time || '18:00'} onChange={(event) => updateShift(dayIndex, 'end_time', event.target.value)} className="h-10 w-28 rounded-lg bg-surface-container-lowest px-2 disabled:opacity-50" />
                </div>;
              })}
            </div>
            <button type="button" disabled={saving} onClick={() => void saveSchedule()} className="mt-4 h-11 rounded-lg bg-primary px-4 font-label-md text-label-md font-bold text-on-primary disabled:opacity-60">{t('sd_save_schedule')}</button>
            {scheduleHistory.length > 0 && <details className="mt-4"><summary className="cursor-pointer font-label-md text-label-md">{t('sd_schedule_history')}</summary><ul className="mt-2 space-y-1 text-sm text-on-surface-variant">{scheduleHistory.map((shift) => <li key={shift.id}>{DAY_KEYS[shift.day_of_week] ? t(DAY_KEYS[shift.day_of_week]) : ''}: {shift.start_time}–{shift.end_time} · {shift.effective_from || '—'}{shift.effective_until ? ` – ${shift.effective_until}` : ''}</li>)}</ul></details>}
          </section>}

          {member.role !== 'owner' && <section className="rounded-2xl bg-surface-container-lowest p-5 shadow-sm">
            <h2 className="font-headline-sm text-headline-sm font-bold">{t('sd_compensation_terms')}</h2>
            {activeCompensation && <div className="mt-3 rounded-lg bg-surface-container-low p-3 text-sm">
              <strong>{payTypeLabel(activeCompensation.pay_type)}</strong> · {activeCompensation.amount == null ? t('sd_unspecified_amount') : `${activeCompensation.amount.toLocaleString(localeOf(lang))} ${activeCompensation.currency}`}
              {activeCompensation.details && <p className="mt-1 text-on-surface-variant">{activeCompensation.details}</p>}
            </div>}
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-sm"><span>{t('sd_pay_type')}</span><select value={payType} onChange={(event) => setPayType(event.target.value as StaffPayType)} className="h-10 rounded-lg bg-surface-container-low px-3"><option value="monthly">{t('sd_monthly')}</option><option value="hourly">{t('sd_hourly')}</option><option value="daily">{t('sd_daily')}</option><option value="commission">{t('sd_commission')}</option><option value="other">{t('sd_other')}</option></select></label>
              <label className="flex flex-col gap-1 text-sm"><span>{t('sd_amount_egp')}</span><input type="number" min="0" step="0.01" value={payAmount} onChange={(event) => setPayAmount(event.target.value)} className="h-10 rounded-lg bg-surface-container-low px-3" /></label>
              <label className="flex flex-col gap-1 text-sm"><span>{t('sd_effective_date_optional')}</span><input type="date" value={payEffectiveFrom} onChange={(event) => setPayEffectiveFrom(event.target.value)} className="h-10 rounded-lg bg-surface-container-low px-3" /></label>
              <label className="flex flex-col gap-1 text-sm"><span>{t('sd_details')}</span><input maxLength={1000} value={payDetails} onChange={(event) => setPayDetails(event.target.value)} className="h-10 rounded-lg bg-surface-container-low px-3" /></label>
            </div>
            <button type="button" disabled={saving} onClick={() => void saveCompensation()} className="mt-4 h-11 rounded-lg bg-primary px-4 font-label-md text-label-md font-bold text-on-primary disabled:opacity-60">{t('sd_save_new_terms')}</button>
            {compensation.length > 1 && <details className="mt-4"><summary className="cursor-pointer font-label-md text-label-md">{t('sd_compensation_history')}</summary><ul className="mt-2 space-y-1 text-sm text-on-surface-variant">{compensation.map((row) => <li key={row.id}>{payTypeLabel(row.pay_type)} · {row.amount == null ? '—' : `${row.amount} ${row.currency}`} · {row.effective_from || '—'}{row.effective_until ? ` – ${row.effective_until}` : ''}</li>)}</ul></details>}
          </section>}
        </>}
      </main>
    </div>
  );
}

function Metric({ label, value, currency = false }: { label: string; value?: number; currency?: boolean }) {
  const { t, lang } = useLanguage();
  return <div className="rounded-xl bg-surface-container-low p-3"><p className="text-xs text-on-surface-variant">{label}</p><p className="mt-1 font-stat-numeric font-bold">{value == null ? '—' : `${value.toLocaleString(localeOf(lang))}${currency ? ` ${t('currency')}` : ''}`}</p></div>;
}