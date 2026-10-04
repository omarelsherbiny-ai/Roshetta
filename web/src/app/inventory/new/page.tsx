// web/src/app/inventory/new/page.tsx (route: /inventory/new — product creation, wraps ProductForm)
'use client';

import React from 'react';
import { ProductForm, ProductFormData } from '@/components/inventory/ProductForm';
import { createNewProduct } from '@/lib/api';

export default function NewProductPage() {
  const handleCreate = async (data: ProductFormData) => {
    await createNewProduct({
      name_ar: data.name_ar,
      name_en: data.name_en,
      active_ingredient: data.active_ingredient,
      category: data.category,
      barcode: data.barcode || undefined,
      stock_qty: data.stock_qty,
      min_threshold: data.min_threshold,
      unit_buy_price: data.unit_buy_price,
      unit_sell_price: data.unit_sell_price,
      expiry_date: data.expiry_date,
      batch_number: data.batch_number || undefined,
    });
  };

  return <ProductForm isEdit={false} onSubmit={handleCreate} />;
}