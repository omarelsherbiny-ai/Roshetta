// web/src/app/inventory/page.tsx  (route: /inventory — inventory catalog)
'use client';

import React, { Suspense, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { getInventoryItems } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { otherNameDirection, pickLocalizedName, pickOtherName } from '@/lib/languages';
import { InventoryItemSchema } from '@/types';
import { cairoToday } from '@/lib/dateRange';

const ALL = '';
const UNCATEGORIZED = '__uncategorized__';
const PAGE_SIZE = 25;
const SHORT_EXPIRY_DAYS = 90;

type QuickFilter = 'all' | 'low' | 'expiry';
type ExpiryStatus = 'none' | 'ok' | 'soon' | 'expired';

// Whole days from Cairo's today to the expiry date. Both sides are read as calendar days (UTC midnight)
// so the result does not depend on the device's own time zone.
function daysUntil(dateStr: string): number | null {
  const expiry = Date.parse(`${dateStr.slice(0, 10)}T00:00:00Z`);
  const today = Date.parse(`${cairoToday()}T00:00:00Z`);
  if (Number.isNaN(expiry) || Number.isNaN(today)) return null;
  return Math.round((expiry - today) / 86400000);
}

function expiryStatus(expiry: string | null): ExpiryStatus {
  if (!expiry) return 'none';
  const days = daysUntil(expiry);
  if (days === null) return 'none';
  if (days < 0) return 'expired';
  if (days <= SHORT_EXPIRY_DAYS) return 'soon';
  return 'ok';
}

function isLowStock(item: InventoryItemSchema): boolean {
  // Same rule as the server's /api/inventory/low-stock endpoint.
  return item.stock_qty <= item.min_threshold;
}

function formatQty(n: number): string {
  return Number.isInteger(n) ? String(n) : String(Number(n.toFixed(2)));
}

function stockPercent(item: InventoryItemSchema): number {
  const target = Math.max(item.min_threshold * 2, 1);
  return Math.max(0, Math.min(100, Math.round((item.stock_qty / target) * 100)));
}

function InventoryCatalog() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { lang, t, dir, isRTL } = useLanguage();

  const [items, setItems] = useState<InventoryItemSchema[]>([]);
  const [search, setSearch] = useState('');
  const [catFilter, setCatFilter] = useState<string>(searchParams.get('category') ?? ALL);
  const [quick, setQuick] = useState<QuickFilter>('all');
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      setItems(await getInventoryItems());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('inv_load_error'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    void loadData();
  }, []);

  // Keep the filter in step with the URL (links from the categories page, back/forward).
  useEffect(() => {
    setCatFilter(searchParams.get('category') ?? ALL);
    setVisible(PAGE_SIZE);
  }, [searchParams]);

  const selectCategory = (next: string) => {
    setCatFilter(next);
    setVisible(PAGE_SIZE);
    router.replace(next ? `/inventory?category=${encodeURIComponent(next)}` : '/inventory', { scroll: false });
  };

  const clearFilters = () => {
    setQuick('all');
    selectCategory(ALL);
  };

  const { categoryList, uncategorizedCount } = useMemo(() => {
    const counts = new Map<string, number>();
    let none = 0;
    for (const item of items) {
      const c = item.category?.trim();
      if (c) counts.set(c, (counts.get(c) ?? 0) + 1);
      else none += 1;
    }
    return {
      categoryList: Array.from(counts.entries()).sort((a, b) => a[0].localeCompare(b[0], lang)),
      uncategorizedCount: none,
    };
  }, [items, lang]);

  const lowCount = useMemo(() => items.filter(isLowStock).length, [items]);
  const expiryCount = useMemo(
    () => items.filter((i) => {
      const s = expiryStatus(i.expiry_date);
      return s === 'soon' || s === 'expired';
    }).length,
    [items],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((i) => {
      const cat = i.category?.trim() || '';
      if (catFilter === UNCATEGORIZED) {
        if (cat) return false;
      } else if (catFilter !== ALL && cat !== catFilter) {
        return false;
      }
      if (quick === 'low' && !isLowStock(i)) return false;
      if (quick === 'expiry') {
        const s = expiryStatus(i.expiry_date);
        if (s !== 'soon' && s !== 'expired') return false;
      }
      if (!q) return true;
      return [i.name_ar, i.name_en, i.active_ingredient, i.barcode].some((v) => (v ?? '').toLowerCase().includes(q));
    });
  }, [items, search, catFilter, quick]);

  const shown = filtered.slice(0, visible);
  const filtersActive = catFilter !== ALL || quick !== 'all';
  const realCategory = catFilter !== ALL && catFilter !== UNCATEGORIZED ? catFilter : null;
  const emptyKind: 'search' | 'category' | 'filter' = search.trim()
    ? 'search'
    : catFilter !== ALL && quick === 'all'
      ? 'category'
      : 'filter';

  const primaryName = (i: InventoryItemSchema) => pickLocalizedName(lang, i.name_ar, i.name_en);
  const secondaryName = (i: InventoryItemSchema) => pickOtherName(lang, i.name_ar, i.name_en);

  const stockBadge = (i: InventoryItemSchema) =>
    isLowStock(i) ? (
      <span className="inline-flex items-center gap-1 rounded-full bg-secondary-fixed px-2.5 py-1 font-label-sm text-label-sm font-bold text-on-secondary-fixed">
        <span className="material-symbols-outlined text-[14px]" aria-hidden="true">warning</span>
        {t('inv_badge_low')}
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 rounded-full bg-surface-container px-2.5 py-1 font-label-sm text-label-sm font-bold text-primary">
        <span className="material-symbols-outlined text-[14px]" aria-hidden="true">check_circle</span>
        {t('inv_badge_ok')}
      </span>
    );

  const expiryBadge = (i: InventoryItemSchema) => {
    const s = expiryStatus(i.expiry_date);
    if (s === 'expired') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-error-container px-2 py-0.5 font-label-sm text-label-sm font-bold text-on-error-container">
          <span className="material-symbols-outlined text-[14px]" aria-hidden="true">event_busy</span>
          {t('inv_badge_expired')}
        </span>
      );
    }
    if (s === 'soon') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-tertiary-fixed px-2 py-0.5 font-label-sm text-label-sm font-bold text-on-tertiary-fixed">
          <span className="material-symbols-outlined text-[14px]" aria-hidden="true">alarm</span>
          {t('inv_badge_soon')}
        </span>
      );
    }
    return null;
  };

  const categoryChip = (i: InventoryItemSchema) =>
    i.category?.trim() ? (
      <span className="rounded-full bg-surface-container-high px-2.5 py-1 font-label-sm text-label-sm text-on-surface">{i.category.trim()}</span>
    ) : (
      <span className="rounded bg-surface-container px-2 py-0.5 font-label-sm text-label-sm italic text-outline">{t('cat_no_category')}</span>
    );

  const actionClasses =
    'inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg px-4 font-label-lg text-label-lg transition-all active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';

  return (
    <div className="bg-surface text-on-surface font-body-md text-body-md flex flex-col min-h-screen">
      <TopHeader
        pharmacyName={t('inventory')}
        subtitle={t('inv_subtitle')}
        showBack={true}
      />

      <main className="flex flex-col relative w-full pt-16 pb-28 px-margin bg-surface flex-grow">
        <div className="flex flex-col w-full pb-6" dir={dir}>
          {/* Title row */}
          <div className="flex items-center justify-between gap-space-sm mb-space-sm">
            <div className="flex min-w-0 items-center gap-space-sm">
              <h1 className="font-headline-sm text-headline-sm text-on-surface truncate">{t('inventory')}</h1>
              <span className="shrink-0 rounded-full bg-surface-container-high px-2.5 py-0.5 font-label-md text-label-md text-primary">
                {t('cat_item_count').replace('{count}', String(items.length))}
              </span>
            </div>
            <Link
              href="/inventory/new"
              className={`${actionClasses} shrink-0 bg-primary text-on-primary shadow-sm hover:bg-primary-container`}
            >
              <span className="material-symbols-outlined text-[20px]" aria-hidden="true">add</span>
              {t('add_product')}
            </Link>
          </div>

          <div className="flex items-center gap-space-sm mb-space-md">
            <Link
              href="/inventory/overview"
              className="flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-lg bg-surface-container-lowest font-label-md text-label-md text-on-surface-variant shadow-sm transition-colors hover:text-primary"
            >
              <span className="material-symbols-outlined text-[18px]" aria-hidden="true">query_stats</span>
              {t('inv_overview')}
            </Link>
            <Link
              href="/inventory/categories"
              className="flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-lg bg-surface-container-lowest font-label-md text-label-md text-on-surface-variant shadow-sm transition-colors hover:text-primary"
            >
              <span className="material-symbols-outlined text-[18px]" aria-hidden="true">category</span>
              {t('inv_categories')}
            </Link>
          </div>

          {/* Search */}
          <div className="relative mb-space-sm">
            <div className={`absolute inset-y-0 ${isRTL ? 'start-0 ps-3.5' : 'end-0 pe-3.5'} flex items-center pointer-events-none text-outline`}>
              <span className="material-symbols-outlined text-[22px]">search</span>
            </div>
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setVisible(PAGE_SIZE);
              }}
              placeholder={t('inv_search_placeholder')}
              className="w-full h-12 ps-11 pe-12 bg-surface-container-lowest text-on-surface placeholder:text-outline rounded-xl font-body-md text-body-md shadow-sm focus:bg-surface-container-low focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary transition-all"
            />
          </div>

          {/* Quick filters */}
          <div className="flex items-center gap-space-sm overflow-x-auto pb-1 mb-space-sm">
            {([
              ['all', t('inv_filter_all'), items.length, 'apps'],
              ['low', t('inv_filter_low'), lowCount, 'warning'],
              ['expiry', t('inv_filter_expiry'), expiryCount, 'hourglass_bottom'],
            ] as [QuickFilter, string, number, string][]).map(([key, label, count, icon]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setQuick(key);
                  setVisible(PAGE_SIZE);
                }}
                aria-pressed={quick === key}
                className={`inline-flex min-h-[44px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-3.5 font-label-md text-label-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                  quick === key
                    ? 'bg-primary text-on-primary shadow-sm'
                    : 'bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container-high'
                }`}
              >
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{icon}</span>
                {label}
                <span className="opacity-80">({count})</span>
              </button>
            ))}
          </div>

          {/* Category chips */}
          <div className="flex items-center gap-space-sm overflow-x-auto pb-1 mb-space-md">
            <button
              type="button"
              onClick={() => selectCategory(ALL)}
              aria-pressed={catFilter === ALL}
              className={`min-h-[44px] shrink-0 whitespace-nowrap rounded-full px-3.5 font-label-md text-label-md transition-colors ${
                catFilter === ALL ? 'bg-primary text-on-primary' : 'bg-surface-container text-on-surface-variant hover:bg-surface-container-high'
              }`}
            >
              {t('inv_all')} ({items.length})
            </button>
            {categoryList.map(([name, count]) => (
              <button
                key={name}
                type="button"
                onClick={() => selectCategory(name)}
                aria-pressed={catFilter === name}
                className={`min-h-[44px] shrink-0 whitespace-nowrap rounded-full px-3.5 font-label-md text-label-md transition-colors ${
                  catFilter === name ? 'bg-primary text-on-primary' : 'bg-surface-container text-on-surface-variant hover:bg-surface-container-high'
                }`}
              >
                {name} ({count})
              </button>
            ))}
            {uncategorizedCount > 0 && (
              <button
                type="button"
                onClick={() => selectCategory(UNCATEGORIZED)}
                aria-pressed={catFilter === UNCATEGORIZED}
                className={`min-h-[44px] shrink-0 whitespace-nowrap rounded-full px-3.5 font-label-md text-label-md transition-colors ${
                  catFilter === UNCATEGORIZED ? 'bg-primary text-on-primary' : 'bg-surface-container text-on-surface-variant hover:bg-surface-container-high'
                }`}
              >
                {t('cat_no_category')} ({uncategorizedCount})
              </button>
            )}
            {filtersActive && (
              <button
                type="button"
                onClick={clearFilters}
                className="inline-flex min-h-[44px] shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-error-container px-3 font-label-md text-label-md text-on-error-container transition-opacity hover:opacity-90"
              >
                <span className="material-symbols-outlined text-[16px]" aria-hidden="true">close</span>
                {t('inv_clear_filter')}
              </button>
            )}
          </div>

          {loadError && (
            <div role="alert" className="mb-space-md flex flex-col items-center gap-3 rounded-xl bg-error-container p-6 text-center text-on-error-container">
              <span className="material-symbols-outlined text-[32px]" aria-hidden="true">cloud_off</span>
              <p className="font-body-md text-body-md">{loadError}</p>
              <button
                type="button"
                onClick={() => void loadData()}
                disabled={isLoading}
                className={`${actionClasses} bg-primary text-on-primary disabled:opacity-60`}
              >
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">refresh</span>
                {t('retry')}
              </button>
            </div>
          )}

          {/* Loading skeleton */}
          {isLoading && !loadError && (
            <div className="flex flex-col gap-space-sm" role="status" aria-label={t('inv_loading')}>
              {[0, 1, 2].map((n) => (
                <div key={n} className="flex animate-pulse flex-col gap-space-sm rounded-xl bg-surface-container-lowest p-space-md shadow-sm">
                  <div className="flex items-start justify-between">
                    <div className="flex w-2/3 flex-col gap-2">
                      <div className="h-4 w-2/3 rounded bg-surface-container-high" />
                      <div className="h-3 w-1/3 rounded bg-surface-container" />
                    </div>
                    <div className="h-6 w-16 rounded bg-surface-container-high" />
                  </div>
                  <div className="h-6 w-1/2 rounded-lg bg-surface-container" />
                  <div className="h-14 w-full rounded-lg bg-surface-container-low" />
                </div>
              ))}
            </div>
          )}

          {/* Empty inventory */}
          {!isLoading && !loadError && items.length === 0 && (
            <div className="flex flex-col items-center justify-center py-space-xl text-center">
              <div className="mb-space-md flex h-20 w-20 items-center justify-center rounded-full bg-surface-container text-primary">
                <span className="material-symbols-outlined text-[40px]" aria-hidden="true">inventory_2</span>
              </div>
              <h2 className="mb-1 font-headline-sm text-headline-sm text-on-surface">{t('inv_empty_title')}</h2>
              <p className="mb-space-md max-w-xs font-body-md text-body-md text-on-surface-variant">
                {t('inv_empty_hint')}
              </p>
              <Link href="/inventory/new" className={`${actionClasses} bg-primary text-on-primary shadow-sm`}>
                <span className="material-symbols-outlined text-[20px]" aria-hidden="true">add</span>
                {t('inv_empty_action')}
              </Link>
            </div>
          )}

          {/* Empty result states */}
          {!isLoading && !loadError && items.length > 0 && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-space-xl text-center">
              <div className="mb-space-md flex h-16 w-16 items-center justify-center rounded-full bg-surface-container-high text-outline">
                <span className="material-symbols-outlined text-[32px]" aria-hidden="true">
                  {emptyKind === 'search' ? 'manage_search' : emptyKind === 'category' ? 'folder_off' : 'filter_alt_off'}
                </span>
              </div>
              <h2 className="mb-1 font-headline-sm text-headline-sm text-on-surface">
                {emptyKind === 'search'
                  ? t('inv_none_search')
                  : emptyKind === 'category'
                    ? t('inv_none_category')
                    : t('inv_none_filter')}
              </h2>
              <p className="mb-space-md max-w-xs font-body-md text-body-md text-on-surface-variant">
                {emptyKind === 'search'
                  ? t('inv_hint_search')
                  : t('inv_hint_filter')}
              </p>
              <div className="flex w-full max-w-[260px] flex-col gap-2">
                {emptyKind === 'search' ? (
                  <button
                    type="button"
                    onClick={() => setSearch('')}
                    className={`${actionClasses} bg-surface-container-high text-on-surface`}
                  >
                    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">restart_alt</span>
                    {t('inv_reset_search')}
                  </button>
                ) : (
                  <>
                    <button type="button" onClick={clearFilters} className={`${actionClasses} bg-primary text-on-primary shadow-sm`}>
                      {t('inv_show_all')}
                    </button>
                    {emptyKind === 'category' && realCategory && (
                      <Link
                        href={`/inventory/new?category=${encodeURIComponent(realCategory)}`}
                        className={`${actionClasses} bg-surface-container-high text-on-surface`}
                      >
                        <span className="material-symbols-outlined text-[18px]" aria-hidden="true">add</span>
                        {t('inv_add_to_category')}
                      </Link>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {/* Results */}
          {!isLoading && !loadError && shown.length > 0 && (
            <>
              {/* Mobile cards */}
              <div className="flex flex-col gap-space-sm md:hidden">
                {shown.map((item) => {
                  const low = isLowStock(item);
                  return (
                    <article key={item.id} className="relative flex flex-col gap-space-sm overflow-hidden rounded-xl bg-surface-container-lowest p-space-md shadow-sm">
                      {low && <div className="absolute inset-y-0 start-0 w-1.5 bg-secondary" aria-hidden="true" />}
                      <div className="flex items-start justify-between gap-space-sm">
                        <div className="flex min-w-0 flex-col">
                          <h3 className="font-headline-sm text-headline-sm leading-tight text-on-surface">{primaryName(item)}</h3>
                          {secondaryName(item) && (
                            <span className="font-body-sm text-body-sm text-outline" dir={otherNameDirection(lang)}>{secondaryName(item)}</span>
                          )}
                          {item.active_ingredient && (
                            <span className="font-body-sm text-body-sm text-on-surface-variant" dir="ltr">{item.active_ingredient}</span>
                          )}
                        </div>
                        <div className="shrink-0 text-end">
                          <span className="font-stat-numeric text-[20px] leading-6 text-primary">{item.unit_sell_price.toFixed(2)}</span>
                          <span className="ms-1 font-label-sm text-label-sm font-bold text-primary">{t('currency')}</span>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {categoryChip(item)}
                        {stockBadge(item)}
                        {expiryBadge(item)}
                      </div>

                      <div className="grid grid-cols-2 gap-2 rounded-lg bg-surface-container-low p-2.5 font-body-sm text-body-sm text-on-surface-variant">
                        <div className="flex flex-col">
                          <span className="font-label-sm text-label-sm text-outline">{t('inv_stock_min_short')}</span>
                          <span className={`font-label-md text-label-md ${low ? 'text-secondary' : 'text-on-surface'}`}>
                            {formatQty(item.stock_qty)} / {formatQty(item.min_threshold)}
                          </span>
                        </div>
                        <div className="flex flex-col">
                          <span className="font-label-sm text-label-sm text-outline">{t('inv_expires')}</span>
                          <span className="font-label-md text-label-md text-on-surface">{item.expiry_date ? item.expiry_date.slice(0, 10) : '—'}</span>
                        </div>
                        <div className="col-span-2 flex flex-col">
                          <span className="font-label-sm text-label-sm text-outline">{t('inv_barcode')}</span>
                          {item.barcode ? (
                            <span className="truncate font-mono text-[13px] text-on-surface" dir="ltr">{item.barcode}</span>
                          ) : (
                            <span className="font-label-sm text-label-sm italic text-outline">{t('inv_no_barcode')}</span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 pt-1">
                        <Link
                          href={`/inventory/${item.id}/restock`}
                          className={`${actionClasses} flex-1 ${low ? 'bg-secondary text-on-secondary' : 'bg-primary-container text-on-primary'} shadow-sm`}
                        >
                          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">add_shopping_cart</span>
                          {t('inv_restock_long')}
                        </Link>
                        <Link href={`/inventory/${item.id}/edit`} className={`${actionClasses} bg-surface-container-high text-on-surface`}>
                          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">edit</span>
                          {t('edit')}
                        </Link>
                      </div>
                    </article>
                  );
                })}
              </div>

              {/* Desktop table */}
              <div className="hidden overflow-hidden rounded-xl bg-surface-container-lowest shadow-sm md:block">
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-start">
                    <thead>
                      <tr className="bg-surface-container-low font-label-md text-label-md text-on-surface-variant">
                        <th scope="col" className="px-4 py-3.5 text-start">{t('inv_col_product')}</th>
                        <th scope="col" className="px-4 py-3.5 text-start">{t('inv_barcode')}</th>
                        <th scope="col" className="px-4 py-3.5 text-start">{t('inv_col_category')}</th>
                        <th scope="col" className="px-4 py-3.5 text-start">{t('inv_col_stock')}</th>
                        <th scope="col" className="px-4 py-3.5 text-start">{t('inv_col_price')}</th>
                        <th scope="col" className="px-4 py-3.5 text-start">{t('inv_col_expiry')}</th>
                        <th scope="col" className="px-4 py-3.5 text-end">{t('inv_col_actions')}</th>
                      </tr>
                    </thead>
                    <tbody className="font-body-md text-body-md text-on-surface">
                      {shown.map((item) => {
                        const low = isLowStock(item);
                        return (
                          <tr key={item.id} className="transition-colors hover:bg-surface">
                            <td className="px-4 py-4">
                              <div className="flex flex-col">
                                <span className="font-headline-sm text-headline-sm text-on-surface">{primaryName(item)}</span>
                                {secondaryName(item) && (
                                  <span className="font-body-sm text-body-sm text-on-surface-variant" dir={otherNameDirection(lang)}>{secondaryName(item)}</span>
                                )}
                                {item.active_ingredient && (
                                  <span className="font-body-sm text-body-sm text-on-surface-variant" dir="ltr">{item.active_ingredient}</span>
                                )}
                              </div>
                            </td>
                            <td className="whitespace-nowrap px-4 py-4">
                              {item.barcode ? (
                                <span className="rounded bg-surface-container px-2.5 py-1 font-mono font-label-sm text-label-sm" dir="ltr">{item.barcode}</span>
                              ) : (
                                <span className="font-label-sm text-label-sm italic text-outline">{t('inv_none_value')}</span>
                              )}
                            </td>
                            <td className="whitespace-nowrap px-4 py-4">{categoryChip(item)}</td>
                            <td className="whitespace-nowrap px-4 py-4">
                              <div className="flex flex-col gap-1.5">
                                <div className="flex items-center gap-2">
                                  <span className={`font-label-lg text-label-lg ${low ? 'text-secondary' : 'text-on-surface'}`}>{formatQty(item.stock_qty)}</span>
                                  <span className="font-body-sm text-body-sm text-on-surface-variant">/ {formatQty(item.min_threshold)}</span>
                                  {stockBadge(item)}
                                </div>
                                <div className="h-1.5 w-36 overflow-hidden rounded-full bg-surface-container-high">
                                  <div className={`h-full rounded-full ${low ? 'bg-secondary' : 'bg-primary'}`} style={{ width: `${stockPercent(item)}%` }} />
                                </div>
                              </div>
                            </td>
                            <td className="whitespace-nowrap px-4 py-4">
                              <span className="font-stat-numeric text-[20px] text-on-surface">{item.unit_sell_price.toFixed(2)}</span>
                              <span className="ms-1 font-label-sm text-label-sm text-on-surface-variant">{t('currency')}</span>
                            </td>
                            <td className="whitespace-nowrap px-4 py-4">
                              <div className="flex flex-col items-start gap-1">
                                <span>{item.expiry_date ? item.expiry_date.slice(0, 10) : '—'}</span>
                                {expiryBadge(item)}
                              </div>
                            </td>
                            <td className="whitespace-nowrap px-4 py-4 text-end">
                              <div className="flex items-center justify-end gap-1">
                                <Link
                                  href={`/inventory/${item.id}/edit`}
                                  className="inline-flex h-9 items-center gap-1 rounded bg-surface px-2.5 font-label-md text-label-md text-primary transition-colors hover:bg-surface-container"
                                >
                                  <span className="material-symbols-outlined text-[16px]" aria-hidden="true">edit</span>
                                  {t('edit')}
                                </Link>
                                <Link
                                  href={`/inventory/${item.id}/restock`}
                                  className="inline-flex h-9 items-center gap-1 rounded bg-secondary-container px-2.5 font-label-md text-label-md text-on-secondary-container transition-colors hover:bg-secondary-fixed"
                                >
                                  <span className="material-symbols-outlined text-[16px]" aria-hidden="true">add_shopping_cart</span>
                                  {t('inv_restock')}
                                </Link>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-space-md flex flex-col items-center gap-2 font-body-sm text-body-sm text-on-surface-variant">
                <span>
                  {t('inv_showing').replace('{shown}', String(shown.length)).replace('{total}', String(filtered.length))}
                </span>
                {filtered.length > shown.length && (
                  <button
                    type="button"
                    onClick={() => setVisible((v) => v + PAGE_SIZE)}
                    className={`${actionClasses} bg-surface-container-high text-on-surface`}
                  >
                    {t('inv_show_more')}
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </main>

      <BottomNav />
    </div>
  );
}

export default function InventoryCatalogPage() {
  // useSearchParams needs a Suspense boundary for the production build.
  return (
    <Suspense fallback={null}>
      <InventoryCatalog />
    </Suspense>
  );
}