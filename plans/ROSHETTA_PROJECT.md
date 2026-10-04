# Meta rule: one file only

Every project `.md` doc for the Roshetta Pharmacy System lives in **this single file** (`ROSHETTA_PROJECT.md`). Anything to add, edit, or log is merged in here; there are no separate rules, notes, or changelog files. **Companion integration:** the MicroMind AI service, with its contract defined in "MicroMind / AI integration contract" below. When either side's API or data contract changes, this document is updated.

**Cleanup policy:** finished work, confirmed items, expired plans, and old history are deleted or condensed, not archived. The code is the single source of truth for anything already built. Only open work, active rules, reference facts, and unrun Stitch tasks stay.

---

## Start here

**Read this section first; everything below it is reference. Nothing here has been run in a production environment unless it says "confirmed".** Rules that always apply: Communication rules, the Stitch UI loop, and Lesson 1 (never trust an old "done" claim without verifying against the live file).

### Where the project stands
- **Web client (`web/`):** Next.js 14 App Router, TypeScript, Tailwind CSS styled with Material 3 / Pharmacy Emerald tokens. 17 routes built and verified (0 build errors):
  - Public & Onboarding: `/onboarding`, `/`, `/assistant` (chat & action proposals), `/records` (ledger transactions & activity), `/scan` (capture UI; OCR extraction safely disabled), `/prescriptions` (review list & safety alerts).
  - Inventory domain: `/inventory` (catalog list & search), `/inventory/categories` (real DB category filter & creation links), `/inventory/new` (product entry with smart duplicate scan & category pills), `/inventory/[id]/edit` (product edit), `/inventory/[id]/restock` (direct intake with stepper, quick pills, FIFO active batches list, live financial ledger preview), `/inventory/overview` (desktop/mobile 4-column KPI bento, pricing grid, batch inspector modal with real `getItemBatches` data).
  - Personal accounts & Pharmacy workspaces: `/pharmacies` (hub list, 5-pharmacy cap), `/pharmacies/[id]` (workspace details & role-gated metrics), `/pharmacies/[id]/roles` (custom role creation & scope selector), `/pharmacies/[id]/members` (staff roster, expiring single-use invite link generator), `/pharmacies/[id]/members/[userId]` (Cairo-time weekly shifts, versioned compensation terms, period work summary), `/me` (profile editor with private 5MB photo upload), `/me/activity` (personal sales, expenses, restocks summary).
- **Backend API (`server/app/`):** FastAPI async application with SQLAlchemy 2.0. SQLite by default (`roshetta.db`), `postgresql+asyncpg://` ready in `server/requirements.txt`. Routers registered: `auth`, `pharmacies`, `staff`, `me`, `inventory`, `ledger`, `actions`, `chat`, `ocr`. Interactive docs at `/docs`, status at `/health`.
- **Database & Migrations (`server/app/db/`):** Custom startup migration engine at **version 11**.
  - v4: unique partial index on non-empty barcodes per pharmacy.
  - v10: `inventory_batches` table created, legacy stock backfilled into discrete initial lots.
  - v11: obsolete reusable invitation codes cleared.
- **Inventory & FIFO Batches:** Multi-batch tracking (`InventoryBatch` model). Product creation with positive stock creates initial batch; direct restock adds new batch; sales consume oldest available batches in FIFO order (`created_at ASC, id ASC`) with `with_for_update()`; actual weighted unit acquisition cost is stamped into `LedgerEntryItem.unit_cost`. Zero-cost items leave `unit_cost=None` so `profit_complete` remains `False`.
- **Chat Assistant & LangGraph (`agents/`):** Orchestrator uses LangGraph with async `ainvoke`. Local pipeline handles intent detection, product matching, stock validation, and structured `PendingAction` proposals. Only confirmed proposals alter inventory and ledger.
- **MicroMind AI Service:** Integrated in `server/app/services/micromind.py`. Privacy-safe: only general chat text is routed externally; sensitive clinical, customer, and financial operations stay strictly on the local database path.
- **OCR Boundary:** Intentionally disabled (`OCR_PROVIDER=disabled`, returns HTTP 503). No mock/sample data returned.

### Next tasks for Claude (in order: easier to harder)
Each task represents a focused micro-task to keep token usage low while maintaining full safety.

