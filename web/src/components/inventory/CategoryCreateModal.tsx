// web/src/components/inventory/CategoryCreateModal.tsx (modal: add a category by name, assign it to a product, or continue to a new product)
'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import Link from 'next/link';
import { createCategory, getInventoryItems, setItemCategory } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { pickLocalizedName } from '@/lib/languages';
import { InventoryItemSchema } from '@/types';

const NAME_MAX = 40;
const SEARCH_DEBOUNCE_MS = 350;
const MAX_VISIBLE = 30;
const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

type Mode = 'name' | 'assign' | 'create';

interface CategoryCreateModalProps {
  /** Existing category names (real data from the server) used for the duplicate check. */
  categories: string[];

  /** Products already loaded by the page; shown while the search box is empty. */
  initialItems: InventoryItemSchema[];

  onClose: () => void;

  /** Duplicate name: the page closes the modal and filters to the existing category. */
  onUseExisting: (name: string) => void;

  /** Category saved (on its own or on a product); the page shows the toast, closes the modal, refreshes. */
  onSaved: (name: string) => void;
}

function normalizeName(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

export function CategoryCreateModal({
  categories,
  initialItems,
  onClose,
  onUseExisting,
  onSaved,
}: CategoryCreateModalProps) {
  const { lang, t, dir } = useLanguage();

  const uid = useId();

  const titleId = `${uid}-title`;
  const hintId = `${uid}-hint`;
  const nameId = `${uid}-name`;
  const dupId = `${uid}-dup`;
  const helpId = `${uid}-help`;

  const noProducts = initialItems.length === 0;

  const [mode, setMode] = useState<Mode>('name');
  const [name, setName] = useState('');
  const [query, setQuery] = useState('');

  const [results, setResults] = useState<InventoryItemSchema[] | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  const [selected, setSelected] =
    useState<InventoryItemSchema | null>(null);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const dialogRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const requestRef = useRef(0);

  const normalized = normalizeName(name);

  const nameValid =
    normalized.length > 0 && normalized.length <= NAME_MAX;

  const existingCategory = nameValid
    ? categories.find(
        (category) =>
          category.trim().toLowerCase() === normalized.toLowerCase(),
      ) ?? null
    : null;

  const nameOk = nameValid && !existingCategory;

  const canSave =
    (mode === 'name' || mode === 'assign') &&
    nameOk &&
    (mode === 'name' || selected !== null) &&
    !saving;

  const blockReason = !nameOk
    ? t('cat_help_name')
    : mode === 'assign' && !selected
      ? t('cat_help_product')
      : null;

  const itemName = (item: InventoryItemSchema) =>
    pickLocalizedName(lang, item.name_ar, item.name_en);

  /*
   * Focus management + body scroll lock.
   */
  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    const previousOverflow = document.body.style.overflow;

    document.body.style.overflow = 'hidden';

    nameRef.current?.focus();

    return () => {
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, []);

  /*
   * Debounced server-side product search.
   *
   * Empty query uses the products already loaded by the page.
   */
  useEffect(() => {
    if (mode !== 'assign') {
      return;
    }

    const q = query.trim();

    if (!q) {
      requestRef.current += 1;
      setResults(null);
      setListLoading(false);
      setListError(null);
      return;
    }

    const requestId = ++requestRef.current;

    setListLoading(true);
    setListError(null);

    const timer = window.setTimeout(async () => {
      try {
        const data = await getInventoryItems(q);

        if (requestRef.current === requestId) {
          setResults(data);
        }
      } catch (error) {
        if (requestRef.current === requestId) {
          setListError(
            error instanceof Error
              ? error.message
              : t('cat_list_error'),
          );
        }
      } finally {
        if (requestRef.current === requestId) {
          setListLoading(false);
        }
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };

    // t is intentionally not included because changing language
    // should not restart an active search request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, mode, retryTick]);

  const requestClose = () => {
    if (!saving) {
      onClose();
    }
  };

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLDivElement>,
  ) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      requestClose();
      return;
    }

    if (event.key !== 'Tab') {
      return;
    }

    const nodes =
      dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);

    if (!nodes || nodes.length === 0) {
      return;
    }

    const first = nodes[0];
    const last = nodes[nodes.length - 1];

    if (
      event.shiftKey &&
      document.activeElement === first
    ) {
      event.preventDefault();
      last.focus();
    } else if (
      !event.shiftKey &&
      document.activeElement === last
    ) {
      event.preventDefault();
      first.focus();
    }
  };

  const handleSave = async () => {
    if (!canSave) {
      return;
    }

    setSaving(true);
    setSaveError(null);

    try {
      if (mode === 'name') {
        await createCategory(normalized);
      } else if (selected) {
        await setItemCategory(selected.id, normalized);
      }

      onSaved(normalized);
    } catch (error) {
      setSaveError(
        error instanceof Error
          ? error.message
          : t('cat_error_title'),
      );

      setSaving(false);
    }
  };

  const source = query.trim() ? results : initialItems;

  const visible = source
    ? source.slice(0, MAX_VISIBLE)
    : [];

  const hasMore = source
    ? source.length > MAX_VISIBLE
    : false;

  const focusRing =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center"
      dir={dir}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-inverse-surface/40"
        onClick={requestClose}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={hintId}
        aria-busy={saving}
        onKeyDown={handleKeyDown}
        className="relative flex max-h-[90vh] w-full flex-col rounded-t-xl bg-surface-container-lowest shadow-lg sm:max-w-lg sm:rounded-xl"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-space-sm px-margin pt-margin pb-space-sm">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="font-headline-md text-headline-md text-on-surface"
            >
              {t('cat_modal_title')}
            </h2>

            <p
              id={hintId}
              className="font-body-sm text-body-sm text-on-surface-variant"
            >
              {t('cat_modal_hint')}
            </p>
          </div>

          <button
            type="button"
            onClick={requestClose}
            disabled={saving}
            aria-label={t('cat_close')}
            className={`flex h-touch-target-min w-touch-target-min shrink-0 items-center justify-center rounded-full text-on-surface hover:bg-surface-container disabled:opacity-50 ${focusRing}`}
          >
            <span
              className="material-symbols-outlined text-[24px]"
              aria-hidden="true"
            >
              close
            </span>
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-col gap-space-md overflow-y-auto px-margin pb-space-md">
          {/* Category name */}
          <div className="flex flex-col gap-space-xs">
            <label
              htmlFor={nameId}
              className="font-label-lg text-label-lg text-on-surface"
            >
              {t('cat_name_label')}
            </label>

            <input
              id={nameId}
              ref={nameRef}
              type="text"
              value={name}
              maxLength={NAME_MAX}
              disabled={saving}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('cat_name_placeholder')}
              aria-invalid={existingCategory ? true : undefined}
              aria-describedby={
                existingCategory ? dupId : undefined
              }
              className={`h-12 w-full rounded-xl bg-surface-container-low px-3.5 font-body-md text-body-md text-on-surface placeholder:text-outline disabled:opacity-60 ${focusRing}`}
            />

            {existingCategory && (
              <div
                id={dupId}
                role="alert"
                className="flex items-center justify-between gap-3 rounded-xl bg-error-container p-3 font-body-sm text-body-sm text-on-error-container"
              >
                <span>{t('cat_err_duplicate')}</span>

                <button
                  type="button"
                  onClick={() =>
                    onUseExisting(existingCategory)
                  }
                  disabled={saving}
                  className={`min-h-10 shrink-0 rounded-lg px-3 font-label-lg text-label-lg underline ${focusRing}`}
                >
                  {t('cat_use_existing')}
                </button>
              </div>
            )}
          </div>

          {/* Mode */}
          <fieldset
            className="flex flex-col gap-space-xs"
            disabled={saving}
          >
            <legend className="mb-space-xs font-label-lg text-label-lg text-on-surface">
              {t('cat_mode_label')}
            </legend>

            <div className="grid grid-cols-1 gap-space-sm sm:grid-cols-3">
              {(['name', 'assign', 'create'] as Mode[]).map((m) => {
                const disabled =
                  m === 'assign' && noProducts;

                return (
                  <label
                    key={m}
                    className={`relative block ${
                      disabled
                        ? 'opacity-50'
                        : 'cursor-pointer'
                    }`}
                  >
                    <input
                      type="radio"
                      name={`${uid}-mode`}
                      value={m}
                      checked={mode === m}
                      disabled={disabled}
                      onChange={() => setMode(m)}
                      className="peer sr-only"
                    />

                    <span className="flex min-h-touch-target-min items-center justify-center rounded-xl bg-surface-container-low px-3 text-center font-label-lg text-label-lg text-on-surface-variant ring-2 ring-transparent peer-checked:bg-primary-fixed peer-checked:text-on-primary-fixed peer-focus-visible:ring-primary">
                      {m === 'name'
                        ? t('cat_mode_name')
                        : m === 'assign'
                          ? t('cat_mode_assign')
                          : t('cat_mode_create')}
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {/* Assign mode */}
          {mode === 'assign' ? (
            <div className="flex flex-col gap-space-sm">
              <input
                type="search"
                value={query}
                disabled={saving}
                onChange={(event) =>
                  setQuery(event.target.value)
                }
                placeholder={t('cat_product_search')}
                aria-label={t('cat_product_search')}
                className={`h-12 w-full rounded-xl bg-surface-container-low px-3.5 font-body-md text-body-md text-on-surface placeholder:text-outline disabled:opacity-60 ${focusRing}`}
              />

              <fieldset disabled={saving}>
                <legend className="sr-only">
                  {t('cat_products_label')}
                </legend>

                {/* Error */}
                {listError ? (
                  <div
                    role="alert"
                    className="flex items-center justify-between gap-3 rounded-xl bg-error-container p-3 font-body-sm text-body-sm text-on-error-container"
                  >
                    <span>{listError}</span>

                    <button
                      type="button"
                      onClick={() =>
                        setRetryTick((n) => n + 1)
                      }
                      className={`min-h-10 shrink-0 rounded-lg px-3 font-label-lg text-label-lg underline ${focusRing}`}
                    >
                      {t('cat_retry')}
                    </button>
                  </div>
                ) : /* Loading */
                listLoading ||
                  (query.trim() && results === null) ? (
                  <div
                    className="flex flex-col gap-space-sm"
                    role="status"
                    aria-label={t('cat_products_label')}
                  >
                    {[0, 1, 2].map((n) => (
                      <div
                        key={n}
                        className="h-16 animate-pulse rounded-xl bg-surface-container"
                      />
                    ))}
                  </div>
                ) : /* Empty */
                visible.length === 0 ? (
                  <p className="rounded-xl bg-surface-container-low p-space-md text-center font-body-md text-body-md text-on-surface-variant">
                    {t('cat_no_results')}
                  </p>
                ) : (
                  /* Products */
                  <div className="flex max-h-64 flex-col gap-space-sm overflow-y-auto">
                    {visible.map((item) => (
                      <label
                        key={item.id}
                        className="relative block cursor-pointer"
                      >
                        <input
                          type="radio"
                          name={`${uid}-product`}
                          value={item.id}
                          checked={
                            selected?.id === item.id
                          }
                          onChange={() =>
                            setSelected(item)
                          }
                          className="peer sr-only"
                        />

                        <span className="flex items-center justify-between gap-space-sm rounded-xl bg-surface-container-low p-space-sm ring-2 ring-transparent peer-checked:bg-primary-fixed peer-checked:ring-primary peer-focus-visible:ring-primary">
                          <span className="flex min-w-0 flex-col">
                            <span className="truncate font-label-lg text-label-lg text-on-surface">
                              {itemName(item)}
                            </span>

                            <span className="truncate font-body-sm text-body-sm text-on-surface-variant">
                              {item.category ||
                                t('cat_no_category')}
                            </span>
                          </span>

                          <span className="flex shrink-0 flex-col items-end">
                            <span className="font-label-md text-label-md text-on-surface">
                              {t('cat_stock')}:{' '}
                              {Number(item.stock_qty)}
                            </span>

                            <span className="font-body-sm text-body-sm text-on-surface-variant">
                              {Number(
                                item.unit_sell_price,
                              ).toFixed(2)}{' '}
                              {t('currency')}
                            </span>
                          </span>
                        </span>
                      </label>
                    ))}

                    {hasMore && (
                      <p className="px-1 font-body-sm text-body-sm text-on-surface-variant">
                        {t('cat_more_results')}
                      </p>
                    )}
                  </div>
                )}
              </fieldset>

              {/* Category move warning */}
              {selected?.category &&
                selected.category.trim().toLowerCase() !==
                  normalized.toLowerCase() && (
                  <p className="font-body-sm text-body-sm text-on-surface-variant">
                    {t('cat_moves_from').replace(
                      '{name}',
                      selected.category,
                    )}
                  </p>
                )}
            </div>
          ) : mode === 'name' ? (
            /* Name-only mode: the category is saved now, empty */
            <p className="rounded-xl bg-surface-container-low p-space-md font-body-md text-body-md text-on-surface-variant">
              {t('cat_name_note')}
            </p>
          ) : (
            /* Create mode */
            <p className="rounded-xl bg-surface-container-low p-space-md font-body-md text-body-md text-on-surface-variant">
              {noProducts
                ? t('cat_no_products')
                : t('cat_create_note')}
            </p>
          )}

          {/* Save error */}
          {saveError && (
            <div
              role="alert"
              className="flex flex-col gap-1 rounded-xl bg-error-container p-3 text-on-error-container"
            >
              <p className="font-label-lg text-label-lg">
                {t('cat_error_title')}
              </p>

              <div className="flex items-center justify-between gap-3">
                <span className="font-body-sm text-body-sm">
                  {saveError}
                </span>

                <button
                  type="button"
                  onClick={() => void handleSave()}
                  disabled={saving}
                  className={`min-h-10 shrink-0 rounded-lg px-3 font-label-lg text-label-lg underline ${focusRing}`}
                >
                  {t('cat_retry')}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex flex-col gap-space-sm border-t border-outline-variant px-margin pt-space-md"
          style={{
            paddingBottom:
              'max(1rem, env(safe-area-inset-bottom))',
          }}
        >
          {blockReason && (
            <p
              id={helpId}
              className="font-body-sm text-body-sm text-on-surface-variant"
            >
              {blockReason}
            </p>
          )}

          <div className="flex gap-space-sm">
            {/* Cancel */}
            <button
              type="button"
              onClick={requestClose}
              disabled={saving}
              className={`h-touch-target-min flex-1 rounded-xl bg-surface-container font-label-lg text-label-lg text-on-surface hover:bg-surface-container-high disabled:opacity-50 ${focusRing}`}
            >
              {t('cancel')}
            </button>

            {/* Save / Continue */}
            {mode === 'assign' || mode === 'name' ? (
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={!canSave}
                aria-describedby={
                  blockReason ? helpId : undefined
                }
                className={`h-touch-target-min flex-1 rounded-xl bg-primary font-label-lg text-label-lg text-on-primary disabled:opacity-50 ${focusRing} focus-visible:ring-offset-2`}
              >
                {saving ? t('cat_saving') : t('save')}
              </button>
            ) : nameOk ? (
              <Link
                href={`/inventory/new?category=${encodeURIComponent(
                  normalized,
                )}`}
                className={`flex h-touch-target-min flex-1 items-center justify-center rounded-xl bg-primary font-label-lg text-label-lg text-on-primary ${focusRing} focus-visible:ring-offset-2`}
              >
                {t('cat_continue')}
              </Link>
            ) : (
              <button
                type="button"
                disabled
                aria-describedby={helpId}
                className="h-touch-target-min flex-1 rounded-xl bg-primary font-label-lg text-label-lg text-on-primary opacity-50"
              >
                {t('cat_continue')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}