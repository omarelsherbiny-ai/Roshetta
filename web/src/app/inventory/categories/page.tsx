// web/src/app/inventory/categories/page.tsx  (route: /inventory/categories — category cards)
'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { CategoryCreateModal } from '@/components/inventory/CategoryCreateModal';
import { getCategoryDetails, getInventory } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { CategoryDetail, InventoryItemSchema } from '@/types';

interface CategoryCardInfo {
  name: string;
  count: number;
}

export default function CategoryManagerPage() {
  const router = useRouter();
  const { t, dir, isRTL } = useLanguage();

  const [categoryDetails, setCategoryDetails] = useState<CategoryDetail[]>([]);
  const [items, setItems] = useState<InventoryItemSchema[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    loadData();
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const showToast = (message: string) => {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3500);
  };

  const handleCategorySaved = (name: string) => {
    setShowCreateModal(false);
    showToast(t('cat_saved').replace('{name}', name));
    void loadData();
  };

  const handleUseExisting = (name: string) => {
    setShowCreateModal(false);
    setSearchQuery(name);
  };

  const loadData = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [catsData, itemsData] = await Promise.all([getCategoryDetails(), getInventory()]);
      setCategoryDetails(catsData);
      setItems(itemsData);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('cat_load_error'));
    } finally {
      setIsLoading(false);
    }
  };

  const categories = useMemo(() => categoryDetails.map((cat) => cat.name), [categoryDetails]);

  // Counts come from the server so a category with no product still shows (with 0).
  const categoryCards = useMemo<CategoryCardInfo[]>(() => {
    return categoryDetails.map((cat) => ({
      name: cat.name,
      count: cat.item_count,
    }));
  }, [categoryDetails]);

  const filteredCards = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return categoryCards;
    return categoryCards.filter((c) => c.name.toLowerCase().includes(q));
  }, [categoryCards, searchQuery]);

  return (
    <div className="bg-surface text-on-surface font-body-md text-body-md flex flex-col min-h-screen">
      <TopHeader
        pharmacyName={t('cat_page_title')}
        subtitle={t('cat_page_subtitle')}
        showBack={true}
      />

      <main className="flex flex-col relative w-full pt-16 pb-28 px-margin bg-surface flex-grow">
        <div className="flex flex-col w-full pb-6 select-none" dir={dir}>
          {/* Top Context & Summary Bar */}
          <div className="flex items-center justify-between gap-space-sm mb-space-md">
            <div className="flex items-center gap-space-sm min-w-0">
              <button
                type="button"
                aria-label={t('back')}
                onClick={() => router.back()}
                className="w-touch-target-min h-touch-target-min rounded-full flex items-center justify-center bg-surface-container hover:bg-surface-container-high text-on-surface active:scale-95 transition-all shadow-sm"
              >
                <span className="material-symbols-outlined text-[24px]">
                  {isRTL ? 'arrow_forward' : 'arrow_back'}
                </span>
              </button>
              <div className="flex flex-col min-w-0">
                <h1 className="font-headline-sm text-headline-sm text-on-surface truncate">
                  {t('cat_page_title')}
                </h1>
                <p className="font-body-sm text-body-sm text-on-surface-variant flex items-center gap-1">
                  <span>{t('cat_page_hint')}</span>
                </p>
              </div>
            </div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary-fixed text-on-primary-fixed font-label-md text-label-md shadow-sm">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
              <span>
                {t('cat_count_badge').replace('{count}', String(categories.length))}
              </span>
            </div>
          </div>

          {loadError && (
            <div role="alert" className="mb-space-md flex items-center justify-between gap-3 rounded-xl bg-error-container p-3 text-sm text-on-error-container">
              <span>{loadError}</span>
              <button type="button" onClick={() => void loadData()} disabled={isLoading} className="min-h-10 shrink-0 rounded-lg px-3 font-semibold underline disabled:opacity-60">
                {t('cat_retry')}
              </button>
            </div>
          )}

          {/* Categories are derived from saved product records. */}
          <div className="flex flex-col gap-space-sm mb-space-lg">
            <div className="flex items-center gap-space-sm">
              <div className="relative min-w-0 flex-1">
                <div className={`absolute inset-y-0 ${isRTL ? 'start-0 ps-3.5' : 'end-0 pe-3.5'} flex items-center pointer-events-none text-outline`}>
                  <span className="material-symbols-outlined text-[22px]">search</span>
                </div>
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t('cat_search_placeholder')}
                  className="w-full h-12 ps-11 pe-12 bg-surface-container-lowest text-on-surface placeholder:text-outline rounded-xl font-body-md text-body-md shadow-sm focus:bg-surface-container-low focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary transition-all"
                />
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                disabled={isLoading || !!loadError}
                className="inline-flex h-12 shrink-0 items-center gap-1.5 rounded-xl bg-primary px-4 font-label-lg text-label-lg text-on-primary shadow-sm transition-all hover:bg-primary-container active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[20px]" aria-hidden="true">add</span>
                {t('cat_new')}
              </button>
            </div>

          </div>

          {/* 2-Column Responsive Grid */}
          <div className="grid grid-cols-2 gap-space-sm mb-space-xl">
            {isLoading ? (
              <div className="col-span-2 flex items-center justify-center gap-2 py-12 text-on-surface-variant" role="status">
                <span className="material-symbols-outlined animate-spin text-primary">progress_activity</span>
                {t('cat_loading')}
              </div>
            ) : loadError ? null : filteredCards.length === 0 ? (
              <div className="col-span-2 text-center py-12 text-on-surface-variant">
                {searchQuery.trim()
                  ? t('cat_none_match')
                  : t('cat_none_yet')}
              </div>
            ) : (
              filteredCards.map((card) => (
                <Link
                  key={card.name}
                  href={`/inventory?category=${encodeURIComponent(card.name)}`}
                  aria-label={t('cat_view_products').replace('{name}', card.name)}
                  className="category-card group relative flex flex-col justify-between p-space-sm bg-surface-container-lowest rounded-xl shadow-sm hover:shadow-md transition-all active:scale-[0.99] overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="w-11 h-11 rounded-lg flex items-center justify-center shadow-sm bg-surface-container text-primary">
                      <span className="material-symbols-outlined text-[24px]">category</span>
                    </div>
                  </div>
                  <div>
                    <h3 className="font-headline-sm text-headline-sm text-on-surface line-clamp-1 mb-2">
                      {card.name}
                    </h3>
                  </div>
                  <div className="flex items-center justify-between pt-2 mt-auto">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container text-on-surface-variant font-label-sm text-label-sm">
                      <span className="material-symbols-outlined text-[14px]">inventory_2</span>
                      {t('cat_item_count').replace('{count}', String(card.count))}
                    </span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </main>

      {showCreateModal && (
        <CategoryCreateModal
          categories={categories}
          initialItems={items}
          onClose={() => setShowCreateModal(false)}
          onUseExisting={handleUseExisting}
          onSaved={handleCategorySaved}
        />
      )}

      {toast && (
        <div role="status" className="pointer-events-none fixed inset-x-0 bottom-24 z-[80] flex justify-center px-margin">
          <div className="pointer-events-auto rounded-xl bg-inverse-surface px-4 py-3 font-body-md text-body-md text-inverse-on-surface shadow-lg">
            {toast}
          </div>
        </div>
      )}

      <BottomNav />
    </div>
  );
}