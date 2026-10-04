// web/src/app/inventory/[id]/restock/page.tsx (route: /inventory/[id]/restock — direct restock intake)
'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { getProduct, restockProduct, getItemBatches, InventoryBatch } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { InventoryItemSchema, DirectRestockPayload } from '@/types';

// Same limit as the server (DirectRestockPayload.supplier_name, max 150).
const SUPPLIER_NAME_MAX = 150;

export default function RestockProductPage() {
  const params = useParams();
  const router = useRouter();
  const { t, dir, isRTL } = useLanguage();
  const currency = t('currency');

  const itemId = parseInt(params.id as string, 10);

  const [item, setItem] = useState<InventoryItemSchema | null>(null);
  const [batches, setBatches] = useState<InventoryBatch[]>([]);
  // Raw text so the field can be cleared while typing; the number is derived below.
  const [qtyText, setQtyText] = useState('1');
  const [buyPrice, setBuyPrice] = useState('');
  const [sellPrice, setSellPrice] = useState('');
  const [batchNo, setBatchNo] = useState('');
  const [expDate, setExpDate] = useState('');
  const [supplierName, setSupplierName] = useState('');
  const [supplierNotes, setSupplierNotes] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [batchLoadError, setBatchLoadError] = useState<string | null>(null);
  const [isBatchesLoading, setIsBatchesLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const redirectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    if (isNaN(itemId)) {
      router.replace('/inventory/overview');
      return;
    }
    loadItem();
  }, [itemId]);

  useEffect(() => {
    return () => {
      if (redirectTimer.current) clearTimeout(redirectTimer.current);
    };
  }, []);

  const loadItem = async () => {
    setIsLoading(true);
    setLoadError(null);
    setBatchLoadError(null);
    try {
      const data = await getProduct(itemId);
      setItem(data);
      if (data.unit_buy_price) setBuyPrice(data.unit_buy_price.toFixed(2));
      if (data.unit_sell_price) setSellPrice(data.unit_sell_price.toFixed(2));
      if (data.expiry_date) setExpDate(data.expiry_date);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('rs_item_load_error'));
    } finally {
      setIsLoading(false);
    }
    setIsBatchesLoading(true);
    try {
      setBatches(await getItemBatches(itemId));
    } catch (error) {
      setBatches([]);
      setBatchLoadError(error instanceof Error ? error.message : t('ov_batches_load_error'));
    } finally {
      setIsBatchesLoading(false);
    }
  };

  const parsedQty = parseInt(qtyText, 10);
  const currentQty = Number.isFinite(parsedQty) && parsedQty > 0 ? parsedQty : 0;

  const adjustQty = (delta: number) => {
    setQtyText(String(Math.max(1, currentQty + delta)));
  };

  const handleQtyChange = (value: string) => {
    setQtyText(value.replace(/\D/g, '').slice(0, 6));
  };

  const handleQtyBlur = () => {
    if (currentQty <= 0) setQtyText('1');
  };

  const parsedBuyPrice = parseFloat(buyPrice) || 0;
  const parsedSellPrice = parseFloat(sellPrice) || 0;
  const totalCost = currentQty * parsedBuyPrice;
  const totalRev = currentQty * parsedSellPrice;
  const netProfit = totalRev - totalCost;
  const newStockQty = (item?.stock_qty || 0) + currentQty;

  const supplierTooLong = supplierName.length > SUPPLIER_NAME_MAX;

  const handleConfirmRestock = async () => {
    if (currentQty <= 0 || supplierTooLong) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      // The intersection keeps this compiling whether or not the generated
      // DirectRestockPayload type already carries the two supplier fields.
      const payload: DirectRestockPayload & { supplier_name?: string; supplier_notes?: string } = {
        quantity: currentQty,
        unit_buy_price: parsedBuyPrice > 0 ? parsedBuyPrice : undefined,
        unit_sell_price: parsedSellPrice > 0 ? parsedSellPrice : undefined,
        batch_number: batchNo.trim() || undefined,
        expiry_date: expDate.trim() || undefined,
        supplier_name: supplierName.trim() || undefined,
        supplier_notes: supplierNotes.trim() || undefined,
      };
      await restockProduct(itemId, payload);
      setIsSuccess(true);
      redirectTimer.current = setTimeout(() => {
        router.push('/inventory/overview');
      }, 1200);
    } catch (err) {
      setSubmitError(err instanceof Error && err.message ? err.message : t('rs_submit_error'));
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-surface font-body-md text-on-surface flex flex-col min-h-screen antialiased">
      <TopHeader
        pharmacyName={item?.name_ar || (t('rs_title_fallback'))}
        subtitle={t('rs_subtitle')}
        showBack={true}
      />

      <main className="flex flex-col relative w-full pt-16 pb-safe bg-surface min-h-screen">
        <div className="flex flex-col w-full pb-48" dir={dir}>
          {loadError && (
            <div role="alert" className="mx-margin-mobile mt-space-md flex items-center justify-between gap-3 rounded-xl bg-error-container p-3 text-sm text-error">
              <span>{loadError}</span>
              <button type="button" onClick={() => void loadItem()} disabled={isLoading} className="min-h-10 shrink-0 rounded-lg px-3 font-semibold underline disabled:opacity-60">
                {t('retry')}
              </button>
            </div>
          )}

          {/* Mobile: one column in this order. Desktop: form on one side, preview and batches on the other. */}
          <div className="w-full max-w-6xl mx-auto lg:grid lg:grid-cols-12 lg:gap-x-space-lg lg:items-start lg:px-margin">
            {/* ===== Form column ===== */}
            <div className="lg:col-span-7 flex flex-col">
              {/* Top Medicine Identity Card */}
              <section className="px-margin-mobile lg:px-0 pt-space-md">
                <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-md flex flex-col gap-space-sm relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-1.5 h-full bg-primary rounded-r"></div>
                  <div className="flex items-start justify-between gap-space-sm pr-2">
                    <div className="flex flex-col min-w-0">
                      <div className="flex items-center gap-space-xs text-primary mb-1">
                        <span className="material-symbols-outlined text-[18px]">medication</span>
                        <span className="font-label-sm text-label-sm font-bold text-primary">
                          {t('rs_verified_product')}
                        </span>
                      </div>
                      <h2 className="font-headline-md text-headline-md text-on-surface truncate">
                        {item?.name_ar || (isLoading ? '...' : '—')}
                      </h2>
                      <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">
                        {t('rs_active_label')}
                        <span className="font-bold">{item?.active_ingredient || item?.name_en || '—'}</span>
                      </p>
                    </div>
                    <div className="w-12 h-12 rounded-xl bg-surface-container-low flex items-center justify-center shrink-0 text-primary">
                      <span className="material-symbols-outlined text-[28px]">pill</span>
                    </div>
                  </div>

                  {/* Quick Chips & Shelf Status */}
                  <div className="flex flex-wrap items-center gap-space-xs pt-space-xs pr-2">
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-container font-label-sm text-label-sm text-on-surface-variant">
                      <span className="material-symbols-outlined text-[14px]">barcode</span>
                      <span className="font-stat-numeric text-label-sm tracking-wide">
                        {item?.barcode || (t('rs_no_barcode'))}
                      </span>
                    </span>
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-secondary-fixed text-on-secondary-fixed font-label-sm text-label-sm font-bold">
                      <span className="material-symbols-outlined text-[14px] text-secondary">inventory_2</span>
                      {t('rs_current_stock').replace('{count}', String(item?.stock_qty || 0))}
                    </span>
                    {item?.category && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary-fixed text-on-primary-fixed-variant font-label-sm text-label-sm font-bold">
                        <span className="material-symbols-outlined text-[14px]">shelves</span>
                        {item.category}
                      </span>
                    )}
                  </div>
                </div>
              </section>

              {/* Quantity Stepper Section */}
              <section className="px-margin-mobile lg:px-0 pt-space-md">
                <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-md flex flex-col gap-space-sm">
                  <div className="flex items-center justify-between">
                    <label className="font-label-lg text-label-lg text-on-surface flex items-center gap-1" htmlFor="quantity-input">
                      <span>{t('rs_intake_qty')}</span>
                      <span className="text-error font-bold text-[16px]">*</span>
                    </label>
                    <span className="font-label-sm text-label-sm text-on-surface-variant bg-surface-container px-2 py-0.5 rounded">
                      {t('rs_unit_label')}
                    </span>
                  </div>

                  {/* Big Numeric Stepper (the number is also typeable) */}
                  <div className="flex items-center justify-between bg-surface-container-low rounded-xl p-2 h-20">
                    <button
                      type="button"
                      aria-label={t('rs_decrease')}
                      onClick={() => adjustQty(-1)}
                      className="w-touch-target-min h-touch-target-min rounded-xl bg-surface-container-highest text-on-surface hover:bg-surface-variant active:scale-95 transition-all flex items-center justify-center shadow-sm"
                    >
                      <span className="material-symbols-outlined text-[28px]">remove</span>
                    </button>
                    <div className="flex flex-col items-center justify-center flex-1 px-space-sm min-w-0">
                      <input
                        id="quantity-input"
                        type="text"
                        inputMode="numeric"
                        autoComplete="off"
                        dir="ltr"
                        value={qtyText}
                        onChange={(e) => handleQtyChange(e.target.value)}
                        onBlur={handleQtyBlur}
                        className="w-full text-center bg-transparent font-stat-numeric text-stat-numeric text-primary tracking-tight focus:outline-none"
                      />
                      <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">
                        {t('rs_ready_to_intake')}
                      </span>
                    </div>
                    <button
                      type="button"
                      aria-label={t('rs_increase')}
                      onClick={() => adjustQty(1)}
                      className="w-touch-target-min h-touch-target-min rounded-xl bg-primary text-on-primary hover:bg-primary-container active:scale-95 transition-all flex items-center justify-center shadow-sm"
                    >
                      <span className="material-symbols-outlined text-[28px]">add</span>
                    </button>
                  </div>

                  {/* Quick Add Pills */}
                  <div className="flex items-center justify-between gap-space-xs pt-space-xs overflow-x-auto no-scrollbar">
                    {[10, 24, 50, 100].map((step) => (
                      <button
                        key={step}
                        type="button"
                        onClick={() => adjustQty(step)}
                        className="flex-1 min-h-[44px] py-2 px-1 rounded-lg bg-surface-container text-on-surface hover:bg-primary-fixed hover:text-on-primary-fixed-variant active:scale-95 transition-all font-label-md text-label-md text-center"
                      >
                        +{step}
                      </button>
                    ))}
                  </div>
                </div>
              </section>

              {/* Pricing & Batch Inspection Details */}
              <section className="px-margin-mobile lg:px-0 pt-space-md flex flex-col gap-space-sm">
                <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-md flex flex-col gap-space-md">
                  <div className="flex items-center gap-space-xs pb-1">
                    <span className="material-symbols-outlined text-primary text-[20px]">receipt_long</span>
                    <h3 className="font-headline-sm text-headline-sm text-on-surface">
                      {t('rs_pricing_title')}
                    </h3>
                  </div>

                  {/* Buy Price & Sell Price */}
                  <div className="grid grid-cols-2 gap-space-sm">
                    <div className="flex flex-col gap-1">
                      <label className="font-label-md text-label-md text-on-surface" htmlFor="buy-price">
                        {t('rs_buy_price')}
                      </label>
                      <div className="relative flex items-center bg-surface-container-low rounded-lg p-2.5">
                        <input
                          id="buy-price"
                          type="number"
                          step="0.10"
                          value={buyPrice}
                          onChange={(e) => setBuyPrice(e.target.value)}
                          className={`w-full bg-transparent font-stat-numeric text-headline-sm text-on-surface focus:outline-none ${isRTL ? 'pr-1 pl-7' : 'pl-1 pr-7'}`}
                        />
                        <span className={`absolute ${isRTL ? 'left-2.5' : 'right-2.5'} font-label-sm text-label-sm text-on-surface-variant`}>
                          {currency}
                        </span>
                      </div>
                    </div>

                    <div className="flex flex-col gap-1">
                      <label className="font-label-md text-label-md text-on-surface" htmlFor="sell-price">
                        {t('rs_sell_price')}
                      </label>
                      <div className="relative flex items-center bg-surface-container-low rounded-lg p-2.5">
                        <input
                          id="sell-price"
                          type="number"
                          step="0.50"
                          value={sellPrice}
                          onChange={(e) => setSellPrice(e.target.value)}
                          className={`w-full bg-transparent font-stat-numeric text-headline-sm text-on-surface focus:outline-none ${isRTL ? 'pr-1 pl-7' : 'pl-1 pr-7'}`}
                        />
                        <span className={`absolute ${isRTL ? 'left-2.5' : 'right-2.5'} font-label-sm text-label-sm text-on-surface-variant`}>
                          {currency}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Batch No & Expiry */}
                  <div className="grid grid-cols-2 gap-space-sm pt-space-xs">
                    <div className="flex flex-col gap-1">
                      <label className="font-label-md text-label-md text-on-surface" htmlFor="batch-no">
                        {t('rs_batch_no')}
                      </label>
                      <div className="flex items-center bg-surface-container-low rounded-lg p-2.5">
                        <input
                          id="batch-no"
                          type="text"
                          value={batchNo}
                          onChange={(e) => setBatchNo(e.target.value)}
                          className="w-full bg-transparent font-body-md text-body-md text-on-surface focus:outline-none uppercase"
                        />
                      </div>
                    </div>

                    <div className="flex flex-col gap-1">
                      <label className="font-label-md text-label-md text-on-surface" htmlFor="exp-date">
                        {t('rs_expiry_date')}
                      </label>
                      <div className="flex items-center bg-surface-container-low rounded-lg p-2.5">
                        <input
                          id="exp-date"
                          type="date"
                          value={expDate}
                          onChange={(e) => setExpDate(e.target.value)}
                          className="w-full bg-transparent font-stat-numeric text-label-lg text-on-surface focus:outline-none"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              {/* Supplier (optional; free text, no supplier directory exists) */}
              <section className="px-margin-mobile lg:px-0 pt-space-md">
                <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-md flex flex-col gap-space-md">
                  <div className="flex items-center justify-between gap-space-xs">
                    <div className="flex items-center gap-space-xs">
                      <span className="material-symbols-outlined text-primary text-[20px]">local_shipping</span>
                      <h3 className="font-headline-sm text-headline-sm text-on-surface">
                        {t('rs_supplier_details')}
                      </h3>
                    </div>
                    <span className="font-label-sm text-label-sm text-on-surface-variant">
                      {t('rs_optional')}
                    </span>
                  </div>

                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-space-xs">
                      <label className="font-label-md text-label-md text-on-surface" htmlFor="supplier-name">
                        {t('rs_supplier_name')}
                      </label>
                      <span
                        className={`font-label-sm text-label-sm ${supplierTooLong ? 'text-error font-bold' : 'text-on-surface-variant'}`}
                        aria-live="polite"
                      >
                        {supplierName.length} / {SUPPLIER_NAME_MAX}
                      </span>
                    </div>
                    <div className={`flex items-center bg-surface-container-low rounded-lg p-2.5 ${supplierTooLong ? 'ring-2 ring-error' : ''}`}>
                      <input
                        id="supplier-name"
                        type="text"
                        dir="auto"
                        autoComplete="off"
                        value={supplierName}
                        onChange={(e) => setSupplierName(e.target.value)}
                        aria-invalid={supplierTooLong}
                        aria-describedby={supplierTooLong ? 'supplier-name-error' : undefined}
                        placeholder={t('rs_supplier_name_placeholder')}
                        className="w-full bg-transparent font-body-md text-body-md text-on-surface placeholder:text-outline focus:outline-none"
                      />
                    </div>
                    {supplierTooLong && (
                      <p id="supplier-name-error" role="alert" className="flex items-center gap-1 pt-0.5 font-body-sm text-body-sm text-error">
                        <span className="material-symbols-outlined text-[16px]">error</span>
                        {t('rs_supplier_name_too_long')}
                      </p>
                    )}
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="font-label-md text-label-md text-on-surface" htmlFor="supplier-notes">
                      {t('rs_supplier_notes')}
                    </label>
                    <div className="flex items-start bg-surface-container-low rounded-lg p-2.5">
                      <textarea
                        id="supplier-notes"
                        rows={2}
                        dir="auto"
                        value={supplierNotes}
                        onChange={(e) => setSupplierNotes(e.target.value)}
                        placeholder={t('rs_supplier_notes_placeholder')}
                        className="w-full resize-none bg-transparent font-body-md text-body-md text-on-surface placeholder:text-outline focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="flex items-start gap-space-sm rounded-lg bg-surface-container-low p-space-sm">
                    <span className="material-symbols-outlined text-secondary text-[20px] shrink-0 mt-0.5">account_balance_wallet</span>
                    <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">
                      {t('rs_credit_note')}
                    </p>
                  </div>
                </div>
              </section>
            </div>

            {/* ===== Preview column ===== */}
            <div className="lg:col-span-5 flex flex-col">
              {/* Real-time Financial Ledger Preview Box */}
              <section className="px-margin-mobile lg:px-0 pt-space-md">
                <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-md flex flex-col gap-space-sm relative overflow-hidden">
                  <div className="absolute top-0 right-0 left-0 h-1 bg-gradient-to-l from-primary to-primary-fixed"></div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-space-xs">
                      <div className="w-7 h-7 rounded-full bg-primary-fixed flex items-center justify-center">
                        <span className="material-symbols-outlined text-on-primary-fixed-variant text-[16px]">calculate</span>
                      </div>
                      <h4 className="font-label-lg text-label-lg text-on-surface">
                        {t('rs_preview_title')}
                      </h4>
                    </div>
                    <span className="font-label-sm text-label-sm text-primary font-bold flex items-center gap-0.5">
                      <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                      {t('rs_preview_live')}
                    </span>
                  </div>

                  <div className="bg-surface-container-low rounded-xl p-space-sm flex flex-col gap-space-xs divide-y divide-surface-container">
                    <div className="flex items-center justify-between py-1.5">
                      <div className="flex flex-col">
                        <span className="font-body-md text-body-md text-on-surface">
                          {t('rs_total_cost')}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant">
                          ({currentQty} × {parsedBuyPrice.toFixed(2)} {currency})
                        </span>
                      </div>
                      <div className="flex items-baseline gap-1">
                        <span className="font-stat-numeric text-headline-sm text-primary">
                          {totalCost.toFixed(2)}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant font-bold">
                          {currency}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between py-1.5">
                      <div className="flex flex-col">
                        <span className="font-body-md text-body-md text-on-surface">
                          {t('rs_new_stock')}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant">
                          {item?.stock_qty || 0} + {currentQty}
                        </span>
                      </div>
                      <span className="px-3 py-1 rounded-full bg-primary text-on-primary font-stat-numeric text-label-lg">
                        {newStockQty} {t('rs_units')}
                      </span>
                    </div>

                    <div className="flex items-center justify-between py-1.5">
                      <div className="flex flex-col">
                        <span className="font-body-md text-body-md text-on-surface">
                          {t('rs_expected_profit')}
                        </span>
                      </div>
                      <div className="flex items-baseline gap-1">
                        <span className="font-stat-numeric text-headline-sm text-secondary font-bold">
                          {netProfit.toFixed(2)}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant font-bold">
                          {currency}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              {/* Multi-Price Batches History / Existing Batches */}
              <section className="px-margin-mobile lg:px-0 pt-space-md">
                <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-md flex flex-col gap-space-sm">
                  <div className="flex items-center justify-between pb-1">
                    <div className="flex items-center gap-space-xs">
                      <span className="material-symbols-outlined text-primary text-[20px]">layers</span>
                      <h4 className="font-label-lg text-label-lg text-on-surface">
                        {t('rs_batches_title')}
                      </h4>
                    </div>
                    <span className="font-label-sm text-label-sm text-on-surface-variant">
                      {batches.length} {t('rs_batches_count_word')}
                    </span>
                  </div>

                  {isBatchesLoading ? (
                    <div className="p-3 text-center rounded-lg bg-surface-container-low text-on-surface-variant" role="status">
                      {t('ov_batches_loading')}
                    </div>
                  ) : batchLoadError ? (
                    <div role="alert" className="flex items-center justify-between gap-3 rounded-lg bg-error-container p-3 text-sm text-error">
                      <span>{batchLoadError}</span>
                      <button type="button" onClick={() => void loadItem()} disabled={isBatchesLoading} className="shrink-0 rounded-lg px-3 py-2 font-semibold underline disabled:opacity-60">
                        {t('retry')}
                      </button>
                    </div>
                  ) : batches.length === 0 ? (
                    <div className="p-3 text-center bg-surface-container-low rounded-lg text-on-surface-variant font-body-sm text-body-sm">
                      {t('rs_batches_none')}
                    </div>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {batches.map((b) => (
                        <div key={b.id} className="bg-surface-container-low rounded-lg p-2.5 flex items-center justify-between">
                          <div className="flex flex-col">
                            <div className="flex items-center gap-1.5">
                              <span className="font-label-md text-label-md font-bold text-on-surface">
                                {b.batch_number || (t('rs_no_batch'))}
                              </span>
                              {b.expiry_date && (
                                <span className="font-label-sm text-label-sm text-on-surface-variant">
                                  • {t('rs_exp_label')}{b.expiry_date}
                                </span>
                              )}
                            </div>
                            <span className="font-label-sm text-label-sm text-on-surface-variant">
                              {t('ov_buy_label')}{b.unit_buy_price.toFixed(2)} {currency} | {t('ov_sell_label')}{b.unit_sell_price.toFixed(2)} {currency}
                            </span>
                          </div>
                          <div className="flex flex-col items-end">
                            <span className="font-stat-numeric text-label-lg font-bold text-primary">
                              {b.quantity} {t('ov_pkgs')}
                            </span>
                            <span className="font-label-sm text-label-sm text-on-surface-variant">
                              = {b.total_retail.toFixed(2)} {currency}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            </div>
          </div>

          {/* Sticky Bottom Floating Action Bar */}
          <div className="fixed bottom-0 right-0 left-0 bg-surface/90 backdrop-blur-xl shadow-lg p-margin-mobile pb-safe z-40">
            <div className="w-full max-w-6xl mx-auto flex flex-col gap-space-xs">
              {submitError && (
                <div role="alert" className="flex items-start justify-between gap-space-sm rounded-lg bg-error-container p-2.5 text-on-error-container">
                  <div className="flex items-start gap-space-xs min-w-0">
                    <span className="material-symbols-outlined text-error text-[20px] shrink-0">error</span>
                    <div className="flex flex-col min-w-0">
                      <span className="font-label-md text-label-md font-bold">
                        {t('rs_submit_error_title')}
                      </span>
                      <span className="font-body-sm text-body-sm break-words">{submitError}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    aria-label={t('rs_dismiss')}
                    onClick={() => setSubmitError(null)}
                    className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center hover:bg-error/10"
                  >
                    <span className="material-symbols-outlined text-[18px]">close</span>
                  </button>
                </div>
              )}
              <div className="flex flex-col gap-space-xs sm:flex-row-reverse sm:justify-start">
                <button
                  type="button"
                  id="btn-submit"
                  disabled={!item || isLoading || isSubmitting || isSuccess || currentQty <= 0 || supplierTooLong}
                  onClick={handleConfirmRestock}
                  className="w-full sm:w-auto sm:px-8 h-[52px] rounded-lg bg-primary text-on-primary font-label-lg text-label-lg flex items-center justify-center gap-space-xs active:scale-[0.98] transition-transform shadow-md disabled:opacity-75"
                >
                  <span className="material-symbols-outlined text-[22px]">
                    {isSuccess ? 'check_circle' : isSubmitting ? 'sync' : 'inventory_2'}
                  </span>
                  <span>
                    {isSuccess
                      ? t('rs_success').replace('{count}', String(currentQty))
                      : isSubmitting
                      ? (t('rs_recording'))
                      : (t('rs_confirm'))}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => router.back()}
                  className="w-full sm:w-auto sm:px-6 h-11 rounded-lg text-on-surface-variant hover:text-on-surface font-label-md text-label-md flex items-center justify-center active:bg-surface-container transition-colors"
                >
                  {t('rs_cancel')}
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}