1. **ProductForm Duplicate Scan Banner UI Refinement:** Enhance visual state styling of the newly wired debounced `matchProduct()` duplicate scanner in `ProductForm.tsx` (verified badge vs warning callout with direct link to existing item).
2. **Category Management Direct Creation Modal:** On `/inventory/categories`, allow adding a new category by assigning it to a new or existing product directly, preventing empty orphaned categories.
3. **Ledger Date Filtering in Export / Records:** Wire Cairo-local start/end date picker in `/records` into `getRecentEntries()` and `getFinancialSummary()` query params for accurate custom period auditing.
4. **Pydantic v2 `ConfigDict` Migration in `server/app/config.py`:** Replace deprecated class-based `class Config:` with Pydantic v2 `model_config = SettingsConfigDict(...)` to eliminate startup deprecation warnings.
5. **PostgreSQL Validation Against Live Service:** Set up test harness against a real PostgreSQL instance to validate `asyncpg` concurrency, partial unique indexes, and schema startup migrations.

### Waiting on Omar (copy, run, check)
Item numbers are kept as they were; gaps are finished items that were deleted.
1. **Verification suites:**
   - Run backend isolated unit/security/migration tests (57 tests):
     ```powershell
     $env:PYTHONPATH="d:\Desktop\projects\Micromind\PharmacySystem"; & "d:\Desktop\projects\Micromind\PharmacySystem\server\.venv\Scripts\python.exe" -m pytest tests -q
     ```
   - Run OpenAPI contract freshness check:
     ```powershell
     $env:PYTHONPATH="d:\Desktop\projects\Micromind\PharmacySystem"; & "d:\Desktop\projects\Micromind\PharmacySystem\server\.venv\Scripts\python.exe" scripts/export_openapi.py --check
     ```
   - Run frontend build & typecheck:
     ```powershell
     npm --prefix web run build
     ```
2. **Barcode duplicate check before live DB upgrades:**
   Run read-only query on existing SQLite/Postgres DB:
   ```sql
   SELECT pharmacy_id, barcode, COUNT(*) AS copies
   FROM inventory
   WHERE pharmacy_id IS NOT NULL AND barcode IS NOT NULL
   GROUP BY pharmacy_id, barcode
   HAVING COUNT(*) > 1;
   ```
3. **Secrets rotation:**
   Confirm `server/.env` is never committed to git, and `SERVER_SECRET_KEY` is set to a unique random 32+ character string.
4. **Live server run check:**
   Start backend:
   ```powershell
   & .\server\.venv\Scripts\Activate.ps1
   python -m uvicorn server.app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   Start frontend in separate terminal:
   ```powershell
   npm --prefix web run dev
   ```
   Open `http://localhost:3000` and spot-check:
   - Onboarding login with phone + PIN.
   - Restock screen `/inventory/[id]/restock` stepper, quick-add pills (+10, +24, +50, +100), and live ledger preview.
   - Overview `/inventory/overview` 4-column KPI bento, pricing grid, and bottom-sheet Batch modal with FIFO active/depleted cards.
   - Product form `/inventory/new` duplicate check scan and category pill selector.
5. **OCR Provider decision:**
   OCR is intentionally disabled (`OCR_PROVIDER=disabled`, returns HTTP 503). When a provider adapter (MicroMind image endpoint or external cloud OCR) is ready, provide API spec, token, and response format before activating.

### Environment variables (names only)
- **Backend (`server/.env`):** `DATABASE_URL`, `SERVER_SECRET_KEY`, `ALLOWED_ORIGINS`, `SEED_DEMO_DATA`, `USE_MICROMIND`, `MICROMIND_API_URL`, `MICROMIND_API_KEY`, `OCR_PROVIDER`, `OCR_API_URL`, `STORAGE_DRIVER`, `STORAGE_LOCAL_PATH`.
- **Frontend (`web/.env.local`):** `NEXT_PUBLIC_API_URL`.

