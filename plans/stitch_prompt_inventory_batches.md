# Stitch prompt: Roshetta multi-price batches, inventory valuation, and stock restock screens

Extend the existing Roshetta Pharmacy Assistant design system using the supplied Roshetta screen references, color tokens, and Material 3 surface hierarchy. Generate production-ready responsive screen designs for desktop and mobile, with complete English LTR and Arabic RTL variants. Keep the same navigation, typography, spacing, colors, and component language as the supplied app.

Create these screens and connected states:

1. **Create new product definition (`/inventory/new`)**
   - Fields: Arabic brand name, English brand name, active ingredient, category (autocomplete from existing catalog categories), barcode (with validation disclaimer), minimum low-stock alert threshold, initial purchase cost (EGP), initial official selling price (EGP), expiry date (YYYY-MM-DD), and optional initial batch/lot number.
   - States: pristine empty form, validation error on duplicate barcode / blank names, saving spinner, success confirmation.
   - Guardrails: explain that this registers the medicine definition and creates its opening stock batch if quantity > 0.

2. **Add / restock product intake (`/inventory/[id]/restock`)**
   - Context card: verified medicine identity, active ingredient, barcode chip, and current warehouse stock count.
   - Intake stepper: large numeric quantity input with quick-add buttons (+10, +24, +50, +100).
   - Batch parameters: supplier unit buy price, official unit sell price, batch/lot number, expiry date.
   - Live ledger preview: total intake cost calculation (quantity × buy price), projected new warehouse stock, and gross profit margin.
   - Active stock batches list: display previously recorded batches for this item showing batch number, remaining quantity, buy/sell prices, expiry date, and batch subtotal valuation.
   - Action bar: sticky bottom confirmation button with ledger posting indicator and cancel/back button.

3. **Dense inventory valuation & catalog overview (`/inventory/overview`)**
   - High-impact bento summary header:
     - Total potential sales value (EGP) with "Live DB" indicator.
     - Total units in stock (packages).
     - Registered SKUs count.
     - Critical low-stock count needing restock.
   - Search & category filter: live text search by brand/generic/barcode, plus horizontally scrollable category chips showing item counts.
   - Inventory price & valuation grid: dense table comparing each item:
     - Brand & generic name with barcode chip.
     - Stock quantity and status badge (green for healthy, amber for low stock).
     - Unit sell price (EGP).
     - Subtotal inventory valuation (`stock_qty × unit_sell_price`).
     - Quick restock action button leading directly to `/inventory/[id]/restock`.
   - Sticky bottom valuation bar: count of filtered items shown and aggregate valuation sum of displayed rows.

4. **Product batches detail modal / sheet**
   - Shows all active and depleted lots/batches for a single medicine.
   - Each row details: batch number, quantity remaining, acquisition unit cost, retail sell price, expiry date, and FIFO depletion order.
   - Visual indicator for batches near expiration or depleted (quantity = 0).

Use real-data states throughout: loading skeleton, empty category, error retry, and zero-stock states. Do not add demo controls, fake avatars, placeholder addresses, or fabricated metrics. Do not imply any transaction was written to the ledger until the server returns HTTP 200. Preserve accessible labels, keyboard focus, touch-sized controls, long Arabic text wrapping, and LTR presentation of barcodes, dates, times, and amounts inside RTL layouts.

Return separate named frames for each screen at mobile (375px/390px) and desktop (1280px+) sizes, and provide both the English and Arabic variant for every frame.

Backend data contract:
- Catalog list & search: `GET /api/inventory/items`
- Active categories: `GET /api/inventory/categories`
- Catalog valuation summary: `GET /api/inventory/summary`
- Item detail: `GET /api/inventory/items/{id}`
- Item batches: `GET /api/inventory/items/{id}/batches` (`id`, `batch_number`, `quantity`, `unit_buy_price`, `unit_sell_price`, `expiry_date`, `total_cost`, `total_retail`, `created_at`)
- Item price changes: `GET /api/inventory/items/{id}/price-history`
- Create product: `POST /api/inventory/create` (`name_ar`, `name_en`, `active_ingredient`, `category`, `barcode`, `stock_qty`, `min_threshold`, `unit_buy_price`, `unit_sell_price`, `expiry_date`, `batch_number`)
- Direct restock: `POST /api/inventory/items/{id}/restock` (`quantity`, `unit_buy_price`, `unit_sell_price`, `batch_number`, `expiry_date`, `supplier_notes`)
- Currency: EGP only.
