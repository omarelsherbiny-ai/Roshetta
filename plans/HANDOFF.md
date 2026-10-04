# Roshetta missing screen states — implementation handoff

This package contains a responsive visual prototype for three additions to the existing Roshetta app. It is a screen design reference, not production UI code. Open `prototype.html` in a browser. Use the language control to review English LTR and Arabic RTL layouts.

## Included

1. **Product identification camera state** — camera-specific view for identifying a medicine pack, with a scan action. It is separate from prescription/invoice scanning.
2. **Product extraction review state** — editable values for Arabic and English product name, active ingredient, barcode, purchase and selling prices, expiry date, and opening stock quantity. It includes verify-before-save guidance and a compact add confirmation.
3. **Blocked action state** — explains that a sale was stopped because a product was not matched, confirms no write occurred, and provides a direct path to Add Product.
4. **Compact action success state** — a small inline confirmation for a completed sale with the recorded item and total.

The two product states extend the existing `/inventory/new` flow. The blocked and success states belong in the existing assistant conversation/action lifecycle. They do not introduce a new dashboard or change the existing app shell.

## Deliberately not redesigned

- Welcome, login, create pharmacy, and join pharmacy are already represented by `web/src/app/onboarding/page.tsx` and `web/src/components/auth/LoginModal.tsx`.
- Product creation already has a dedicated route at `web/src/app/inventory/new/page.tsx` using `web/src/components/inventory/ProductForm.tsx`.
- Action review already exists in `web/src/components/cards/ActionProposalCard.tsx`, rendered by `web/src/components/chat/MessageBubble.tsx`.
- Recent transactions already appear on the dashboard (`web/src/app/page.tsx`) and detailed financial activity has its own records page (`web/src/app/records/page.tsx`). The backend also exposes `GET /api/staff/me/activity`, an audit feed scoped to the signed-in actor across their recorded pharmacy actions. It is not a pharmacy-wide audit feed and cannot show actions performed by other members.

Those screens and components should be kept visually intact. The proposed additions are missing states and a product-specific camera/review path, not replacements for existing screens.

## Backend field alignment

The product review fields map to `InventoryItem` in `server/app/db/models/__init__.py` and `ProductPayload` in `server/app/api/inventory.py`: `name_ar`, `name_en`, `active_ingredient`, `barcode`, `category`, `unit_buy_price`, `unit_sell_price`, `expiry_date`, `stock_qty`, and `min_threshold`. The prototype shows fields supported by the current backend. Do not add dosage form, strength, lot/batch number, or shelf location without a backend/schema change; those are not persisted today.

The current `/api/ocr/product-box` handler in `server/app/api/ocr.py` fails closed with HTTP 503 because no OCR provider adapter is configured. It does not return extracted or sample values. The camera and extraction shown here are target states; real computer vision/OCR and reliable confidence/error handling still need implementation. Once a provider is configured, keep extracted values editable and require user review before saving.

The blocked-action design corresponds to `agents/agents/verification.py` rejecting a sale when a product is missing. The “Add product” action can route to the existing product creation page. After return, the user should retry the original action so it can be matched and reviewed again.

The success message is a compact state after the existing confirm endpoint succeeds (`server/app/api/actions.py`). Do not show it before the server confirms the write. The prototype's buttons demonstrate layout only and do not call APIs.

## Locale note

The app has a partial language helper in `web/src/lib/i18n.ts`, but it does not provide complete application-wide localization. This prototype includes sample English and Arabic text plus `dir="ltr"`/`dir="rtl"` behavior to show the intended layouts. It does not make the project locale-capable. Implementation still needs a complete string catalog, persisted language preference, direction handling, localized validation/errors/loading states, and checks for mixed-direction values such as barcodes, phone numbers, and prices.

## Existing Roshetta styling used

The prototype follows the source tokens in `web/tailwind.config.ts` and `web/src/app/globals.css`: Roshetta green surfaces, Material 3 surface hierarchy, rounded white cards, Noto Sans/Tajawal font family, the 16px mobile page margin, touch-sized controls, sticky Roshetta header, five-item bottom navigation, and safe-area insets. The four screen examples use the current pharmacy name/header conventions and no new navigation system.

## Responsive and interaction notes

- Mobile is the primary target; desktop arranges separate phone frames for review only.
- The language control switches all prototype copy and page direction.
- Long product names wrap; input values remain editable; barcode/amount examples stay LTR.
- Product scan and save controls illustrate state transitions locally. Production implementation must connect the existing upload and product-create APIs and provide genuine loading, validation, OCR failure, and success states.
- The blocked state has no confirm control. Its next action is Add Product; returning to the assistant must preserve enough context to retry safely.

## Source files to revisit during implementation

- `web/src/app/inventory/new/page.tsx`
- `web/src/components/inventory/ProductForm.tsx`
- `web/src/app/inventory/page.tsx`
- `web/src/lib/api.ts`
- `web/src/lib/i18n.ts`
- `web/src/app/assistant/page.tsx`
- `web/src/components/chat/MessageBubble.tsx`
- `web/src/components/cards/ActionProposalCard.tsx`
- `server/app/api/ocr.py`
- `server/app/api/inventory.py`
- `server/app/api/actions.py`
- `agents/agents/verification.py`
