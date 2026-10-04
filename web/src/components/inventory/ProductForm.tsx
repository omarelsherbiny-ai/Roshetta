// web/src/components/inventory/ProductForm.tsx (reusable product form: duplicate scan banner, category pills, margin calculator)
'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { useLanguage } from '@/lib/i18n';
import { getInventoryCategories, getPharmacyProfile, matchProduct } from '@/lib/api';
import { InventoryItemSchema } from '@/types';

export interface ProductFormData {
  id?: number;
  name_ar: string;
  name_en: string;
  barcode: string;
  active_ingredient: string;
  category: string;
  expiry_date: string;
  unit_buy_price: number;
  unit_sell_price: number;
  stock_qty: number;
  min_threshold: number;
  batch_number?: string;
}

interface ProductFormProps {
  initialData?: Partial<ProductFormData>;
  isEdit?: boolean;
  itemId?: number;
  onSubmit: (data: ProductFormData) => Promise<void>;
}

type DupField = { key: string; label: string; value: string; ltr?: boolean; strong?: boolean };

// Number fields are kept as the raw typed text so they can be cleared and typed naturally.
// The numeric value is derived: empty, invalid, or negative text counts as 0.
const toNum = (text: string): number => {
  const n = parseFloat(text);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

export function ProductForm({ initialData, isEdit = false, itemId, onSubmit }: ProductFormProps) {
  const router = useRouter();
  const { dir, t } = useLanguage();

  // Form states
  const [nameAr, setNameAr] = useState(initialData?.name_ar || '');
  const [nameEn, setNameEn] = useState(initialData?.name_en || '');
  const [activeIngredient, setActiveIngredient] = useState(initialData?.active_ingredient || '');
  const [category, setCategory] = useState(initialData?.category || '');
  const [categories, setCategories] = useState<string[]>([]);
  const [barcode, setBarcode] = useState(initialData?.barcode || '');
  const [expiryDate, setExpiryDate] = useState(initialData?.expiry_date || '');
  const [batchNumber, setBatchNumber] = useState(initialData?.batch_number || '');
  
  // Financial & Inventory
  const [buyPriceInput, setBuyPriceInput] = useState<string>(
    initialData?.unit_buy_price != null ? String(initialData.unit_buy_price) : ''
  );
  const [sellPriceInput, setSellPriceInput] = useState<string>(
    initialData?.unit_sell_price != null ? String(initialData.unit_sell_price) : ''
  );
  const [stockQty, setStockQty] = useState<number>(initialData?.stock_qty ?? 0);
  const [minThresholdInput, setMinThresholdInput] = useState<string>(
    String(initialData?.min_threshold ?? 5)
  );
  const buyPrice = toNum(buyPriceInput);
  const sellPrice = toNum(sellPriceInput);
  const minThreshold = toNum(minThresholdInput);

  // UI States
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSaved, setIsSaved] = useState(false); // keeps the button locked until the redirect
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [pharmacyName, setPharmacyName] = useState('');
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Duplicate scanner state
  type ScanState = 'idle' | 'scanning' | 'verified' | 'warning' | 'failed';
  const [scanState, setScanState] = useState<ScanState>('idle');
  const [matchedItem, setMatchedItem] = useState<InventoryItemSchema | null>(null);
  const scanTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scanSeqRef = useRef(0); // only the newest request may update the banner
  const lastQueryRef = useRef('');

  const runDuplicateScan = useCallback((query: string, delayMs: number) => {
    if (isEdit) return; // don't scan on edit page
    if (scanTimerRef.current) clearTimeout(scanTimerRef.current);
    const seq = ++scanSeqRef.current;
    const trimmed = query.trim();
    lastQueryRef.current = trimmed;
    setMatchedItem(null);
    if (trimmed.length < 3) {
      setScanState('idle');
      return;
    }
    setScanState('scanning');
    scanTimerRef.current = setTimeout(async () => {
      try {
        const result = await matchProduct(trimmed);
        if (seq !== scanSeqRef.current) return;
        if (result.found && result.matched_item) {
          setMatchedItem(result.matched_item);
          setScanState('warning');
        } else {
          setScanState('verified');
        }
      } catch {
        if (seq !== scanSeqRef.current) return;
        setScanState('failed');
      }
    }, delayMs);
  }, [isEdit]);

  // Cancel any pending scan when the form unmounts
  useEffect(() => {
    return () => {
      scanSeqRef.current += 1;
      if (scanTimerRef.current) clearTimeout(scanTimerRef.current);
    };
  }, []);

  // Cancel the toast and redirect timers when the form unmounts
  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current);
    };
  }, []);

  useEffect(() => {
    let active = true;
    getPharmacyProfile().then((profile) => {
      if (active && profile.pharmacy_name) setPharmacyName(profile.pharmacy_name);
    }).catch(() => undefined);
    getInventoryCategories().then((values) => {
      if (active) setCategories(values);
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (isEdit) return;
    const params = new URLSearchParams(window.location.search);
    const suggestedName = params.get('name');
    if (suggestedName) {
      setNameAr(suggestedName);
      runDuplicateScan(suggestedName, 0);
    }
    // ?category= prefill (new product only): trimmed, capped at the 40-char category limit.
    // Runs once on mount; the user can still change or clear it afterwards.
    const suggestedCategory = (params.get('category') ?? '').trim().slice(0, 40);
    if (suggestedCategory) {
      setCategory((current) => current || suggestedCategory);
    }
  }, [isEdit, runDuplicateScan]);

  // Live profit calculation
  const unitProfit = sellPrice - buyPrice;
  const profitMarginPercent = buyPrice > 0 ? ((unitProfit / buyPrice) * 100).toFixed(1) : '0';
  const isProfitable = unitProfit >= 0;

  // Real fields of the matched item only; nullable fields are hidden when empty
  const duplicateFields: DupField[] = matchedItem
    ? ([
        matchedItem.barcode
          ? { key: 'barcode', label: t('pf_barcode'), value: matchedItem.barcode, ltr: true }
          : null,
        matchedItem.category
          ? { key: 'category', label: t('pf_category'), value: matchedItem.category }
          : null,
        {
          key: 'stock',
          label: t('pf_current_stock'),
          value: `${matchedItem.stock_qty} ${t('pf_packs')}`,
          strong: true,
        },
        {
          key: 'price',
          label: t('pf_selling_price_plain'),
          value: `${Number(matchedItem.unit_sell_price).toFixed(2)} ${t('currency')}`,
        },
        matchedItem.expiry_date
          ? { key: 'expiry', label: t('pf_expiry_date'), value: matchedItem.expiry_date, ltr: true }
          : null,
      ] as Array<DupField | null>).filter((f): f is DupField => f !== null)
    : [];

  const showToast = (msg: string) => {
    setToastMsg(msg);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToastMsg(null), 3500);
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isSubmitting || isSaved) return;
    setErrorMsg(null);

    if (!nameAr.trim()) {
      setErrorMsg(t('pf_err_name_ar'));
      return;
    }
    if (!nameEn.trim()) {
      setErrorMsg(t('pf_err_name_en'));
      return;
    }
    if (sellPrice <= 0) {
      setErrorMsg(t('pf_err_sell'));
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit({
        id: itemId,
        name_ar: nameAr.trim(),
        name_en: nameEn.trim(),
        active_ingredient: activeIngredient.trim(),
        category,
        barcode: barcode.trim(),
        expiry_date: expiryDate,
        unit_buy_price: buyPrice,
        unit_sell_price: sellPrice,
        stock_qty: stockQty,
        min_threshold: minThreshold,
        batch_number: batchNumber.trim() || undefined,
      });
      setIsSaved(true);
      showToast((isEdit ? t('pf_toast_updated') : t('pf_toast_added')).replace('{name}', nameAr));
      redirectTimerRef.current = setTimeout(() => router.push('/inventory'), 1200);
    } catch (err: any) {
      setErrorMsg(err.message || t('pf_err_save'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-surface text-on-surface font-body-md text-body-md flex flex-col min-h-screen selection:bg-primary-fixed selection:text-on-primary-fixed" dir={dir}>
      {/* Top Header */}
      <TopHeader
        pharmacyName={pharmacyName}
        subtitle={isEdit ? t('pf_edit_product') : t('pf_add_product')}
        showBack={true}
      />

      <main className="flex flex-col relative w-full pt-16 bg-surface min-h-screen">
        <div className="flex flex-col w-full pb-32">
          {/* Status & Context Banner */}
          <div className="px-margin pt-space-md pb-space-sm flex items-center justify-between">
            <div className="flex items-center gap-space-xs">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-label-sm font-label-sm bg-primary text-on-primary font-bold">
                {isEdit ? t('pf_edit_product') : t('pf_badge_add')}
              </span>
              <span className="text-body-sm font-body-sm text-on-surface-variant font-medium">
                {isEdit ? `${t('pf_id')}: #${itemId}` : t('pf_new_product')}
              </span>
            </div>
            <div className="flex items-center gap-1 text-primary text-label-sm font-label-sm">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              <span>{t('pf_product_details')}</span>
            </div>
          </div>

          {/* Error Message */}
          {errorMsg && (
            <div className="px-margin mb-3">
              <div className="p-3 bg-error-container text-on-error-container rounded-xl flex items-center gap-2 text-body-sm">
                <span className="material-symbols-outlined text-lg">error</span>
                <span>{errorMsg}</span>
              </div>
            </div>
          )}

          <div className="px-margin flex flex-col gap-space-lg">
            {/* 1. OCR Smart Camera Capture Section */}
            <section className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm border border-outline-variant/30 overflow-hidden relative">
              <div className="flex items-center justify-between mb-space-sm">
                <div className="flex items-center gap-space-xs">
                  <div className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined text-[20px]">document_scanner</span>
                  </div>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                    {t('pf_scan_title')}
                  </h2>
                </div>
                <span className="inline-flex items-center gap-1 bg-surface-container px-2 py-0.5 rounded-full text-label-sm font-label-sm text-primary font-bold">
                  <span className="material-symbols-outlined text-[14px]">edit_note</span>
                  {t('pf_manual_entry')}
                </span>
              </div>

              <div className="w-full min-h-32 rounded-lg bg-surface-container-low flex flex-col items-center justify-center gap-2 p-4 text-center text-on-surface-variant mb-space-sm">
                <span className="material-symbols-outlined text-4xl text-outline">medication</span>
                <span className="text-body-sm font-medium">{t('pf_scan_unavailable')}</span>
              </div>

              <button
                type="button"
                disabled
                aria-disabled="true"
                className="w-full min-h-12 rounded-lg bg-surface-container text-on-surface-variant flex items-center justify-center gap-2 font-label-lg text-label-lg font-bold border border-outline-variant/30 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <span className="material-symbols-outlined text-[20px]">photo_camera</span>
                <span>{t('pf_camera_unavailable')}</span>
              </button>
            </section>

            {/* 2. Basic Drug Information */}
            <section className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm border border-outline-variant/30 flex flex-col gap-space-md">
              <div className="flex items-center gap-space-xs">
                <div className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-primary">
                  <span className="material-symbols-outlined text-[20px]">medication</span>
                </div>
                <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">{t('pf_info_title')}</h2>
              </div>

              {/* Trade Name Arabic */}
              <div className="flex flex-col gap-1.5">
                <label className="font-label-md text-label-md text-on-surface font-semibold" htmlFor="trade-name-ar">
                  {t('pf_name_ar_label')}
                </label>
                <input
                  id="trade-name-ar"
                  type="text"
                  dir="rtl"
                  value={nameAr}
                  onChange={(e) => {
                    setNameAr(e.target.value);
                    runDuplicateScan(e.target.value, 650);
                  }}
                  placeholder={t('pf_name_ar_ph')}
                  className="w-full h-12 px-3.5 bg-surface-container-low rounded-lg text-right text-on-surface font-body-md text-body-md focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent"
                />
              </div>

              {/* Trade Name English */}
              <div className="flex flex-col gap-1.5">
                <label className="font-label-md text-label-md text-on-surface font-semibold" htmlFor="trade-name-en">
                  {t('pf_name_en_label')}
                </label>
                <input
                  id="trade-name-en"
                  type="text"
                  dir="ltr"
                  value={nameEn}
                  onChange={(e) => {
                    setNameEn(e.target.value);
                    runDuplicateScan(e.target.value, 650);
                  }}
                  placeholder={t('pf_name_en_ph')}
                  className="w-full h-12 px-3.5 bg-surface-container-low rounded-lg text-on-surface font-body-md text-body-md text-left focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent font-stat-numeric"
                />
              </div>

              {/* Duplicate check banner (add mode only) */}
              {!isEdit && (
                <div role="status" aria-live="polite" className="transition-all duration-300">
                  {scanState === 'scanning' && (
                    <div className="flex items-center gap-space-sm rounded-lg bg-surface-container px-space-md py-3 text-on-surface">
                      <span className="material-symbols-outlined animate-spin text-[22px] text-primary">progress_activity</span>
                      <span className="font-label-md text-label-md text-primary">
                        {t('pf_dup_checking')}
                      </span>
                    </div>
                  )}

                  {scanState === 'verified' && (
                    <div className="flex items-center gap-space-xs rounded-lg bg-surface-container-high px-space-md py-2.5 text-primary">
                      <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                      <span className="font-label-md text-label-md">
                        {t('pf_dup_none')}
                      </span>
                    </div>
                  )}

                  {scanState === 'failed' && (
                    <div className="flex items-center justify-between gap-space-sm rounded-lg bg-surface-container px-space-md py-2.5 text-on-surface-variant">
                      <div className="flex items-center gap-space-sm">
                        <span className="material-symbols-outlined text-[20px] text-outline">cloud_off</span>
                        <span className="font-label-md text-label-md text-on-surface">
                          {t('pf_dup_failed')}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => runDuplicateScan(lastQueryRef.current, 0)}
                        className="inline-flex min-h-12 shrink-0 items-center gap-1 rounded-lg px-2 font-label-md text-label-md text-primary hover:bg-surface-container-high active:scale-95 transition-all cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-[18px]">refresh</span>
                        <span>{t('retry')}</span>
                      </button>
                    </div>
                  )}

                  {scanState === 'warning' && matchedItem && (
                    <div className="flex flex-col gap-space-sm rounded-xl bg-secondary-fixed p-space-md text-on-secondary-fixed shadow-sm">
                      <div className="flex items-center gap-space-xs">
                        <span className="material-symbols-outlined text-[24px] text-secondary" style={{ fontVariationSettings: "'FILL' 1" }}>error</span>
                        <span className="font-label-lg text-label-lg font-bold">
                          {t('pf_dup_may_exist')}
                        </span>
                      </div>

                      <div className="flex flex-col gap-space-xs rounded-lg bg-surface-container-lowest/80 p-space-sm text-on-surface">
                        <div className="flex flex-wrap items-baseline justify-between gap-x-space-sm border-b border-surface-variant pb-1">
                          <div>
                            <span className="font-headline-sm text-headline-sm text-primary">{matchedItem.name_ar}</span>
                            <span dir="ltr" className="ms-1 font-body-sm text-body-sm text-on-surface-variant">({matchedItem.name_en})</span>
                          </div>
                          <span dir="ltr" className="font-label-sm text-label-sm text-on-surface-variant font-stat-numeric">#{matchedItem.id}</span>
                        </div>
                        <dl className="grid grid-cols-2 gap-x-space-md gap-y-space-xs md:grid-cols-3">
                          {duplicateFields.map((field) => (
                            <div key={field.key} className="flex min-w-0 flex-col">
                              <dt className="font-label-sm text-label-sm text-on-surface-variant">{field.label}</dt>
                              <dd
                                dir={field.ltr ? 'ltr' : undefined}
                                className={`truncate font-label-md text-label-md ${field.strong ? 'text-primary font-bold' : 'text-on-surface'} ${field.ltr ? 'text-start font-stat-numeric' : ''}`}
                              >
                                {field.value}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </div>

                      <div className="flex flex-wrap items-center gap-space-xs">
                        <Link
                          href={`/inventory/${matchedItem.id}/edit`}
                          className="inline-flex min-h-12 items-center gap-1 rounded-lg bg-secondary px-space-md font-label-md text-label-md text-on-secondary shadow-sm transition-all hover:bg-secondary/90 active:scale-[0.98]"
                        >
                          <span className="material-symbols-outlined text-[18px]">open_in_new</span>
                          <span>{t('pf_dup_open')}</span>
                        </Link>
                        <Link
                          href={`/inventory/${matchedItem.id}/restock`}
                          className="inline-flex min-h-12 items-center gap-1 rounded-lg bg-surface-container-lowest px-space-md font-label-md text-label-md text-secondary transition-all hover:bg-surface-container active:scale-[0.98]"
                        >
                          <span className="material-symbols-outlined text-[18px]">add_box</span>
                          <span>{t('pf_dup_restock')}</span>
                        </Link>
                      </div>

                      <div className="flex items-center gap-1 text-on-secondary-fixed-variant">
                        <span className="material-symbols-outlined text-[16px]">info</span>
                        <span className="font-body-sm text-body-sm">
                          {t('pf_dup_ignore')}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Active Ingredient */}
              <div className="flex flex-col gap-1.5">
                <label className="font-label-md text-label-md text-on-surface font-semibold" htmlFor="active-ingredient">
                  {t('pf_active_ingredient')}
                </label>
                <div className="relative">
                  <input
                    id="active-ingredient"
                    type="text"
                    dir="ltr"
                    value={activeIngredient}
                    onChange={(e) => setActiveIngredient(e.target.value)}
                    placeholder={t('pf_active_ingredient_ph')}
                    className="w-full h-12 pr-3.5 pl-10 bg-surface-container-low rounded-lg text-on-surface font-body-md text-body-md text-left focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent"
                  />
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-outline text-[20px]">
                    science
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="font-label-md text-label-md text-on-surface font-semibold">
                  {t('pf_category')}
                </label>
                {/* Category pills from real DB */}
                {categories.length > 0 && (
                  <div className="flex flex-wrap gap-space-xs">
                    {categories.map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        onClick={() => setCategory(category === cat ? '' : cat)}
                        className={`h-8 px-3 rounded-full font-label-md text-label-md active:scale-95 transition-all shadow-sm ${
                          category === cat
                            ? 'bg-primary text-on-primary'
                            : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container hover:text-on-surface'
                        }`}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>
                )}
                {/* Custom category fallback input */}
                <input
                  id="drug-category"
                  type="text"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  maxLength={50}
                  placeholder={t('pf_category_new_ph')}
                  className="w-full h-10 px-3 bg-surface-container-low rounded-lg text-on-surface font-body-md text-body-md focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent"
                />
              </div>
            </section>

            {/* 3. Barcode & Regulatory Details */}
            <section className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm border border-outline-variant/30 flex flex-col gap-space-md">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-space-xs">
                  <div className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined text-[20px]">qr_code_scanner</span>
                  </div>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">{t('pf_barcode')}</h2>
                </div>
                <span className="inline-flex items-center gap-1 text-primary font-label-sm text-label-sm bg-surface-container-low px-2 py-1 rounded-full font-bold">
                  <span className="material-symbols-outlined text-[15px]">verified</span>
                  {t('pf_barcode_checked')}
                </span>
              </div>

              {/* Barcode Number with Scanner Trigger */}
              <div className="flex flex-col gap-1.5">
                <label className="font-label-md text-label-md text-on-surface font-semibold" htmlFor="barcode-val">
                  {t('pf_barcode')}
                </label>
                <div className="flex items-center gap-space-xs">
                  <div className="relative flex-1">
                    <input
                      id="barcode-val"
                      type="text"
                      dir="ltr"
                      value={barcode}
                      onChange={(e) => setBarcode(e.target.value)}
                      placeholder={t('pf_optional')}
                      className="w-full h-12 pr-3.5 pl-10 bg-surface-container-low rounded-lg text-on-surface font-stat-numeric text-[16px] tracking-wider focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent"
                    />
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 material-symbols-outlined text-outline text-[20px]">
                      barcode
                    </span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-space-sm">
                <div className="flex flex-col gap-1.5">
                  <label className="font-label-md text-label-md text-on-surface font-semibold" htmlFor="expiry-date">
                    {t('pf_expiry_label')}
                  </label>
                  <div className="relative">
                    <input
                      id="expiry-date"
                      type="date"
                      dir="ltr"
                      value={expiryDate}
                      onChange={(e) => setExpiryDate(e.target.value)}
                      className="w-full h-12 px-3 bg-surface-container-low rounded-lg text-on-surface font-body-md text-body-md text-center focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent font-stat-numeric"
                    />
                    <span className="absolute left-2.5 top-1/2 -translate-y-1/2 material-symbols-outlined text-outline text-[18px]">
                      event
                    </span>
                  </div>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="font-label-md text-label-md text-on-surface font-semibold" htmlFor="batch-number">
                    {t('pf_batch_number')}
                  </label>
                  <div className="relative">
                    <input
                      id="batch-number"
                      type="text"
                      dir="ltr"
                      value={batchNumber}
                      onChange={(e) => setBatchNumber(e.target.value)}
                      placeholder={t('pf_optional')}
                      className="w-full h-12 px-3.5 bg-surface-container-low rounded-lg text-on-surface font-body-md text-body-md focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent font-stat-numeric uppercase"
                    />
                  </div>
                </div>
              </div>
            </section>

            {/* 4. Pricing & Auto Profit Margin Card */}
            <section className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm border border-outline-variant/30 flex flex-col gap-space-md">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-space-xs">
                  <div className="w-8 h-8 rounded-full bg-secondary-container/20 flex items-center justify-center text-secondary">
                    <span className="material-symbols-outlined text-[20px]">payments</span>
                  </div>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                    {t('pf_pricing')}
                  </h2>
                </div>
                <span className="text-label-sm font-label-sm bg-surface-container text-on-surface-variant px-2.5 py-0.5 rounded-full font-bold">
                    {t('pf_currency_badge')}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-space-sm">
                {/* Buy Price */}
                <div className="flex flex-col gap-1.5">
                  <label className="font-label-md text-label-md text-on-surface-variant font-semibold" htmlFor="buy-price">
                    {t('pf_buy_price')}
                  </label>
                  <div className="relative flex items-center">
                    <input
                      id="buy-price"
                      type="number"
                      inputMode="decimal"
                      min="0"
                      step="0.5"
                      value={buyPriceInput}
                      onChange={(e) => setBuyPriceInput(e.target.value)}
                      placeholder="0.00"
                      className="w-full h-12 ps-10 pe-3.5 bg-surface-container-low rounded-lg text-on-surface font-stat-numeric text-[20px] focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent"
                    />
                    <span className="absolute start-3 font-label-sm text-label-sm text-outline font-bold">{t('currency')}</span>
                  </div>
                </div>

                {/* Sell Price */}
                <div className="flex flex-col gap-1.5">
                  <label className="font-label-md text-label-md text-primary font-bold" htmlFor="sell-price">
                    {t('pf_sell_price')}
                  </label>
                  <div className="relative flex items-center">
                    <input
                      id="sell-price"
                      type="number"
                      inputMode="decimal"
                      min="0"
                      step="0.5"
                      value={sellPriceInput}
                      onChange={(e) => setSellPriceInput(e.target.value)}
                      placeholder="0.00"
                      className="w-full h-12 ps-10 pe-3.5 bg-surface-container-low rounded-lg text-primary font-stat-numeric text-[20px] font-extrabold focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent"
                    />
                    <span className="absolute start-3 font-label-sm text-label-sm text-primary font-bold">{t('currency')}</span>
                  </div>
                </div>
              </div>

              {/* Live Profit Summary Badge */}
              <div className="bg-surface-container-low rounded-lg p-space-sm flex items-center justify-between">
                <div className="flex items-center gap-space-xs">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                    isProfitable ? 'bg-primary-fixed text-on-primary-fixed' : 'bg-tertiary-fixed text-on-tertiary-fixed'
                  }`}>
                    <span className="material-symbols-outlined text-[22px]">
                      {isProfitable ? 'trending_up' : 'trending_down'}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">{t('pf_profit_unit')}</span>
                    <span className={`font-stat-numeric text-[18px] leading-tight font-extrabold ${
                      isProfitable ? 'text-primary' : 'text-tertiary'
                    }`}>
                      {unitProfit >= 0 ? `+${unitProfit.toFixed(2)}` : unitProfit.toFixed(2)} {t('currency')}
                    </span>
                  </div>
                </div>

                <div className="flex flex-col items-end">
                  <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">{t('pf_profit_margin')}</span>
                  <span className={`font-stat-numeric text-[18px] leading-tight font-extrabold ${
                    isProfitable ? 'text-primary' : 'text-tertiary'
                  }`}>
                    {profitMarginPercent}%
                  </span>
                </div>
              </div>
            </section>

            {/* 5. Stock & Inventory Alert */}
            <section className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm border border-outline-variant/30 flex flex-col gap-space-md">
              <div className="flex items-center gap-space-xs">
                <div className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-primary">
                  <span className="material-symbols-outlined text-[20px]">inventory_2</span>
                </div>
                <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">{t('pf_stock')}</h2>
              </div>

              {isEdit ? (
                <div className="flex items-center justify-between rounded-lg bg-surface-container-low px-4 py-3">
                  <span className="font-label-md text-label-md text-on-surface-variant">{t('pf_current_qty')}</span>
                  <span className="font-stat-numeric text-lg font-extrabold text-on-surface">{stockQty} {t('pf_packs')}</span>
                </div>
              ) : (
              <div className="flex flex-col gap-1.5">
                <label className="font-label-md text-label-md text-on-surface font-semibold">
                  {t('pf_current_qty')}
                </label>
                <div className="flex items-center justify-between bg-surface-container-low rounded-lg p-1.5">
                  <button
                    type="button"
                    aria-label={t('pf_decrease')}
                    onClick={() => setStockQty((q) => Math.max(0, q - 1))}
                    className="w-12 h-12 rounded-lg bg-surface-container-lowest text-on-surface flex items-center justify-center active:scale-95 shadow-sm transition-transform cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[24px]">remove</span>
                  </button>

                  <div className="flex items-baseline gap-1">
                    <span className="font-stat-numeric text-[26px] text-on-surface font-extrabold">
                      {stockQty}
                    </span>
                    <span className="font-body-md text-body-md text-on-surface-variant">{t('pf_packs')}</span>
                  </div>

                  <button
                    type="button"
                    aria-label={t('pf_increase')}
                    onClick={() => setStockQty((q) => q + 1)}
                    className="w-12 h-12 rounded-lg bg-primary text-on-primary flex items-center justify-center active:scale-95 shadow-sm transition-transform cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[24px]">add</span>
                  </button>
                </div>
              </div>
              )}

              <div className="flex flex-col gap-space-sm">
                <div className="flex flex-col gap-1.5">
                  <label className="font-label-md text-label-md text-on-surface font-semibold" htmlFor="min-threshold">
                    {t('pf_low_threshold')}
                  </label>
                  <div className="relative">
                    <input
                      id="min-threshold"
                      type="number"
                      inputMode="decimal"
                      min="0"
                      value={minThresholdInput}
                      onChange={(e) => setMinThresholdInput(e.target.value)}
                      placeholder="0"
                      className="w-full h-12 px-3 bg-surface-container-low rounded-lg text-on-surface font-stat-numeric text-[18px] text-center focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-primary border border-transparent"
                    />
                    <span className="absolute start-2.5 top-1/2 -translate-y-1/2 font-label-sm text-label-sm text-outline">
                      {t('pf_packs_plural')}
                    </span>
                  </div>
                </div>

              </div>

              {/* Inventory Warning Note */}
              <div className="rounded-lg bg-secondary-fixed/30 p-space-sm flex items-start gap-space-xs">
                <span className="material-symbols-outlined text-secondary text-[20px] shrink-0 mt-0.5">
                  notification_important
                </span>
                <p className="font-body-sm text-body-sm text-on-secondary-fixed-variant leading-relaxed">
                  {t('pf_alert_note').replace('{count}', String(minThreshold))}
                </p>
              </div>
            </section>
          </div>

          {/* 6. Sticky Thumb Actions Bottom Bar */}
          <aside className="fixed bottom-3 inset-x-3 max-w-lg mx-auto z-40">
            <div className="bg-surface-container-lowest/95 backdrop-blur-md rounded-xl p-2.5 shadow-xl flex items-center gap-space-sm border border-outline-variant/30">
              <button
                type="button"
                disabled={isSubmitting || isSaved}
                onClick={() => handleSubmit()}
                className="flex-1 h-14 rounded-lg bg-primary hover:bg-primary-container active:scale-[0.98] transition-all flex items-center justify-center gap-2 text-on-primary font-headline-sm text-headline-sm shadow-md disabled:opacity-70 cursor-pointer"
              >
                {isSubmitting ? (
                  <span className="material-symbols-outlined animate-spin text-2xl">progress_activity</span>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[22px]">check_circle</span>
                    <span>{isEdit ? t('pf_save_changes') : t('pf_add_to_inventory')}</span>
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={() => router.back()}
                aria-label={t('pf_cancel')}
                className="w-14 h-14 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface-variant flex items-center justify-center active:scale-95 transition-transform cursor-pointer"
              >
                <span className="material-symbols-outlined text-[24px]">close</span>
              </button>
            </div>
          </aside>
        </div>
      </main>

      {/* Toast Notification */}
      {toastMsg && (
        <div className="fixed bottom-24 inset-x-4 max-w-md mx-auto z-50 bg-inverse-surface text-inverse-on-surface p-3.5 rounded-xl shadow-2xl flex items-center justify-between text-start animate-bounce">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary-fixed">verified</span>
            <span className="font-label-md text-body-sm">{toastMsg}</span>
          </div>
        </div>
      )}
    </div>
  );
}