### Domain and system reference (short; the code is the truth)
- **Multi-Tenant Model:** Every pharmacy is an isolated tenant (`pharmacies` table). All inventory, batches, ledger entries, pending actions, prescription reviews, and staff memberships are foreign-keyed to `pharmacy_id`.
- **Personal Accounts & Workspaces:** Personal accounts (`users` table) authenticate via phone number and 4-6 digit PIN. Users can own up to 5 pharmacies (enforced by DB unique slot index `owner_user_id` + `owner_slot`).
- **Roles & Delegable Scopes:**
  - Built-in roles: `owner`, `pharmacist`, `cashier`, `viewer`.
  - Custom roles: Created per pharmacy with explicit scopes (`sell_medicine`, `view_inventory`, `manage_inventory`, `restock_inventory`, `manage_staff`, `view_staff_activity`, `edit_settings`, `view_reports`).
  - Scheduling and compensation terms remain strictly owner-only.
- **Staff Invitations:** Secure, time-limited, single-use or limited-use invitation links (`pharmacy_invitations` table) storing hashed tokens. Reusable public codes and PIN-issuing invites are retired (`410 Gone`).
- **FIFO Multi-Price Batches:** Tracked in `inventory_batches`. Sales allocate stock starting from the oldest active batch (`quantity > 0`). Unit acquisition costs are weighted across consumed batches and written to `LedgerEntryItem.unit_cost`.
- **Assistant Action Proposals:** Chat proposes structured actions (`PendingAction`). Confirming an action runs the atomic database transaction: FIFO batch depletion, inventory aggregate update, `LedgerEntry` + `LedgerEntryItem` creation, and `AuditLog` write.
- **Currency & Timezone:** Currency is strictly **EGP** (`ج.م`). All business-day rollups, staff shifts, and audit timestamps use **Cairo time (`Africa/Cairo`)**.

---

## Communication rules

- When Claude needs source files it asks with a single ready-to-run command, listing only the files actually needed:

```
Run this command for me:

python scripts/collect_for_claude.py file1 file2 ...
```

- **File paths always start with their relative path from project root (`server/app/...`, `web/src/...`, `agents/...`).** The collector runs from the project root.
- **Collect rule: always the original way.** Claude asks with ONE `python scripts/collect_for_claude.py <files>` command per message; the output is `scripts/needed_files.txt` and it is uploaded under that default name. **No `Get-Content` / `Select-String` PowerShell one-liners and no custom upload names** (`needed_files2.txt` and the like), they made the exchange harder. To avoid confusion, Claude asks for ONE domain per message and asks for the next only after the previous upload has arrived. If a whole file is too big to collect, Claude says so and asks Omar to extend `collect_for_claude.py` (a line-range option) instead of falling back to PowerShell. Default output path: `scripts/needed_files.txt`.
- **File map:** `python scripts/file_map.py` (run in project root) writes `scripts/file_map.txt`, a structure-only outline of every file (never file bodies or secrets). Claude asks for it when a task needs "which file has X" instead of requesting many files.
- Claude doesn't pause to double-confirm; it implements directly. "Ready for [Feature/Step]" or any update/correction from Omar is picked up without reassurance prompts. Updates are just made.
- **Omar's core standing directives:**
  1. **"always start with easier to harder"** — order tasks strictly by complexity.
  2. **"ok next don't waste token there is a lot of tasks yet we need to make it longer but lower cost in process as small tiny tasks to reduce usage of tokens"** — work in small, focused micro-tasks.
  3. **"always make sure no virtual data or defined text in code always get real data from databases or whatever it comes from"** — zero hardcoded dummy data, zero placeholder mock values. Everything connects to real backend APIs and DB models.
  4. **"dont create anything from your own in ui always give prompt to get stitch make screen for you for both website and phone version"** — all new visual layouts/screens must go through the Stitch prompt loop first.
  5. **"For micromind we should do all necessary ai models there for now"** — MicroMind client in `server/app/services/micromind.py` is the hub for external AI models.
  6. **"check always security and safety and possible bugs for long term app live"** — maintain multi-tenant isolation, row locking, input validation, and secure auth.
