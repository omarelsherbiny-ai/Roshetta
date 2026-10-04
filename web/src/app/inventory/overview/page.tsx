// web/src/app/inventory/overview/page.tsx (route: /inventory/overview — stock valuation, price grid and batch inspector)
'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import {
  getInventory,
  getInventoryCategories,
  getInventorySummary,
  getItemBatches,
  InventoryBatch,
} from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { localeOf } from '@/lib/languages';
import { InventoryItemSchema, InventorySummary } from '@/types';

export default function InventoryOverviewPage() {
  const router = useRouter();
  const { lang, t, dir, isRTL } = useLanguage();

  const [items, setItems] = useState<InventoryItemSchema[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Batch modal state
  const [batchModalItem, setBatchModalItem] = useState<InventoryItemSchema | null>(null);
  const [modalBatches, setModalBatches] = useState<InventoryBatch[]>([]);
  const [modalBatchesLoading, setModalBatchesLoading] = useState(false);
  const [modalBatchesError, setModalBatchesError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    loadData();
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [itemsData, catsData, sumData] = await Promise.all([
        getInventory(), getInventoryCategories(), getInventorySummary(),
      ]);
      setItems(itemsData);
      setCategories(catsData);
      setSummary(sumData);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('ov_load_error'));
    } finally {
      setIsLoading(false);
    }
  };

  const openBatchModal = useCallback(async (item: InventoryItemSchema) => {
    setBatchModalItem(item);
    setModalBatches([]);
    setModalBatchesError(null);
    setModalBatchesLoading(true);
    try {
      const batches = await getItemBatches(item.id!);
      setModalBatches(batches);
    } catch (error) {
      setModalBatches([]);
      setModalBatchesError(error instanceof Error ? error.message : t('ov_batches_load_error'));
    } finally {
      setModalBatchesLoading(false);
    }
  }, []);

  const closeBatchModal = () => {
    setBatchModalItem(null);
    setModalBatches([]);
    setModalBatchesError(null);
  };

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const matchCat =
        selectedCategory === 'all' ||
        (item.category && item.category.trim() === selectedCategory.trim());
      const query = searchQuery.trim().toLowerCase();
      const matchQuery =
        !query ||
        item.name_ar.toLowerCase().includes(query) ||
        item.name_en.toLowerCase().includes(query) ||
        (item.barcode && item.barcode.includes(query)) ||
        (item.active_ingredient && item.active_ingredient.toLowerCase().includes(query));
      return matchCat && matchQuery;
    });
  }, [items, selectedCategory, searchQuery]);

  const filteredTotalValue = useMemo(() => {
    return filteredItems.reduce((acc, curr) => acc + curr.stock_qty * curr.unit_sell_price, 0);
  }, [filteredItems]);

  const filteredCapitalValue = useMemo(() => {
    return filteredItems.reduce((acc, curr) => acc + curr.stock_qty * curr.unit_buy_price, 0);
  }, [filteredItems]);

  const lowStockCount = useMemo(() => {
    return items.filter((i) => i.stock_qty <= i.min_threshold).length;
  }, [items]);

  const formatNum = (val: number) => {
    return val.toLocaleString(localeOf(lang));
  };


  return (
    <div className="bg-surface font-body-md text-on-surface flex flex-col min-h-screen">
      <TopHeader
        pharmacyName={t('ov_title')}
        subtitle={t('ov_subtitle')}
        showBack={true}
      />

      <main className="flex flex-col relative w-full pt-16 pb-28 px-margin-mobile bg-surface min-h-screen">
        <div className="flex flex-col w-full gap-space-md" dir={dir}>
          {/* Top Navigation & Page Context */}
          <div className="flex items-center justify-between gap-space-sm pt-space-xs">
            <div className="flex items-center gap-space-sm">
              <button
                type="button"
                aria-label={t('back')}
                onClick={() => router.back()}
                className="w-touch-target-min h-touch-target-min rounded-xl bg-surface-container flex items-center justify-center text-on-surface hover:bg-surface-container-high transition-colors active:scale-95 shadow-sm"
              >
                <span className="material-symbols-outlined text-[24px]">
                  {isRTL ? 'arrow_forward' : 'arrow_back'}
                </span>
              </button>
              <div className="flex flex-col">
                <h2 className="font-headline-sm text-headline-sm text-on-surface">
                  {t('ov_title')}
                </h2>
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  {t('ov_subtitle')}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={loadData}
              aria-label={t('ov_refresh')}
              className="w-10 h-10 rounded-xl bg-primary-fixed text-on-primary-fixed-variant flex items-center justify-center shadow-sm active:scale-95 transition-all"
            >
              <span className={`material-symbols-outlined text-[20px] ${isLoading ? 'animate-spin' : ''}`}>
                sync
              </span>
            </button>
          </div>

          {loadError && (
            <div role="alert" className="flex items-center justify-between gap-3 rounded-xl bg-error-container p-3 text-sm text-error">
              <span>{loadError}</span>
              <button type="button" onClick={() => void loadData()} disabled={isLoading} className="min-h-10 shrink-0 rounded-lg px-3 font-semibold underline disabled:opacity-60">
                {t('retry')}
              </button>
            </div>
          )}

          {/* 4-Column KPI Bento Hero */}
          <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-surface-container-lowest via-surface-container-low to-surface-container p-margin shadow-sm">
            <div className="absolute -top-12 -left-12 w-40 h-40 rounded-full bg-primary-fixed-dim/20 blur-2xl pointer-events-none" />
            <div className="relative flex flex-col gap-space-md">
              <div className="flex items-start justify-between">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-space-xs">
                    <span className="material-symbols-outlined text-primary text-[18px]">account_balance_wallet</span>
                    <span className="font-label-md text-label-md text-on-surface-variant">
                      {t('ov_total_value')}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-space-xs mt-0.5">
                    <span className="font-stat-numeric text-stat-numeric text-primary tracking-tight">
                      {summary
                        ? formatNum(Math.round(summary.potential_sales_value))
                        : formatNum(Math.round(filteredTotalValue))}
                    </span>
                    <span className="font-headline-sm text-headline-sm text-primary">
                      {t('currency')}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 bg-surface-container-lowest px-2.5 py-1 rounded-full shadow-sm">
                  <span className="material-symbols-outlined text-primary text-[16px]">verified</span>
                  <span className="font-label-sm text-label-sm text-primary font-bold">
                    {t('ov_live')}
                  </span>
                </div>
              </div>

              {/* 4-column secondary metrics */}
              <div className="grid grid-cols-4 gap-space-xs pt-space-xs">
                {/* Units */}
                <div className="flex flex-col bg-surface-container-lowest/80 backdrop-blur-sm p-space-sm rounded-lg shadow-sm">
                  <div className="flex items-center gap-1 text-primary">
                    <span className="material-symbols-outlined text-[14px]">medication</span>
                    <span className="font-label-sm text-label-sm text-on-surface-variant truncate">
                      {t('ov_units')}
                    </span>
                  </div>
                  <span className="font-label-lg text-label-lg text-on-surface mt-1">
                    {summary
                      ? formatNum(Math.round(summary.total_units))
                      : formatNum(items.reduce((s, i) => s + i.stock_qty, 0))}
                  </span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">
                    {t('ov_pkgs')}
                  </span>
                </div>

                {/* SKUs */}
                <div className="flex flex-col bg-surface-container-lowest/80 backdrop-blur-sm p-space-sm rounded-lg shadow-sm">
                  <div className="flex items-center gap-1 text-primary">
                    <span className="material-symbols-outlined text-[14px]">category</span>
                    <span className="font-label-sm text-label-sm text-on-surface-variant truncate">
                      {t('ov_skus')}
                    </span>
                  </div>
                  <span className="font-label-lg text-label-lg text-on-surface mt-1">
                    {formatNum(items.length)}
                  </span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">
                    {t('ov_items')}
                  </span>
                </div>

                {/* Capital/Cost value */}
                <div className="flex flex-col bg-surface-container-lowest/80 backdrop-blur-sm p-space-sm rounded-lg shadow-sm">
                  <div className="flex items-center gap-1 text-secondary">
                    <span className="material-symbols-outlined text-[14px]">payments</span>
                    <span className="font-label-sm text-label-sm text-on-surface-variant truncate">
                      {t('ov_capital')}
                    </span>
                  </div>
                  <span className="font-label-lg text-label-lg text-secondary mt-1">
                    {formatNum(Math.round(filteredCapitalValue))}
                  </span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">
                    {t('currency')}
                  </span>
                </div>

                {/* Low stock */}
                <div className="flex flex-col bg-tertiary-fixed/40 p-space-sm rounded-lg shadow-sm">
                  <div className="flex items-center gap-1 text-tertiary">
                    <span className="material-symbols-outlined text-[14px]">warning</span>
                    <span className="font-label-sm text-label-sm text-tertiary-container font-bold truncate">
                      {t('ov_low')}
                    </span>
                  </div>
                  <span className="font-label-lg text-label-lg text-tertiary mt-1">
                    {formatNum(lowStockCount)}
                  </span>
                  <span className="font-body-sm text-body-sm text-tertiary font-medium">
                    {t('ov_restock_small')}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Interactive Search & Action Bar */}
          <div className="flex items-center gap-space-xs">
            <div className="relative flex-1 flex items-center bg-surface-container-lowest rounded-xl shadow-sm h-touch-target-min px-space-md">
              <span className={`material-symbols-outlined text-outline text-[22px] ${isRTL ? 'ml-space-xs' : 'mr-space-xs'}`}>
                search
              </span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('ov_search_placeholder')}
                className="w-full bg-transparent font-body-sm text-body-sm text-on-surface placeholder:text-outline focus:outline-none"
              />
            </div>
            <Link
              href="/inventory/new"
              className="h-touch-target-min px-space-md bg-primary text-on-primary rounded-xl flex items-center justify-center gap-1 shadow-sm active:scale-95 transition-transform"
            >
              <span className="material-symbols-outlined text-[20px]">add</span>
              <span className="font-label-lg text-label-lg whitespace-nowrap">
                {t('ov_add_item')}
              </span>
            </Link>
          </div>

          {/* Horizontally Scrollable Category Filter Chips */}
          <div className="flex items-center gap-space-xs overflow-x-auto pb-1 -mx-margin-mobile px-margin-mobile scroll-smooth no-scrollbar">
            <button
              type="button"
              onClick={() => setSelectedCategory('all')}
              className={`flex-shrink-0 h-9 px-space-md rounded-full font-label-md text-label-md shadow-sm active:scale-95 transition-all flex items-center justify-center ${
                selectedCategory === 'all'
                  ? 'bg-primary text-on-primary'
                  : 'bg-surface-container-lowest text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {t('ov_all_count').replace('{count}', String(items.length))}
            </button>
            {categories.map((cat) => {
              const count = items.filter((i) => i.category === cat).length;
              const isSelected = selectedCategory === cat;
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSelectedCategory(cat)}
                  className={`flex-shrink-0 h-9 px-space-md rounded-full font-label-md text-label-md shadow-sm active:scale-95 transition-all flex items-center justify-center ${
                    isSelected
                      ? 'bg-primary text-on-primary'
                      : 'bg-surface-container-lowest text-on-surface-variant hover:text-on-surface'
                  }`}
                >
                  {cat} ({count})
                </button>
              );
            })}
          </div>

          {/* Dense Inventory Items Table */}
          <div className="bg-surface-container-lowest rounded-xl shadow-sm border border-surface-container overflow-hidden mt-space-xs">
            <div className="p-space-sm border-b border-surface-container flex items-center justify-between bg-surface-container-low/50">
              <div className="flex items-center gap-1.5">
                <span className="material-symbols-outlined text-primary text-[20px]">table_chart</span>
                <h3 className="font-label-lg text-label-lg text-on-surface font-bold">
                  {t('ov_grid_title')}
                </h3>
              </div>
              <span className="font-label-sm text-label-sm text-on-surface-variant bg-surface-container px-2 py-0.5 rounded-full">
                {t('ov_items_shown').replace('{count}', String(filteredItems.length))}
              </span>
            </div>

            <div className="overflow-x-auto no-scrollbar">
              <table className="w-full text-right border-collapse min-w-[580px]">
                <thead>
                  <tr className="bg-surface-container-high/60 border-b border-surface-variant font-label-md text-label-md text-on-surface-variant">
                    <th className="py-3 px-3 text-right font-bold">{t('inv_col_product')}</th>
                    <th className="py-3 px-3 text-center font-bold">{t('ov_col_stock')}</th>
                    <th className="py-3 px-3 text-left font-bold">{t('ov_col_buy_sell')}</th>
                    <th className="py-3 px-3 text-left font-bold">{t('ov_col_total')}</th>
                    <th className="py-3 px-2 text-center font-bold w-[110px]">{t('ov_col_actions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-low font-body-sm text-body-sm">
                  {filteredItems.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-on-surface-variant">
                        {t('ov_none_match')}
                      </td>
                    </tr>
                  ) : (
                    filteredItems.map((item) => {
                      const isLow = item.stock_qty <= item.min_threshold;
                      const rowTotal = item.stock_qty * item.unit_sell_price;
                      return (
                        <tr
                          key={item.id}
                          className={`transition-colors ${isLow ? 'bg-error-container/10 hover:bg-error-container/20' : 'hover:bg-surface-container-low/40'}`}
                        >
                          <td className="py-3 px-3 align-middle">
                            <div className="flex flex-col">
                              <div className="flex items-center gap-1.5">
                                <span className={`font-label-lg text-label-lg font-bold ${isLow ? 'text-tertiary' : 'text-on-surface'}`}>
                                  {item.name_ar}
                                </span>
                                {item.category && (
                                  <span className="bg-surface-container px-1.5 py-0.5 rounded text-[11px] text-on-surface-variant">
                                    {item.category}
                                  </span>
                                )}
                              </div>
                              <span className="text-[11px] text-on-surface-variant truncate max-w-[180px]">
                                {item.name_en} • {item.barcode || t('ov_no_barcode')}
                              </span>
                            </div>
                          </td>
                          <td className="py-3 px-3 align-middle text-center">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-1 rounded-full font-label-sm text-label-sm font-bold ${
                                isLow
                                  ? 'bg-tertiary-fixed text-tertiary'
                                  : 'bg-surface-container text-primary'
                              }`}
                            >
                              {isLow && <span className="material-symbols-outlined text-[12px]">warning</span>}
                              {!isLow && <span className="w-1.5 h-1.5 rounded-full bg-primary" />}
                              {formatNum(item.stock_qty)} {t('ov_unit_short')}
                            </span>
                          </td>
                          <td className="py-3 px-3 align-middle text-left whitespace-nowrap">
                            <div className="flex flex-col">
                              <span className="font-label-sm text-label-sm text-on-surface-variant">
                                {t('ov_buy_label')}{formatNum(item.unit_buy_price)} {t('currency')}
                              </span>
                              <span className="font-label-md text-label-md text-primary font-bold">
                                {t('ov_sell_label')}{formatNum(item.unit_sell_price)} {t('currency')}
                              </span>
                            </div>
                          </td>
                          <td className={`py-3 px-3 align-middle text-left font-label-lg text-label-lg font-bold whitespace-nowrap ${isLow ? 'text-tertiary' : 'text-primary'}`}>
                            {formatNum(Math.round(rowTotal))} {t('currency')}
                          </td>
                          <td className="py-3 px-2 align-middle text-center">
                            <div className="flex items-center justify-center gap-1">
                              {/* View Batches button */}
                              <button
                                type="button"
                                title={t('ov_view_batches')}
                                onClick={() => openBatchModal(item)}
                                className="w-8 h-8 rounded-lg flex items-center justify-center text-on-surface-variant hover:bg-primary-fixed hover:text-on-primary-fixed-variant transition-colors"
                              >
                                <span className="material-symbols-outlined text-[18px]">layers</span>
                              </button>
                              {/* Restock button */}
                              <Link
                                href={`/inventory/${item.id}/restock`}
                                title={t('inv_restock_long')}
                                className="w-8 h-8 rounded-lg flex items-center justify-center text-primary hover:bg-surface-container transition-colors mx-auto"
                              >
                                <span className="material-symbols-outlined text-[18px]">add_shopping_cart</span>
                              </Link>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Sticky Bottom Summary Bar */}
          <div className="sticky bottom-2 z-40 bg-inverse-surface text-inverse-on-surface rounded-xl p-space-md shadow-xl flex items-center justify-between gap-space-sm mt-space-sm">
            <div className="flex flex-col">
              <span className="font-label-sm text-label-sm text-primary-fixed-dim">
                {t('ov_showing_of').replace('{shown}', String(filteredItems.length)).replace('{total}', String(items.length))}
              </span>
              <div className="flex items-baseline gap-1 mt-0.5">
                <span className="font-label-md text-label-md text-surface-variant">
                  {t('ov_filtered_total')}
                </span>
                <span className="font-headline-sm text-headline-sm text-primary-fixed font-bold">
                  {formatNum(Math.round(filteredTotalValue))} {t('currency')}
                </span>
              </div>
            </div>

            <Link
              href="/inventory/categories"
              className="h-11 px-3.5 bg-primary-fixed text-on-primary-fixed rounded-lg font-label-md text-label-md flex items-center justify-center gap-1.5 active:scale-95 transition-all shadow-sm"
            >
              <span className="material-symbols-outlined text-[18px]">category</span>
              <span>{t('inv_categories')}</span>
            </Link>
          </div>
        </div>
      </main>

      <BottomNav />

      {/* Batch Detail Modal */}
      {batchModalItem && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-sm"
          onClick={closeBatchModal}
        >
          <div
            className="w-full max-w-lg bg-surface rounded-t-2xl shadow-2xl flex flex-col max-h-[80vh]"
            dir={dir}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between p-space-md border-b border-surface-container">
              <div className="flex items-center gap-space-sm">
                <div className="w-9 h-9 rounded-xl bg-primary-fixed flex items-center justify-center">
                  <span className="material-symbols-outlined text-on-primary-fixed-variant text-[20px]">layers</span>
                </div>
                <div className="flex flex-col">
                  <span className="font-label-lg text-label-lg text-on-surface font-bold">
                    {t('ov_batches_title')}
                  </span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">
                    {batchModalItem.name_ar}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={closeBatchModal}
                aria-label={t('cat_close')}
                className="w-9 h-9 rounded-xl bg-surface-container flex items-center justify-center text-on-surface-variant hover:bg-surface-container-high active:scale-95 transition-all"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            {/* Modal body */}
            <div className="overflow-y-auto flex-1 p-space-md flex flex-col gap-2">
              {modalBatchesLoading ? (
                <div className="flex flex-col items-center justify-center py-10 gap-2 text-on-surface-variant">
                  <span className="material-symbols-outlined text-[32px] animate-spin text-primary">progress_activity</span>
                  <span className="font-body-sm text-body-sm">{t('ov_batches_loading')}</span>
                </div>
              ) : modalBatchesError ? (
                <div role="alert" className="flex flex-col items-center justify-center gap-3 py-10 text-error">
                  <span>{modalBatchesError}</span>
                  <button type="button" disabled={modalBatchesLoading} onClick={() => batchModalItem && void openBatchModal(batchModalItem)} className="rounded-lg bg-error-container px-4 py-2 font-semibold disabled:opacity-60">
                    {t('retry')}
                  </button>
                </div>
              ) : modalBatches.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 gap-2 text-on-surface-variant">
                  <span className="material-symbols-outlined text-[32px] text-outline">inventory_2</span>
                  <span className="font-body-sm text-body-sm">
                    {t('ov_batches_none')}
                  </span>
                </div>
              ) : (
                modalBatches.map((batch, idx) => {
                  const isActive = batch.quantity > 0;
                  return (
                    <div
                      key={batch.id}
                      className={`rounded-xl p-space-sm flex items-center justify-between gap-space-sm border ${
                        isActive
                          ? 'bg-surface-container-lowest border-surface-container shadow-sm'
                          : 'bg-surface-container border-transparent opacity-60'
                      }`}
                    >
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <div className="flex items-center gap-1.5">
                          {/* FIFO order badge */}
                          <span className={`w-5 h-5 rounded-full flex items-center justify-center font-label-sm text-label-sm font-bold shrink-0 ${isActive ? 'bg-primary text-on-primary' : 'bg-surface-container-highest text-on-surface-variant'}`}>
                            {idx + 1}
                          </span>
                          <span className="font-label-md text-label-md font-bold text-on-surface font-stat-numeric uppercase truncate">
                            {batch.batch_number || t('ov_no_batch_number')}
                          </span>
                          {isActive ? (
                            <span className="px-2 py-0.5 rounded-full bg-primary-fixed text-on-primary-fixed-variant font-label-sm text-label-sm font-bold">
                              {t('ov_batch_active')}
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant font-label-sm text-label-sm">
                              {t('ov_batch_depleted')}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-body-sm text-body-sm text-on-surface-variant">
                            {t('ov_buy_short')} <span className="font-bold text-on-surface font-stat-numeric">{batch.unit_buy_price.toFixed(2)}</span> {t('currency')}
                          </span>
                          <span className="text-outline">•</span>
                          <span className="font-body-sm text-body-sm text-on-surface-variant">
                            {t('ov_sell_short')} <span className="font-bold text-primary font-stat-numeric">{batch.unit_sell_price.toFixed(2)}</span> {t('currency')}
                          </span>
                          {batch.expiry_date && (
                            <>
                              <span className="text-outline">•</span>
                              <span className="font-body-sm text-body-sm text-on-surface-variant">
                                {t('ov_exp_short')} {batch.expiry_date}
                              </span>
                            </>
                          )}
                        </div>
                        {batch.created_at && (
                          <span className="font-label-sm text-label-sm text-on-surface-variant">
                            {t('ov_added')} {new Date(batch.created_at).toLocaleDateString(localeOf(lang))}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-col items-end shrink-0 gap-0.5">
                        <span className={`font-stat-numeric text-headline-sm font-bold ${isActive ? 'text-primary' : 'text-on-surface-variant'}`}>
                          {batch.quantity}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant">
                          {t('ov_pkgs')}
                        </span>
                        <span className="font-label-sm text-label-sm text-secondary font-bold">
                          {batch.total_retail.toFixed(0)} {t('currency')}
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Modal footer */}
            <div className="p-space-md border-t border-surface-container flex items-center gap-space-sm pb-safe">
              <Link
                href={`/inventory/${batchModalItem.id}/restock`}
                className="flex-1 h-12 rounded-xl bg-primary text-on-primary flex items-center justify-center gap-1.5 font-label-lg text-label-lg active:scale-95 transition-all shadow-sm"
              >
                <span className="material-symbols-outlined text-[20px]">add_shopping_cart</span>
                <span>{t('ov_new_lot')}</span>
              </Link>
              <button
                type="button"
                onClick={closeBatchModal}
                className="h-12 px-4 rounded-xl bg-surface-container text-on-surface-variant font-label-md text-label-md active:scale-95 transition-all"
              >
                {t('cat_close')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}