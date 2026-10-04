// web/src/app/inventory/[id]/edit/page.tsx (route: /inventory/[id]/edit — product edit, wraps ProductForm)
'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProductForm, ProductFormData } from '@/components/inventory/ProductForm';
import { getInventoryItem, updateProduct } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';

export default function EditProductPage() {
  const params = useParams();
  const router = useRouter();
  const { dir, t } = useLanguage();
  const itemId = Number(params?.id);

  const [loading, setLoading] = useState(true);
  const [initialData, setInitialData] = useState<Partial<ProductFormData> | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    async function loadItem() {
      if (!itemId || isNaN(itemId)) {
        setFetchError(t('ep_invalid_id'));
        setLoading(false);
        return;
      }

      try {
        const item = await getInventoryItem(itemId);
        setInitialData({
          id: item.id,
          name_ar: item.name_ar,
          name_en: item.name_en,
          active_ingredient: item.active_ingredient || '',
          category: item.category || '',
          barcode: item.barcode || '',
          stock_qty: item.stock_qty,
          min_threshold: item.min_threshold,
          unit_buy_price: item.unit_buy_price,
          unit_sell_price: item.unit_sell_price,
          expiry_date: item.expiry_date || '',
        });
      } catch (err: any) {
        console.error('Failed to load item:', err);
        setFetchError(err.message || t('ep_load_error'));
      } finally {
        setLoading(false);
      }
    }

    loadItem();
  }, [itemId]);

  const handleUpdate = async (data: ProductFormData) => {
    await updateProduct(itemId, {
      name_ar: data.name_ar,
      name_en: data.name_en,
      active_ingredient: data.active_ingredient,
      category: data.category,
      barcode: data.barcode || undefined,
      min_threshold: data.min_threshold,
      unit_buy_price: data.unit_buy_price,
      unit_sell_price: data.unit_sell_price,
      expiry_date: data.expiry_date,
    });
  };

  if (loading) {
    return (
      <div dir={dir} className="min-h-screen bg-surface flex flex-col items-center justify-center p-4">
        <span className="material-symbols-outlined text-4xl text-primary animate-spin mb-3">
          progress_activity
        </span>
        <p className="font-body-md text-on-surface-variant">{t('ep_loading')}</p>
      </div>
    );
  }

  if (fetchError || !initialData) {
    return (
      <div dir={dir} className="min-h-screen bg-surface flex flex-col items-center justify-center p-6 text-center">
        <span className="material-symbols-outlined text-5xl text-tertiary mb-3">error</span>
        <h2 className="font-headline-sm text-on-surface mb-2">{t('ep_open_error_title')}</h2>
        <p className="font-body-md text-on-surface-variant mb-4">{fetchError}</p>
        <button
          onClick={() => router.push('/inventory')}
          className="px-6 py-2.5 rounded-lg bg-primary text-on-primary font-label-md font-bold shadow"
        >
          {t('ep_back_to_inventory')}
        </button>
      </div>
    );
  }

  return (
    <ProductForm
      isEdit={true}
      itemId={itemId}
      initialData={initialData}
      onSubmit={handleUpdate}
    />
  );
}