- **Auto-pick rule:** when several approaches exist and none is specified, Claude picks the simpler one, says which and why in one line, and moves on.
- **Any UI/visual change goes through the Stitch loop first (absolute; steps in "UI/UX handling (Stitch loop)" right below).** New layout, component, page, restyling, responsive treatment, information density, missing/awkward states. Claude never invents or "quickly improves" a visual/layout decision from its own design sense, and never quietly reclassifies a design problem as a quick fix. Non-visual work (wiring markup to real data, JS behaviour on an existing element, bug fixes, backend/contract work, copy/value corrections on existing markup) proceeds directly. If a bug report is ambiguous between wiring and design, Claude asks for the Stitch `.zip` or screen HTML by name instead of guessing.
- **Stitch prompts are never stored in this `.md` or any file, at all (Omar's rule).** Whenever Claude writes or revises a Stitch prompt, it sends the ready-to-paste text in the chat reply only, in one code block. No prompt text, no copy of it, no "prompts ready to run" section. Once Omar has run a prompt the text is gone; if he needs it again he asks and Claude writes it again from the real fields. What is still open (which design is waiting) is tracked as plain task lines in "Next tasks for Claude", without prompt text.
- Whenever a file is open, Claude flags anything suspicious it notices, even if unrelated.
- **After every edit Claude delivers one complete updated `.md` file only**, no fragments or addenda.
- **Never trust a past "delivered and verified" claim.** On pickup or on any visual bug report, re-collect the actual live file named and check it. This rule has been proven necessary repeatedly (see Lessons).
- **Session protocol:** Omar says "Ready for [Feature/Step]" → Claude requests files via `collect_for_claude.py` (or confirms none needed) → implements one step → delivers code files + this updated `.md`.

---

## UI/UX handling (Stitch loop)

1. **To see a design, ask for the HTML/zip:** Claude never invents complex UI layouts from imagination. When a new screen is needed, ask Omar for the Stitch export or view the HTML provided.
2. **To change or request a design, give a prompt in chat only:** Write the modification prompt in a clear copy-paste code block in chat. Never store raw prompt text inside this `.md` file.
3. **Prompt contents:** Demand Material 3 / Pharmacy Emerald tokens, real database fields only (no mock labels), both desktop and mobile layouts, and explicit UI states (loading, empty, validation error, success).
4. **Audit every returned Stitch design before coding:** Inspect the HTML/CSS for:
   - Invented fake fields or mock clinical tags with no backend backing.
   - Non-standard palette tokens.
   - Missing RTL support (`dir="rtl"`, mirrored icons).
   - Broken accessibility (low contrast, missing labels).
5. **Non-visual work proceeds directly:** Backend APIs, bug fixes, data validation, test suites, and schema wiring proceed directly without needing Stitch.

---

## Standing facts and lessons

**Lessons that cost real time (do not repeat):**
1. **Windows virtualenv timezone requirement:** Python on Windows requires `tzdata` installed in `server/.venv` for `zoneinfo.ZoneInfo("Africa/Cairo")` to resolve without crashing.
2. **Pytest PYTHONPATH on Windows PowerShell:** Running pytest requires setting `$env:PYTHONPATH` to the project root, or running via `python -m pytest tests`, otherwise absolute imports like `server.app.main` fail to resolve.
3. **FIFO batch deduction order:** Always sort by `InventoryBatch.created_at.asc(), InventoryBatch.id.asc()` with `with_for_update()` to prevent race conditions during concurrent sales confirmations.
4. **Weighted unit acquisition cost:** When a single sale line consumes multiple batches bought at different prices, the unit cost is the weighted average. If any consumed batch had zero cost or unknown cost, `unit_cost` must remain `None` so financial reports don't falsely claim 100% profit.
5. **Never use Unix `tail` or `grep` in PowerShell:** Use PowerShell cmdlets (`Select-Object -Last N`, `Select-String`) or Python scripts.
6. **Next.js production build check:** Remote Google font downloads fail in offline sandboxes; Next.js builds fall back to local system fonts cleanly. Always verify `npm --prefix web run build` before declaring a UI task finished.
7. **Pydantic v2 Settings warning:** `server/app/config.py` uses deprecated `class Config:` instead of `SettingsConfigDict`. It works but emits deprecation warnings.
8. **Contract freshness:** The backend exposes `scripts/export_openapi.py`. Whenever API routes or response schemas change, run `python scripts/export_openapi.py --check` or regenerate `shared-schema/openapi.json`.

---

## Design reference: Stitch Pharmacy Emerald / M3 (current)

Source: Stitch designs for Roshetta Pharmacy System. All UI pages follow Material 3 surface hierarchy and custom tokens configured in `web/tailwind.config.ts`.

- **Color palette:**
  - `primary`: `#00563a` (Deep Emerald), `on-primary`: `#ffffff`, `primary-container`: `#1f6f50`, `on-primary-container`: `#a1efc8`, `primary-fixed`: `#a5f3cc`, `primary-fixed-dim`: `#8ad6b0`.
  - `surface`: `#ecfef3` (Mint tint), `surface-container-lowest`: `#ffffff`, `surface-container-low`: `#e6f8ed`, `surface-container`: `#e1f2e8`, `surface-container-high`: `#dbece2`, `surface-container-highest`: `#d5e7dd`.
  - `on-surface`: `#101e18`, `on-surface-variant`: `#3f4943`.
  - `secondary`: `#875200` (Warm Amber/Bronze), `secondary-container`: `#feb152`, `secondary-fixed`: `#ffddba`.
  - `tertiary`: `#8b2611` (Rust/Alert), `tertiary-container`: `#ab3e26`, `on-tertiary`: `#ffffff`.
  - `error`: `#ba1a1a`, `error-container`: `#ffdad6`, `on-error`: `#ffffff`.
  - `outline`: `#6f7a73`, `outline-variant`: `#bec9c1`.
- **Typography:**
  - Headlines & Numbers: `Plus Jakarta Sans`, weights 700 / 800 (`font-headline-xl`, `font-headline-md`, `font-stat-numeric`).
  - Body & Labels: `Noto Sans`, weights 400 / 500 / 700 (`font-body-md`, `font-body-sm`, `font-label-lg`, `font-label-md`, `font-label-sm`).
- **Layout & RTL:**
  - Default direction: RTL (`dir="rtl"` for Arabic, `dir="ltr"` for English). Controlled by `useLanguage()` hook from `@/lib/i18n`.
  - Touch targets: Minimum 44px/48px (`w-touch-target-min`, `h-touch-target-min`).
  - Mobile safe areas: `pt-safe`, `pb-safe` for mobile notches and gesture bars.

---

## Project scope and architecture

**Scope:**
1. Bilingual, mobile-first pharmacy operations web application (Arabic primary, English secondary).
2. Multi-tenant workspace management (personal account hub, 5 owned pharmacies cap, invite-based staff access).
3. Inventory tracking with multi-batch acquisition prices and FIFO cost deduction.
4. Double-entry financial ledger capturing sales, restocks, expenses, and gross profit.
5. AI pharmacy assistant chat for natural-language sales/restock proposals with human-in-the-loop confirmation.
6. MicroMind AI client for clinical knowledge and drug-safety checks.

**Backend Architecture (`server/`):**
- FastAPI async application running under Uvicorn.
- SQLAlchemy 2.0 async engine (`aiosqlite` default, `asyncpg` ready for PostgreSQL).
- Startup migration runner (`server/app/db/migrations.py`) managing incremental schema upgrades.
- JWT-like signed HMAC tokens for session authentication (`server/app/services/security.py`).
- Role-based and scope-based authorization matrix (`server/app/services/rbac.py`).

**Frontend Architecture (`web/`):**
- Next.js 14 App Router, React 18, TypeScript.
- Tailwind CSS with Material 3 tokens.
- Shared API client (`web/src/lib/api.ts`) with bilingual error mapping.
- Session storage auth manager (`web/src/lib/auth.ts`) supporting personal account scope and pharmacy workspace scope.

---

## MicroMind / AI integration contract

The external AI backend is **MicroMind**. The client lives at `server/app/services/micromind.py`.

- **Base URL:** Configured via `MICROMIND_API_URL` (default `http://127.0.0.1:8001/predict`), enabled via `USE_MICROMIND=true`.
- **Privacy boundary:**
  - Only general clinical or operational chat text is routed externally.
  - Sensitive pharmacy data (tenant inventory, customer records, financial numbers, actual profit) remains strictly on the local database path.
  - No patient identifiers or private customer information are ever sent to external endpoints.
- **Methods:**
  - `query(user_text, context)`: Sends query text, returns AI text response with graceful fallback on timeout or service unavailability.
  - `check_drug_safety(medicines)`: Evaluates drug-drug interactions and dosage alerts.
  - `extract_document(image_b64, document_type)`: Prepared client method for document OCR, currently inactive pending provider activation.

---

## File map (structure of every file; 96 files)

Regenerate anytime with: `python scripts/file_map.py`

### Root & Scripts
| File | What it is | Line count |
|---|---|---|
| `.env.example` | Environment variable template for server | 38 lines |
| `.gitignore` | Git exclusions | 45 lines |
| `FINAL_IMPLEMENTATION_PLAN.md` | Historical audit & implementation plan | 382 lines |
| `README.md` | System setup, run instructions, and operational boundaries | 104 lines |
| `ROSHETTA_PROJECT.md` | Master project documentation & truth file (THIS FILE) | ~320 lines |
| `scripts/collect_for_claude.py` | Collects requested files into `scripts/needed_files.txt` | 44 lines |
| `scripts/file_map.py` | Generates structure-only outline of codebase into `scripts/file_map.txt` | 46 lines |
| `scripts/export_openapi.py` | Exports FastAPI schema to `shared-schema/openapi.json` | 67 lines |
| `scripts/generate_openapi_types.py` | Generates TypeScript DTOs from OpenAPI contract | 100 lines |

### Backend API & Database (`server/`)
| File | What it is | Line count |
|---|---|---|
| `server/requirements.txt` | Backend Python dependencies (FastAPI, SQLAlchemy, asyncpg, etc.) | 13 lines |
| `server/app/main.py` | FastAPI app factory, CORS, exception handlers, router registry | 79 lines |
| `server/app/config.py` | Pydantic BaseSettings loading backend configuration | 43 lines |
| `server/app/api/actions.py` | Action proposal confirmation (FIFO batch deduction) & cancellation | 488 lines |
| `server/app/api/auth.py` | Personal account login, registration, pharmacy switching, legacy auth | 776 lines |
| `server/app/api/chat.py` | Pharmacy assistant chat endpoint invoking LangGraph pipeline | 162 lines |
| `server/app/api/inventory.py` | Inventory CRUD, batches endpoint, low-stock, direct restock, matching | 712 lines |
| `server/app/api/ledger.py` | Financial summaries, ledger transaction queries, activity audit events | 179 lines |
| `server/app/api/me.py` | Personal profile viewing, photo upload/serving, personal activity | 357 lines |
| `server/app/api/ocr.py` | Document scanning upload endpoint (safely returns 503 disabled) | 207 lines |
| `server/app/api/pharmacies.py` | Pharmacy workspace creation, selection, roles, invite links | 358 lines |
| `server/app/api/staff.py` | Staff roster, member details, shifts, compensation, invitation management | 796 lines |
| `server/app/db/session.py` | Async SQLAlchemy engine & session factory | 30 lines |
| `server/app/db/seed.py` | Database startup initialization and optional demo data seeding | 168 lines |
| `server/app/db/migrations.py` | Incremental database migration runner (v1 to v11) | 222 lines |
| `server/app/db/models/__init__.py` | SQLAlchemy ORM models (User, Pharmacy, Item, Batch, Ledger, etc.) | 410 lines |
| `server/app/services/clock.py` | Cairo-local datetime helpers (`Africa/Cairo`) | 13 lines |
| `server/app/services/financials.py` | Ledger summation and profit calculation helpers | 98 lines |
| `server/app/services/micromind.py` | MicroMind AI client (timeout, query, safety check) | 44 lines |
| `server/app/services/rbac.py` | Token identity decoding, role check, and delegable scope authorization | 92 lines |
| `server/app/services/security.py` | Password/PIN hashing, signed token generation & validation | 127 lines |
| `server/app/services/stock.py` | Inventory quantity validation helpers | 20 lines |

### Assistant & Agents (`agents/`)
| File | What it is | Line count |
|---|---|---|
| `agents/orchestrator.py` | LangGraph async orchestrator graph definition | 65 lines |
| `agents/state.py` | Agent conversation and intent state schema | 28 lines |
| `agents/agents/intake.py` | Message classification, dialect normalization, entity extraction | 234 lines |
| `agents/agents/verification.py` | Inventory verification and structured proposal builder | 188 lines |
| `agents/agents/inventory.py` | Stock lookup node for assistant queries | 52 lines |
| `agents/agents/finance.py` | Financial summary calculation node for assistant queries | 55 lines |
| `agents/agents/drug_safety.py` | Interaction rule checker node | 72 lines |
| `agents/agents/ocr_extract.py` | OCR extraction node (disabled) | 15 lines |
| `agents/prompts/dialect.py` | Arabic dialect normalization dictionary | 42 lines |

### Shared Contracts & Tests
| File | What it is | Line count |
|---|---|---|
| `shared-schema/openapi.json` | Authoritative OpenAPI 3.1 contract | 7,675 lines |
| `shared-schema/models.py` | Pydantic data transfer models | 137 lines |
| `shared-schema/types.ts` | Shared TypeScript types | 134 lines |
| `tests/test_api_security.py` | Auth, RBAC, tenant isolation, role management tests | 1,070 lines |
| `tests/test_flow.py` | End-to-end sales proposal, FIFO batch deduction, ledger tests | 192 lines |
| `tests/test_migrations.py` | Barcode uniqueness (v4) and inventory batch backfill (v10) tests | 206 lines |
| `tests/test_openapi_contract.py` | Schema freshness and declared success response tests | 183 lines |
| `tests/test_micromind.py` | MicroMind client timeout & fallback tests | 74 lines |
| `tests/test_config.py` | Settings & environment validation tests | 31 lines |

### Frontend Client (`web/`)
| File | What it is | Line count |
|---|---|---|
| `web/package.json` | Next.js 14, React 18, Tailwind dependencies | 28 lines |
| `web/tailwind.config.ts` | Material 3 Pharmacy Emerald tokens & color palette | 127 lines |
| `web/src/app/page.tsx` | Dashboard overview: financial summary, quick actions, low-stock items | 550 lines |
| `web/src/app/assistant/page.tsx` | Assistant chat view and action proposal cards | 581 lines |
| `web/src/app/inventory/page.tsx` | Inventory catalog table, search, category filter | 243 lines |
| `web/src/app/inventory/categories/page.tsx` | Category management and filtering | 216 lines |
| `web/src/app/inventory/new/page.tsx` | Product creation route wrapping ProductForm | 25 lines |
| `web/src/app/inventory/[id]/edit/page.tsx` | Product edit route wrapping ProductForm | 103 lines |
| `web/src/app/inventory/[id]/restock/page.tsx` | Direct restock intake screen with stepper and live ledger preview | 481 lines |
| `web/src/app/inventory/overview/page.tsx` | Valuation grid, 4-column KPI bento, and Batch modal | 627 lines |
| `web/src/app/onboarding/page.tsx` | Login, personal registration, pharmacy creation hub | 140 lines |
| `web/src/app/pharmacies/page.tsx` | Pharmacy workspace hub (5-pharmacy cap) | 302 lines |
| `web/src/app/pharmacies/[id]/page.tsx` | Pharmacy workspace details & scoped summary metrics | 389 lines |
| `web/src/app/pharmacies/[id]/members/page.tsx` | Staff member list & expiring invite link creator | 420 lines |
| `web/src/app/pharmacies/[id]/members/[userId]/page.tsx` | Staff shift editor, compensation terms, period work summary | 202 lines |
| `web/src/app/pharmacies/[id]/roles/page.tsx` | Custom role manager and delegable scope checklist | 460 lines |
| `web/src/app/me/page.tsx` | Personal profile editor with private 5MB photo upload | 330 lines |
| `web/src/app/me/activity/page.tsx` | Personal staff work summary (sales, restocks, expenses) | 362 lines |
| `web/src/app/prescriptions/page.tsx` | Prescription review records & clinical alert status | 276 lines |
| `web/src/app/records/page.tsx` | Transaction ledger entries and activity audit logs | 247 lines |
| `web/src/app/scan/page.tsx` | Document scan capture screen (shows disabled banner) | 406 lines |
| `web/src/app/settings/page.tsx` | Pharmacy settings, address, tax ID, license | 207 lines |
| `web/src/components/inventory/ProductForm.tsx` | Reusable form with duplicate scan, category pills, margin calculator | 618 lines |
| `web/src/components/cards/ActionProposalCard.tsx` | Interactive proposal confirmation card with editable items | 145 lines |
| `web/src/components/ui/TopHeader.tsx` | Responsive bilingual header with workspace switcher | 86 lines |
| `web/src/components/ui/BottomNav.tsx` | Mobile-first bottom navigation bar | 64 lines |
| `web/src/lib/api.ts` | Authoritative API client with bilingual error mapping | 977 lines |
| `web/src/lib/auth.ts` | Session token storage and scope manager | 75 lines |
| `web/src/lib/i18n.ts` | Language state (ar/en) and RTL layout manager | 145 lines |
| `web/src/types/index.ts` | Frontend TypeScript interface definitions | 250 lines |
| `web/src/types/openapi.generated.ts` | Auto-generated OpenAPI DTOs | 753 lines |

---

## Open items & Verify checklist

Run these commands to verify total project integrity:

```powershell
# 1. Run all backend tests (57 tests)
$env:PYTHONPATH="d:\Desktop\projects\Micromind\PharmacySystem"; & "d:\Desktop\projects\Micromind\PharmacySystem\server\.venv\Scripts\python.exe" -m pytest tests -q

# 2. Check OpenAPI contract freshness
$env:PYTHONPATH="d:\Desktop\projects\Micromind\PharmacySystem"; & "d:\Desktop\projects\Micromind\PharmacySystem\server\.venv\Scripts\python.exe" scripts/export_openapi.py --check

# 3. Check frontend TypeScript types and build
npm --prefix web run build
```

**Manual Verification Checklist:**
1. *Authentication & Workspaces:* Log in via `/onboarding`, navigate to `/pharmacies`, select a pharmacy workspace, verify pharmacy-scoped token is issued and displayed in header.
2. *Inventory Batches:* Add a product via `/inventory/new` with stock 20 and buy price 10. Go to `/inventory/[id]/restock` and intake 10 more at buy price 12. Check `/inventory/overview` to verify 2 distinct batches appear in the batch modal.
3. *FIFO Sale Deduction:* Open `/assistant`, request sale of 25 units. Confirm the action proposal. Verify the first 20 units are consumed from batch 1 (cost 10) and 5 from batch 2 (cost 12), with weighted unit cost 10.40 stamped in ledger.
4. *Bilingual Switcher:* Switch between Arabic and English using the top header control; verify RTL/LTR layout transitions cleanly on all screens.
5. *Duplicate Product Alert:* In `/inventory/new`, type an existing medicine name; verify the duplicate check alerts the user before saving.

---

## Deferred / standing technical debt (not yet scheduled)

1. **Pydantic v2 `BaseSettings` deprecation in `server/app/config.py`:** Update to `from pydantic_settings import BaseSettings, SettingsConfigDict` to remove console warnings.
2. **PostgreSQL deployment verification:** Validate multi-worker `asyncpg` connection pool behavior, migration execution, and transaction isolation on a managed PostgreSQL cluster.
3. **OCR Provider implementation:** When a real OCR provider is contracted, implement a dedicated adapter in `server/app/services/ocr_provider.py` and activate endpoints.
4. **Cloud Object Storage (S3):** Currently all uploaded photos and documents use local disk storage (`STORAGE_DRIVER=local`). Implement an S3/GCS adapter for scalable production storage.
5. **Native Mobile App (Capacitor / React Native):** The web client is mobile-first and responsive. A dedicated wrapper app is documented in `mobile-later/` for future development.

---

## History (short; the code holds the rest)

- **Session 10:** Multi-price batches (`InventoryBatch`) model created, startup migration v10 implemented, FIFO batch deduction added to `actions.py`, MicroMind AI client wired for document extraction and drug safety, batch number input added to `ProductForm.tsx`.
- **Session 11:** UI implementation pass:
  - `/inventory/overview/page.tsx` upgraded with 4-column KPI bento (Units, SKUs, Capital Cost, Low-Stock), Buy/Sell split in table, and bottom-sheet Batch Inspector modal loading real `getItemBatches()` data with FIFO status cards.
  - `ProductForm.tsx` upgraded with clickable real-DB category pills and fallback text input.
  - Smart duplicate check debounced scan wired in `ProductForm.tsx` using `matchProduct()`.
  - Next.js build verified: 17 routes, 0 errors, 57 backend tests passing.
- **Session 12:** Single master documentation `ROSHETTA_PROJECT.md` created matching the exact structure and standards of the Miku project docs. Created `scripts/collect_for_claude.py` and `scripts/file_map.py` to support the exact file collection and map generation workflow.
