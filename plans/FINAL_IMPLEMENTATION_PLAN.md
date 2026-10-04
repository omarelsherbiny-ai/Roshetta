# Final Implementation Plan — Roshetta Pharmacy System

## Continuation update — 2026-10-01

- Sale proposals now load this pharmacy's positive-quantity inventory lots in FIFO order and calculate the proposed unit sale price from those lots. If the requested quantity exceeds lot records because of legacy/manual stock, the remainder uses the product-level sell price. Confirmation already consumes stock FIFO and records the corresponding weighted acquisition cost.
- OCR remains deliberately unavailable. The configured MicroMind text prediction URL does not document an image/OCR payload or response schema, and the `OCR_PROVIDER` setting is disabled by default. Enabling image uploads against an assumed contract could misrepresent extracted prescription, invoice, or product data. A provider endpoint, authentication method, supported formats, response examples/schema, and data handling terms are needed before safe activation.
- Multi-lot inventory storage, migration v10, lot listing, direct restock lot creation, and FIFO cost capture were already present in this checkout before this continuation. The new sale pricing completes the missing connection between those stored per-lot selling prices and assistant sale proposals.
- Personal activity summaries now attribute confirmed ledger actions to the staff member who confirmed them, use Cairo-local day/week/month boundaries, and report both sold and restocked unit quantities. The activity UI now includes a restocked-units card.
- Pharmacy overview reporting now uses the Cairo business-day window. Product/low-stock counts and revenue are returned only when the member has the corresponding `view_inventory` or `view_reports` scope. The overview API and UI no longer expose the reusable legacy invite code.
- Profile image upload is now limited to JPEG/PNG/WebP up to 5 MB, checks file signatures, stores generated account-specific filenames, and serves the current image only to the authenticated account. The profile UI fetches private images with its bearer token and revokes temporary object URLs.
- Root documentation now reflects the connected account/pharmacy screens and current profile-photo behavior rather than describing those screens as disconnected.
- Custom roles can now be edited and deactivated from the roles screen; members can be reassigned between supported built-in and custom roles. The scope selector now covers the backend's delegable scopes, including restocks, inventory viewing, and staff activity. Scheduling and compensation remain owner-controlled.
- The staff page no longer displays a fabricated pharmacy invite code or hard-coded public domain. It creates secure expiring invitations with a selected fixed/custom role, use limit, one-time displayed link, active-link list, and revocation. Staff granted `manage_staff` may invite fixed roles; custom-role invitations remain owner-only.
- Added a staff details screen for Cairo-time weekly shift editing, effective dates, period work summaries, versioned compensation terms, and history; it is linked from the owner member drawer.
- Settings now links owners to the secure staff management page and no longer offers the old PIN-issuing invitation, unrestricted invite-code banner, or duplicate staff editor. Owner controls fail closed when the client role is absent. The older login modal now directs staff to personal-account onboarding and the secure link flow.
- Removed unsubstantiated UI status claims such as an “Active License” on a personal profile and live/connected pharmacy indicators; overview captions now describe actual member, catalog, and transaction records.
- Verification after this continuation: frontend TypeScript checking passes and all 40 isolated backend/security/workflow/migration tests pass. The first typecheck exposed and this pass fixed a missing `(pharmacy_id, user_id, days)` call on the staff detail page and a missing `custom_role_id` field in the staff client type. Migration tests cover v4 barcode conflicts and uniqueness; new workflow tests cover FIFO sale prices across multiple lots and duplicate sale lines. Backend tests use in-memory SQLite; no live database or external provider was used.
- The shared frontend API error mapper now covers the common action, inventory, pharmacy, staff, profile-photo, report-date, and permission errors. It translates permission names in dynamic role errors, and unknown English server details fall back to localized operation-specific copy in Arabic instead of leaking English.
- The category view no longer pretends to save categories in client-only state. It shows categories derived from saved products, links to product creation when none exist, and distinguishes search-empty from data-empty states. Category and inventory overview requests now show retryable failures; lot-detail fetch errors no longer appear as an empty lot list.
- Pharmacy overview now reports summary-load failures instead of silently substituting zeros, and workspace switching retrieves the account when the browser cache is missing rather than fabricating a user. Restock now distinguishes product-load and lot-load failures, offers retry, and prevents submission until the actual product loads.
- Reusable invitation-code admission, code refresh, and credential-issuing legacy invitations are retired with `410 Gone` responses. Staff role changes/removal use pharmacy-scoped endpoints, and the members UI uses those routes. Security tests now join through expiring invitations. The old database column remains only for existing-schema compatibility; API payloads omit it.
- Verification after this security migration: backend isolated tests and frontend TypeScript checking pass; no live database or external provider is involved.
- Added a reproducible OpenAPI JSON contract export from the FastAPI app, including an HTTP bearer security scheme and accurate `410 Gone` responses for retired routes. `scripts/export_openapi.py --check` confirms the generated contract matches current routes without writing changes.
- The LangGraph runner now awaits `ainvoke` instead of calling the synchronous `invoke` inside an async API request, so agent execution no longer blocks the event loop while awaiting graph work.
- OpenAPI freshness and retired-route/bearer documentation are covered by isolated tests, preventing the shared API contract from silently drifting from FastAPI. Migration v10 has regression coverage for legacy stock-lot backfill and migration v11 clears obsolete reusable invitation codes; migration tests cover lot indexes, empty/unscoped stock exclusion, saved costs/expiry, and restart behavior. The current suite has 46 tests.
- New registrations and demo seeds no longer create or print retired invitation codes; migration v11 clears old persisted values. Configuration now rejects non-local storage driver values instead of silently using local disk, and the README/environment template state that object storage is not implemented. A config regression test covers rejection.
- Added the missing `asyncpg` runtime dependency required by the documented SQLAlchemy async PostgreSQL URL. Isolated verification remains on SQLite; no live PostgreSQL connection was attempted.
- Corrected the MicroMind configuration description and clarified in the assistant UI/README that, when enabled, only general-chat text is sent externally; pharmacy data queries/actions remain local. The UI cautions against sending patient identifiers or sensitive clinical details.
- Direct restock input now validates real `YYYY-MM-DD` expiry dates with the same validator as product entry, caps batch IDs at the 60-character database field limit, and assigns the required unique ledger ID. Its per-lot buy price now drives the restock ledger total and line unit price/subtotal, including an explicitly zero-cost lot. Changes to product-level buy/sell prices made during restock now add the same tenant-scoped price-history record as product edits. API coverage exercises validation, lot/ledger persistence, matching purchase-cost line values, and price history; valid requests had previously failed on a missing ledger primary key.
- Focused direct-restock API regression test passes, including changed-price history and zero-cost lot accounting.
- The inventory API now declares Pydantic success response models for all 11 endpoints. This constrains serialized inventory fields and makes their actual return shapes part of OpenAPI.
- Ledger financial summary, entry, and activity endpoints now also declare typed success responses. Their generated DTOs replace handwritten dashboard/API types, including removal of `any[]` from recent ledger entries.
- Personal-account logout, account-scope, registration, login, profile-read, and profile-update endpoints now publish constrained response schemas. The account UI consumes generated user/session DTOs, and persisted language preferences are validated before applying them in the frontend.
- Pending-action recovery, confirmation, and cancellation now publish explicit response models. Recovery validates full saved proposals before exposing them and computes each line subtotal from quantity and unit price, so malformed persisted proposals are safely counted as unavailable instead of producing ill-typed UI cards.
- Pharmacy registration, login, pharmacy switching, staff listing, and profile read/update now have explicit response schemas. Private pharmacy fields remain optional in the schema and are included only when existing `edit_settings` permission checks supply them; frontend auth/settings clients now use generated request and response DTOs.
- The `/api/me` profile summary, profile update, photo-upload result, and activity summary now have response models. The account-hub client uses the generated profile/activity/photo DTOs, and an integration regression covers profile membership data, updates, and Cairo-scoped activity output.
- Added deterministic TypeScript schema generation from the OpenAPI contract and wired inventory and ledger request/response types in the frontend API client to those generated DTOs. `scripts/generate_openapi_types.py --check` guards the generated file against drift.
- Historical contract audit found typed JSON `200` responses for 33 of 68 API operations. Current route metadata adds typed JSON contracts for the remaining JSON operations; the two file-download operations document supported binary image media types. `test_all_declared_success_responses_have_constrained_schemas` validates all success responses. TypeScript client generation is still only adopted for selected domains, so broad generated-client adoption remains follow-up work.
- Current verification on the isolated environment: the full backend suite passes (53 tests), frontend `tsc --noEmit` passes, OpenAPI and generated-TypeScript freshness checks pass, and the production frontend build passes. The build cannot download remote Google fonts in the offline environment; it completes with the existing fallback behavior.
- Verification after these UI/error-state changes: TypeScript checking passes and the full isolated backend/security/workflow/migration suite passes (40 tests). The two new FIFO tests exercise weighted multi-lot pricing and sequential lot use across duplicate sale lines.

## Initial audit scope and confidence (historical)

The initial audit reviewed first-party source under `agents/`, `mobile-later/`, `server/`, `shared-schema/`, `tests/`, and `web/src/`, plus root configuration and package manifests. Later continuation updates have run the isolated backend suite, frontend TypeScript checking, and the OpenAPI contract check; these checks do not constitute production or external-provider validation.

The current directory has no `.git` repository metadata, so tracked/untracked status and change history could not be determined. The checked-in-looking `roshetta.db`, `server/.env`, generated caches, and installed dependencies should be inventoried separately before release.

## 1. What is complete

“Complete” here means a coherent implementation exists in source, not that it has been production-validated.

- **Backend app structure and local persistence bootstrap:** FastAPI app, router registration, SQLAlchemy async session, schema creation, seed flow, upload serving, and health endpoint exist in `server/app/main.py`, `server/app/db/session.py`, `server/app/db/seed.py`, and `server/app/db/models/__init__.py`.
- **Core pharmacy domain tables:** Pharmacy/user/membership, inventory, ledger entries and line items, prescription records, interaction rules, and audit log models exist in `server/app/db/models/__init__.py`.
- **Pharmacy registration, login, staff and profile endpoints:** Registration/login, secure invitation acceptance, scoped role/removal, profile read/update, and staff listing endpoints exist. Reusable-code and credential-issuing legacy routes are retired in `server/app/api/auth.py`.
- **Inventory CRUD and lookup endpoints:** Pharmacy-scoped list, detail, low-stock, create, update, and match routes exist in `server/app/api/inventory.py`.
- **Ledger read endpoints and proposal confirm/cancel routes:** Daily totals, recent entries, confirmation, cancellation, stock adjustments, and audit writes exist in `server/app/api/ledger.py` and `server/app/api/actions.py`.
- **Web app route skeleton and key screens:** Dashboard, assistant, inventory, product add/edit, scan, prescription list, records, settings, and onboarding screens exist under `web/src/app/`.
- **Typed chat and confirmation presentation:** The assistant UI posts text to the backend and displays proposal results; confirmation/cancel UI calls the action API in `web/src/app/assistant/page.tsx`, `web/src/components/cards/ActionProposalCard.tsx`, and `web/src/lib/api.ts`.
- **Shared model concepts:** Python Pydantic models and TypeScript interfaces cover proposals, prescriptions, inventory, and ledger summary in `shared-schema/models.py` and `shared-schema/types.ts`; frontend types also exist in `web/src/types/index.ts`.
- **Basic flow test intent:** `tests/test_flow.py` describes a typed sale, confirmation, finance query, and drug interaction scenario, though it currently contains significant encoding and fixture assumptions (see below).

## 2. Initial audit snapshot (historical; superseded by the continuation updates above)

The notes below were written before the continuation work recorded above. They are retained as history and must not be read as a current defect list. In particular, authentication now uses signed expiring tokens and validates active users/memberships server-side; proposal type and confirmation state are persisted; daily reports use Cairo date windows; OCR is explicitly unavailable rather than returning sample extraction; prescription review is persisted and alert-gated; profile/staff screens and upload constraints have since been updated.

## 3. Remaining verified work

- Real document extraction is still unavailable. Keep scan paths unavailable until a provider supplies a documented image request/response contract, authentication details, supported formats, and data-handling terms.
- Prescription records support persisted review/hold decisions, but there is no dispense workflow. Do not add dispensing until verified medicine identity, clinical review rules, and inventory/ledger behavior have an agreed specification.
- The local drug-safety agent uses a small rule list; the persisted interaction-rule table is not yet the operational source of clinical interaction checks. This needs a validated drug knowledge source and clinical review before use for decisions.
- The generated OpenAPI contract is checked in at `shared-schema/openapi.json` and can be freshness-checked. Inventory, ledger, personal-account and pharmacy auth, account-hub profile/activity, and action-flow success responses are typed and matching generated TypeScript DTOs are consumed by the frontend. The other 35 of 68 operations do not yet publish typed success responses, so their handwritten frontend response DTOs can still drift; add accurate response models before generating and adopting those DTOs.
- Production deployment against a real database/provider has not been validated. The async PostgreSQL driver is now packaged, but migration/runtime behavior still needs a PostgreSQL service. Current verification uses isolated in-memory SQLite and disabled external services. Backup/restore, secret provisioning, monitoring, and operational runbooks remain.
- A native mobile client remains a roadmap item. It depends on the stable API contract and offline/idempotency requirements.

## 4. Duplicated implementation notes (historical)

- **Authentication and RBAC:** Login verifies a user and membership in `server/app/api/auth.py`, and endpoint permission checks use the permission matrix in `server/app/db/models/__init__.py`. Request authentication itself trusts an unsigned token and does not revalidate membership or active status (`server/app/services/rbac.py`). Frontend guards are inconsistent and client-only (`web/src/lib/auth.ts` and pages).
- **Chat orchestration:** The request gathers pharmacy inventory and all-time ledger totals in `server/app/api/chat.py`; local intent detection and proposal generation exist in `agents/agents/intake.py` and `agents/agents/verification.py`. User query coverage, real language handling, accurate quantities/prices, and safe catalog matching are narrow and rule-based. Financial results are labeled “today” but the query has no date filter.
- **MicroMind integration:** A configurable HTTP client with timeout/fallback exists in `server/app/services/micromind.py`; chat calls it in `server/app/api/chat.py`. Only a limited response shape is used, and remote output is considered only for `general_chat`; structured actions are not integrated. Defaults say enabled and provide a configured URL in `server/app/config.py` and `.env.example`, but the setting is not used to control the client call beyond client-level config.
- **Document scan flow:** Browser capture/file upload and backend endpoint wiring exist in `web/src/app/scan/page.tsx`, `web/src/components/camera/CameraCaptureModal.tsx`, `web/src/lib/api.ts`, and `server/app/api/ocr.py`. `agents/agents/ocr_extract.py` returns canned prescription/invoice/receipt content regardless of uploaded image; file validation, secure names, OCR provider use, and robust cleanup are absent.
- **Prescription safety:** `agents/agents/drug_safety.py` checks a small hard-coded list and is called on the canned prescription path. Database interaction rules exist but are not consulted. Safety alerts are persisted as a coarse status, while medication matching and pharmacist review/dispense state are not implemented end-to-end.
- **Inventory product scan:** `server/app/api/ocr.py` exposes `/product-box`, but returns fixed sample fields. The inventory list can call it (`web/src/app/inventory/page.tsx`, `web/src/lib/api.ts`); the shared `ProductForm` has a separate simulated OCR flow instead of using this endpoint (`web/src/components/inventory/ProductForm.tsx`).
- **Prescription UI:** `web/src/app/prescriptions/page.tsx` loads backend records but merges them with many hard-coded sample cards; dispense and print interactions are local UI actions, not persisted backend workflows.
- **Settings/staff UI:** Settings is connected to profile and staff APIs in `web/src/app/settings/page.tsx` and `web/src/lib/api.ts`, but permissions and supported roles diverge in places, errors are mostly browser alerts, and client role defaults can misrepresent actual authorization.
- **Database evolution:** `seed_data()` creates missing tables and seeds only when the user table is empty (`server/app/db/seed.py`). There is no migration system; `create_all` cannot evolve existing tables when models change.
- **Mobile target:** `mobile-later/README.md` defines Capacitor/React Native possibilities and planned capabilities, but there is no mobile app or the referenced `shared-schema/openapi.yaml` contract.

## 3. What is broken or materially unsafe

1. **Any caller can forge an owner token.** `server/app/api/auth.py::_make_token` creates `roshetta_<user>_<pharmacy>_<role>` without a signature; `server/app/services/rbac.py::decode_token` accepts caller-supplied IDs and role without a database lookup. A caller can change the role to `owner` or pharmacy ID and access/alter another tenant’s data. This blocks any deployment with real data.
2. **Role model disagreement causes inconsistent behavior.** `shared-schema/models.py` allows `staff` but not `cashier`/`viewer`; `web/src/types/index.ts` includes all five. The backend permission matrix supports `cashier` and `viewer`, and join defaults to `cashier`. Product-level authorization therefore has no single authoritative role contract.
3. **OCR does not extract the uploaded document.** `agents/agents/ocr_extract.py` ignores `image_path` contents and returns fixed records, and `/product-box` in `server/app/api/ocr.py` returns fixed values. The UI can present those results as actual extraction, which can create incorrect sales/restocks and safety conclusions.
4. **Prescription dispensing is not persisted or safety-gated.** The dispense controls in `web/src/app/prescriptions/page.tsx` only update client state; there is no backend dispense/review route. A flagged prescription is not technically prevented from being dispensed through the API because no prescription dispense API exists.
5. **Action type inference is based on proposal ID/name substrings.** `server/app/api/actions.py` determines expense/restock by searching `action_id` or a mojibaked expense string, rather than receiving and validating the proposal’s action type. IDs like `prop-inv-*` happen to work for canned scans, but ordinary generated IDs can be recorded as sales. This can cause incorrect ledger type and stock movement.
6. **Confirmation accepts client prices/subtotals and does not enforce positive quantities or consistency.** `server/app/api/actions.py` recomputes total from quantity and unit price but does not reject negative values or ensure quantity/price/subtotal are valid; it also lacks row locking/transaction conflict handling for concurrent sales. Client-provided `confirmed_by_user_id` is ignored, which is good, but the proposal itself is not persisted before confirmation.
7. **Catalog matching can select the wrong product.** Both `agents/agents/verification.py` and `server/app/api/actions.py` use short-prefix matching. In the backend fallback, only Arabic name matching is attempted. A wrong but prefix-similar product can be proposed or decremented.
8. **Financial “daily” values are all-time totals.** `server/app/api/ledger.py` and `server/app/api/chat.py` sum all matching entries without a date boundary. Displayed daily report and assistant answers therefore become false after the first day of use.
9. **The seeded/test fixtures and source text are inconsistent.** `tests/test_flow.py` searches for a fixed mojibaked product string and assumes a fixed dataset/price; sample OCR refers to fixed item IDs and quantities. The seeded tenant and inventory data are not a general fixture strategy. Many source strings display as mojibake in the checked-out text, including `agents/`, backend errors, and UI labels; confirm encoding at byte level before changing them, but current rendered strings are corrupted in the inspected output.
10. **Some frontend records and product fields cannot round-trip.** `ProductForm` submits `dosage_form`, `strength`, `batch_number`, and `shelf_location` fields that are absent from `ProductPayload` and `InventoryItem`; `expiry_date` uses `MM / YYYY` in sample defaults while API/schema expect an unconstrained string. Edit initialization also uses baked-in example values when fields are absent (`web/src/components/inventory/ProductForm.tsx`).
11. **The project lacks a reproducible root developer entry point.** Root `package-lock.json` is only 93 bytes and there is no root `package.json`, README, or compose/dev orchestration file in the source inventory. Backend dependencies live separately in `server/requirements.txt`, frontend in `web/package.json`, and a local `.env` exists under `server/`.
12. **CORS configuration is not honored.** `server/app/config.py` defines `ALLOWED_ORIGINS`, but `server/app/main.py` allows every origin with credentials. This is broader than configured intent.
13. **Upload handling is unsafe/incomplete.** `server/app/api/ocr.py` trusts client filenames, writes directly beneath a relative folder, does not cap size/type, has no failure cleanup, and `/product-box` has no auth dependency despite serving pharmacy inventory workflows.
14. **The shared schema is not actually the runtime source of truth.** Backend APIs define duplicate request models (notably `ActionConfirmRequest`), TypeScript has overlapping interfaces in `shared-schema/types.ts` and `web/src/types/index.ts`, and the declared sync relationship is unenforced.

## 4. What is duplicated

- **Domain interfaces:** `shared-schema/models.py`, `shared-schema/types.ts`, and `web/src/types/index.ts` independently define roles, actions, proposals, prescriptions, and inventory shapes; the web copy has extra fields and the shared role enum differs from backend roles.
- **Action confirmation DTO:** `shared-schema/models.py::ActionConfirmRequest` and `server/app/api/actions.py::ActionConfirmRequest` duplicate the request definition; the endpoint-local item model is also separate.
- **Inventory product form/creation flows:** `web/src/app/inventory/page.tsx` maintains an inline add form while `/inventory/new` uses `web/src/components/inventory/ProductForm.tsx`; the edit route uses the shared form. Their defaults and scan behavior differ.
- **Camera/document upload UIs:** `web/src/app/scan/page.tsx` and `web/src/components/camera/CameraCaptureModal.tsx` each implement camera capture, document type selection, preview, and upload interaction.
- **Authentication UI flows:** `web/src/app/onboarding/page.tsx` and `web/src/components/auth/LoginModal.tsx` both implement login/register/join flows; `LoginModal` also directly posts join rather than using the API helper.
- **Proposal presentation:** assistant inline proposal rendering and `web/src/components/cards/ActionProposalCard.tsx` both handle proposal display/actions; confirm which path is actually used and consolidate.
- **Finance aggregation:** summation logic is repeated in `server/app/api/chat.py` and `server/app/api/ledger.py` with the same missing date scope.
- **Drug interaction knowledge:** `DrugInteractionRule` is persisted in `server/app/db/models/__init__.py`, while separate hard-coded rule lists live in `agents/agents/drug_safety.py`; only the latter is used.
- **Fixture content:** seeded catalog (`server/app/db/seed.py`), canned OCR data (`agents/agents/ocr_extract.py`), canned product scan (`server/app/api/ocr.py`), UI static prescription cards (`web/src/app/prescriptions/page.tsx`), and test assumptions (`tests/test_flow.py`) describe overlapping records independently.

## 5. Older backlog (recheck against current source before acting)

- Signed/opaque session authentication with expiry, revocation, active user/membership validation, and server-derived role/tenant context.
- A consistent documented API contract (including the missing `shared-schema/openapi.yaml`) and a single role/type source.
- Database migrations and a clean test database/seed fixture separate from developer or production data.
- Persistent pending proposals, idempotency keys, concurrency-safe stock decrement, confirmation validation, and durable cancellation state beyond audit lookup.
- Real OCR/provider integration, upload constraints, product scan authorization, image/document error states, and review/edit corrections based on extracted content.
- Prescription review lifecycle: pharmacist identity/authorization, safety alert persistence at rule level, review decisions, dispense endpoint, inventory decrement where appropriate, and history.
- Sale cost/COGS and actual net profit semantics still need a product/accounting definition. Current reporting uses recorded sale costs, withholds net profit when costs are incomplete, and treats expenses as operating deductions.
- Inventory deletion/archive, batch/lot/expiry tracking, dosage/strength/form fields, and stock adjustment trail; whether these are product requirements is unstated, but the UI currently implies some fields that the backend cannot store.
- User-facing loading/empty/error states for several screens, permission-aware navigation and actions, session expiry presentation, and broad API error presentation.
- Automated coverage for auth/tenant isolation, role permission matrix, CRUD, sales/restock/expense confirmation, duplicate confirmation/cancel, OCR upload, and prescription review. The existing `tests/test_flow.py` is one monolithic async script, not an isolated repeatable test suite.
- Production configuration and operations: secret management, restrictive CORS, deployment instructions, database backup/migration strategy, storage driver behavior, logging/monitoring, and documented local setup.
- Actual native mobile project. `mobile-later/README.md` is a roadmap only.

## 6. Dependencies between unfinished features

1. **Tenant-safe auth first.** All protected API behavior relies on `get_current_user`; reporting, inventory, chat, ledger, settings, OCR, and action work cannot be safely completed until identity and pharmacy membership are validated server-side.
2. **Canonical contract and migration plan next.** Decide role names and persisted inventory/prescription fields before adding endpoints or changing tables. This unblocks web/API alignment and clean database evolution.
3. **Persistent proposal and transaction model before polishing confirmation UX.** OCR and typed chat must both create the same validated pending proposal record; confirmation/cancel must operate on that record with idempotency and atomic stock updates. This underpins both sales and restocks.
4. **Inventory matching and stock invariants before OCR-driven sales/restocks.** Extraction results need a reliable human review/match step; confirmation then uses stable inventory IDs and transaction-safe stock checks.
5. **Real OCR/provider selection before validating scan screens.** Camera/upload wiring can remain, but correctness of receipt, invoice, product-box, and prescription flows depends on actual extraction plus document-specific validation.
6. **Prescription persistence and safety rules before dispense workflow.** First align interaction rules and extracted medicine identity; then implement pharmacist review; only then enable dispense and inventory/ledger effects. Current canned cards should not be treated as operational records.
7. **Shared financial query service and date semantics before dashboard/report/chat metrics.** Decide timezone and what “profit” means (gross sales minus expenses vs margin after product cost), then reuse one aggregation service across dashboard, records, and assistant.
8. **UI consolidation follows stable APIs.** Consolidate duplicate form, camera, auth, and proposal experiences after contracts and endpoint behavior settle, or the duplicated code will drift again.
9. **Mobile follows the stable web/API contract.** The mobile roadmap depends on the missing OpenAPI contract, stable auth, durable action queue semantics, and server-side idempotency/offline conflict handling.

## 7. Exact files involved

### Root and shared contracts

- `.env.example`
- `.gitignore`
- `package-lock.json`
- `roshetta.db` (binary runtime data; schema/content not inspected)
- `shared-schema/models.py`
- `shared-schema/types.ts`
- `mobile-later/README.md`

### Backend

- `server/requirements.txt`
- `server/app/config.py`
- `server/app/main.py`
- `server/app/db/session.py`
- `server/app/db/seed.py`
- `server/app/db/models/__init__.py`
- `server/app/services/rbac.py`
- `server/app/services/micromind.py`
- `server/app/api/auth.py`
- `server/app/api/actions.py`
- `server/app/api/chat.py`
- `server/app/api/inventory.py`
- `server/app/api/ledger.py`
- `server/app/api/ocr.py`
- `uploads/` (runtime upload destination)

### Agent and business logic

- `agents/state.py`
- `agents/orchestrator.py`
- `agents/prompts/dialect.py`
- `agents/agents/intake.py`
- `agents/agents/verification.py`
- `agents/agents/inventory.py`
- `agents/agents/finance.py`
- `agents/agents/drug_safety.py`
- `agents/agents/ocr_extract.py`

### Web application

- `web/package.json`
- `web/next.config.mjs`
- `web/src/types/index.ts`
- `web/src/lib/api.ts`
- `web/src/lib/auth.ts`
- `web/src/lib/i18n.ts`
- `web/src/lib/utils.ts`
- `web/src/app/page.tsx`
- `web/src/app/layout.tsx`
- `web/src/app/globals.css`
- `web/src/app/onboarding/page.tsx`
- `web/src/app/assistant/page.tsx`
- `web/src/app/scan/page.tsx`
- `web/src/app/prescriptions/page.tsx`
- `web/src/app/records/page.tsx`
- `web/src/app/settings/page.tsx`
- `web/src/app/inventory/page.tsx`
- `web/src/app/inventory/new/page.tsx`
- `web/src/app/inventory/[id]/edit/page.tsx`
- `web/src/components/auth/LoginModal.tsx`
- `web/src/components/camera/CameraCaptureModal.tsx`
- `web/src/components/cards/ActionProposalCard.tsx`
- `web/src/components/cards/PrescriptionCard.tsx`
- `web/src/components/chat/InputBar.tsx`
- `web/src/components/chat/MessageBubble.tsx`
- `web/src/components/inventory/ProductForm.tsx`
- `web/src/components/ui/BottomNav.tsx`
- `web/src/components/ui/QuickActionChips.tsx`
- `web/src/components/ui/TopHeader.tsx`

### Existing test

- `tests/test_flow.py`

## Recommended implementation order

### Phase 0 — Establish a reproducible baseline

- Add root setup/run documentation and define separate frontend/backend start commands and environment handling.
- Confirm text encoding and normalize corrupted source strings in a dedicated change.
- Create isolated fixtures and a clean disposable test database; do not use `roshetta.db` as a test target.
- Record current frontend build/typecheck and backend startup results once the baseline is reproducible.

### Phase 1 — Secure tenant and identity boundaries

- Replace unsigned role-bearing tokens with signed, expiring sessions or opaque server-stored sessions.
- Resolve user, active membership, pharmacy, and role from trusted server state on every request; reject disabled users/memberships.
- Align role enum and permission policy across shared schema, backend, seed data, and UI.
- Honor configured CORS origins and protect all pharmacy-specific endpoints, including product scan.

### Phase 2 — Define contracts and database lifecycle

- Establish a canonical OpenAPI/API contract and generated or checked types.
- Resolve whether dosage form, strength, batch, shelf, and lot/expiry are supported; make persistence and UI agree.
- Add migrations for existing SQLite/PostgreSQL databases and a fresh database path for tests.
- Add API validation for IDs, money, quantities, dates, upload types/sizes, and supported enum values.

### Phase 3 — Make stock and ledger operations reliable

- Persist proposals with type, source, items, pharmacy, status, and audit history.
- Pass action type explicitly and validate it against permissions; remove ID/name substring inference.
- Enforce positive quantities/prices and server-side totals; apply stock changes atomically with concurrency protection and idempotency.
- Implement correct date/time-zone ranges and a shared financial aggregation service; define net profit semantics.

### Phase 4 — Replace fixtures with real extraction and review

- Implement the selected OCR/vision provider behind configured service interfaces, with deterministic failure behavior and confidence handling.
- Store uploads with generated names and validation; persist document metadata and connect source image references.
- Require review of extracted line items/product matches before proposal confirmation; match only to tenant inventory and stable IDs.
- Replace fake product-box extraction and simulated form OCR with the same real endpoint/service.

### Phase 5 — Complete prescription safety and dispense lifecycle

- Use persisted interaction rules (or a reviewed, versioned source) and normalize medicine identifiers.
- Persist extracted prescription plus alert details and pharmacist review status.
- Add owner/pharmacist-only review and dispense APIs; block critical alerts until an explicit authorized disposition.
- Connect actual dispense to inventory and audit/ledger semantics as product requirements dictate.
- Replace static sample records and local-only dispense/print affordances with server data/actions.

### Phase 6 — Align and consolidate web experiences

- Make page guards, navigation, settings and action controls permission-aware; handle session expiry consistently.
- Unify onboarding/login/join, inventory create/edit, camera scan, and proposal confirmation implementations.
- Replace browser alerts and silent swallowed errors with consistent accessible loading, error, and success states.
- Remove example defaults that silently submit as real item data; ensure each form maps only persisted fields.

### Phase 7 — Mobile and operational readiness

- Select Capacitor or React Native and create the actual mobile app after API/auth contracts stabilize.
- Add offline queue and conflict/idempotency behavior before enabling offline sales or scan uploads.
- Define production database/storage/secrets, backup, logging/monitoring, deployment, and recovery procedures.

## Audit limitations

- No runtime test/build was executed by request scope and the audit instructions did not request verification.
- `roshetta.db`, `.env` secrets, `uploads/`, `node_modules/`, `.next/`, and Python cache contents were not inspected.
- Product decisions remain open for prescription dispensing effects, profit definition, multi-branch support, and whether the extra product metadata in the UI is required.

## Implementation progress (2026-09-30)

Work started after the audit. This is a status update, not a claim that the roadmap is complete.

### Implemented in source

- Signed, expiring access tokens and database-derived active membership/role checks; PIN hashing with legacy upgrade; persistent login throttling; configured CORS; private tenant-scoped upload access. See `server/app/services/security.py`, `server/app/services/rbac.py`, `server/app/api/auth.py`, `server/app/api/ocr.py`, and `server/app/main.py`.
- The role contract now uses owner, pharmacist, cashier, and viewer consistently in shared Python/TypeScript roles. New staff receive a one-time initial PIN; the UI displays it after invitation.
- Pending proposals are persisted and scoped to their pharmacy; confirmation/cancellation validates stored action type and inventory identity, recomputes totals, checks stock, and commits ledger/stock/audit state together. See `server/app/db/models/__init__.py`, `server/app/api/chat.py`, and `server/app/api/actions.py`.
- A versioned additive database migration adds ledger cost snapshots while model metadata creates new tables. Fresh demo accounts hash their PINs, and demo seeding is opt-in. See `server/app/db/migrations.py`, `server/app/db/seed.py`, and `server/app/config.py`.
- Daily summaries use Cairo-local date boundaries. Cost-aware profit is withheld for sales with missing historical cost data. Cashier report queries are scoped to their own entries. See `server/app/services/financials.py`, `server/app/api/ledger.py`, `server/app/api/chat.py`, and `agents/agents/finance.py`.
- Pharmacy activity is exposed from the audit log and rendered separately from ledger transactions on the dashboard. Staff invitations, role changes, and removals are audited.
- Inventory creation/edit now uses one dedicated form and sends only fields supported by the current inventory model. Form defaults no longer prefill a sample medicine. The form accepts a full date and no longer fabricates a barcode or unsupported batch/shelf/dosage data.
- Canned OCR outputs and simulated product scans were removed/disabled. The UI and API now report OCR as unavailable instead of creating fake prescription, invoice, or product data. See `agents/agents/ocr_extract.py`, `server/app/api/ocr.py`, `web/src/components/inventory/ProductForm.tsx`, and `web/src/app/scan/page.tsx`.
- Onboarding no longer submits prefilled sample identities and now reads the backend's `pharmacy_name` response field. Language preference validation and dynamic document direction were extended to onboarding, inventory, settings, and the shared product form.
- Prescription history now loads saved pharmacy-scoped records, exposes an audited owner/pharmacist review-or-hold endpoint, and blocks a plain "reviewed" decision when saved safety alerts exist. The screen no longer uses static example prescriptions or local-only dispense/print actions. New review columns are covered by migration version 2. See `server/app/api/ocr.py`, `server/app/db/models/__init__.py`, `server/app/db/migrations.py`, `web/src/app/prescriptions/page.tsx`, `web/src/lib/api.ts`, and `web/src/types/index.ts`.
- The dashboard's pending-prescription count excludes reviewed/held records. The scan preview no longer claims fabricated OCR confidence, image quality, or active AI extraction; its extraction action is disabled while the provider is unavailable. Hard-coded demo login credentials were removed from `web/src/components/auth/LoginModal.tsx`.
- The onboarding, inventory, product form, settings, records, dashboard, assistant, and scan screens now select Arabic/English copy from the saved language and follow document direction on their primary containers. The onboarding copy no longer promises OCR, voice processing, HIPAA-grade compliance, or electronic invoicing capabilities that the current product does not substantiate. The assistant no longer presents an unperformed drug-interaction check or claims tax invoices were generated; successful action feedback is compact. See `web/src/app/onboarding/page.tsx`, `web/src/app/inventory/page.tsx`, `web/src/components/inventory/ProductForm.tsx`, `web/src/app/settings/page.tsx`, `web/src/app/records/page.tsx`, `web/src/app/page.tsx`, `web/src/app/assistant/page.tsx`, `web/src/app/scan/page.tsx`, and `web/src/components/ui/TopHeader.tsx`.
- Inventory API input now rejects blank names, negative quantity/cost/threshold, and a non-positive selling price; optional barcodes are stored as null instead of generated fake identifiers and explicit edits can clear them. See `server/app/api/inventory.py`.
- The assistant now sends the selected locale to the chat API and configures speech recognition for that locale. The missing-product blocked-action guidance points to manual inventory entry while image extraction is unavailable. See `web/src/app/assistant/page.tsx`, `web/src/app/page.tsx`, `web/src/lib/api.ts`, and `agents/agents/verification.py`.
- New pharmacies now start with empty, real inventory instead of automatically receiving demo medicines. Demo data remains limited to the explicit opt-in seed path. Pharmacy invitation codes now use 48 bits of randomness, with schema version 3 expanding the stored code column. See `server/app/api/auth.py`, `server/app/db/seed.py`, `server/app/db/models/__init__.py`, and `server/app/db/migrations.py`.
- Sale confirmation now totals requested quantities per inventory item before changing stock, preventing duplicate proposal lines from overselling one product. See `server/app/api/actions.py`.
- Central API error presentation now maps known Arabic backend errors to English and supplies bilingual operation-specific fallbacks across auth, inventory, finance/actions, prescriptions, staff, and pharmacy requests. The login modal also routes pharmacy joining through the shared API helper instead of maintaining a separate raw-fetch implementation. This is a partial localization improvement; it does not establish complete locale coverage.
- The login modal now has an accessible Arabic/English switch that syncs with saved app locale and updates direction for the active flow. Its welcome copy no longer promises camera OCR/AI. Shared chat input follows the selected direction and adds accessible labels; chat content follows its own detected text direction. Prescription-card labels and severity names now respect the selected language. See `web/src/components/auth/LoginModal.tsx`, `web/src/components/chat/InputBar.tsx`, `web/src/components/chat/MessageBubble.tsx`, `web/src/components/cards/PrescriptionCard.tsx`, and `web/src/components/ui/TopHeader.tsx`.
- Inventory and settings no longer silently present failed requests as empty data; both now surface localized retryable error states. Dashboard financial widgets show placeholders until the summary loads, and partial dashboard failures display a retryable warning. Staff invitation success messaging is localized instead of displaying raw backend Arabic. See `web/src/app/inventory/page.tsx`, `web/src/app/settings/page.tsx`, and `web/src/app/page.tsx`.
- Ordinary staff-role edits can no longer assign or alter the `owner` role. The settings screen renders owners as non-editable and the API rejects owner-role changes; a deliberate ownership-transfer flow remains a separate product/API feature. See `server/app/api/auth.py`, `web/src/app/settings/page.tsx`, and `web/src/lib/api.ts`.
- Multi-pharmacy login now presents all active memberships for explicit selection. Switching uses a server endpoint that verifies the target membership against the authenticated user, revokes the temporary source token, and issues a token scoped to the selected pharmacy. See `server/app/api/auth.py`, `web/src/lib/api.ts`, and `web/src/components/auth/LoginModal.tsx`.
- Auth request schemas now strip surrounding whitespace and enforce database-aligned bounds for names, phone numbers, invitation codes, PIN length, settings strings, and positive pharmacy IDs; role, language, and numeral-format values use literal enums. This moves malformed input rejection to request validation before DB access. See `server/app/api/auth.py`.
- The shipped OCR provider default is now `disabled` in app settings and `.env.example`, matching the actual absence of an OCR adapter. A local deployment may override this setting, but no image request is sent unless a real adapter is implemented. See `server/app/config.py`, `.env.example`, and `agents/agents/ocr_extract.py`.
- Logout now revokes the current signed token server-side, with expired revocations pruned on logout; the settings flow clears browser auth state even if the server is unavailable. The revocation table is created through existing metadata startup. See `server/app/db/models/__init__.py`, `server/app/services/security.py`, `server/app/services/rbac.py`, `server/app/api/auth.py`, `web/src/lib/api.ts`, `web/src/lib/auth.ts`, and `web/src/app/settings/page.tsx`.
- Ledger entries are now dated at confirmation (booking) time, and records can request summaries and entries for a Cairo business date range. Both endpoints keep pharmacy and cashier scoping; invalid or partial ranges are rejected. The table signals when its 100-entry limit is reached while summaries remain complete. See `server/app/api/actions.py`, `server/app/api/ledger.py`, `server/app/services/financials.py`, `web/src/lib/api.ts`, and `web/src/app/records/page.tsx`.
- Pharmacy-scoped barcode uniqueness is now enforced with a partial unique database index as well as API validation. Migration v4 detects pre-existing duplicate barcodes per pharmacy and stops with a cleanup instruction rather than discarding or rewriting product records. Concurrent create/update conflicts return HTTP 409. See `server/app/db/models/__init__.py`, `server/app/db/migrations.py`, and `server/app/api/inventory.py`.
- Shared translation labels no longer assert a 100% clinical safety result or live AI connectivity, and the dashboard balance label now reflects the implemented sales-minus-expenses calculation rather than claiming net profit. Profit margin and unit profit labels explicitly state they are unavailable. See `web/src/lib/i18n.ts`.
- Replaced the old database-mutating one-off `tests/test_flow.py` script—which depended on canned OCR and demo rows—with isolated standard-library unit tests for the deterministic inventory verification stage. It covers grounded sale pricing/identity, missing-product blocks, insufficient stock, restock costs, and Arabic blocked-action copy.

### Still unfinished or blocked

- MicroMind image input is not confirmed. The repository's MicroMind client sends JSON only and has no credential or documented image request contract. The user selected MicroMind if supported; implementation is waiting for its image API schema/documentation or confirmation that the configured prediction endpoint accepts image payloads. Do not guess the payload.
- English/Arabic localization remains partial despite the latest screen translations and API error mapper. FastAPI validation arrays now get field-aware bilingual messages, but backend validation messages and the app still have untranslated or language-stale content in shared cards/components, auth, and other dynamic assistant responses. Review every route, shared component, accessible label, empty/error/loading state, date/currency format, and persisted language flow before claiming complete locale support.
- Prescription extraction, validated rule-backed safety review, pharmacist dispense API, and persisted dispense effects remain incomplete. The saved record review/hold workflow is not a clinical approval or dispense. No real extraction pipeline is available yet.
- App-wide loading/error/empty/permission/session-expiry handling, canonical OpenAPI/types, operational deployment guidance, and a native mobile project remain outstanding. Automated FastAPI/API coverage now runs against in-memory SQLite; PostgreSQL and production-database behavior remain unverified.
- Ownership transfer is not implemented. The regular role-management path now rejects owner promotion and owner demotion to prevent unintended privilege transfer; define an explicit audited transfer process if the product needs multiple owners or transfer.
- In-memory API tests now verify logout revocation and pharmacy-data isolation. Token expiry/pruning and PostgreSQL-specific session behavior still need coverage; production-database behavior has not been exercised.
- Inventory migration v4 intentionally requires manual resolution if a pharmacy already has duplicate nonempty barcodes. A backup-first, read-only conflict query and safe correction procedure are documented in `README.md`; the SQLite migration and uniqueness behavior are covered, while PostgreSQL migration coverage is still required before production rollout.

### Verification performed

- `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json` completed successfully in `web/` after the latest localization and action-review edits.
- `python -m unittest discover -s tests -p test_flow.py -v` passed seven isolated tests; these do not connect to a pharmacy database or external service.
- Python AST parsing completed for all 17 Python files under `server/app`. The bundled Python runtime lacks FastAPI, so backend imports/startup and API integration behavior could not be verified.
- TypeScript `tsc --noEmit` passed after the latest API error localization and pharmacy-join helper changes.
- Backend runtime execution remains unavailable in this host: the project `.venv` points at a missing Python 3.11 base interpreter, and its installed Pydantic native extension is CPython 3.11-only while the available bundled runtime is Python 3.12. AST checks do not verify backend runtime behavior.
- TypeScript `tsc --noEmit` passed after the server-side logout wiring; the seven focused deterministic action tests passed, and AST parsing again covered all 17 backend Python files.
- TypeScript `tsc --noEmit` passed after adding selected-date records queries. Date behavior and confirmation-day booking still need database/API integration tests.
- Multi-day report filtering now has matching summary and entry range parameters; TypeScript and backend syntax checks are required after this change, with database-backed boundary/scoping tests still outstanding.
- TypeScript `tsc --noEmit` passed after the latest localized load-error states for inventory, settings, and dashboard.
- The SQLite partial-unique-index behavior was exercised in an in-memory database: duplicate non-null barcodes are rejected within a pharmacy, duplicates are allowed across pharmacies, and null barcodes can repeat. This does not execute the application's SQLAlchemy migration.
- Backend Python AST parsing, the seven isolated action tests, and TypeScript checking remain the available gates; the latest barcode-index migration/API behavior still lacks a live backend/database integration test.
- The audit-limitation note above records what was inspected before implementation; it is a historical baseline rather than the current verification status.

## Latest implementation update — 2026-09-30

- Tightened `ProductPayload` in `server/app/api/inventory.py` to the actual database column lengths, reject NaN/infinite or out-of-range stock/threshold/prices, and accept only empty or ISO `YYYY-MM-DD` expiry dates. Product edits now record the previous and resulting stock count and whether stock changed in the existing audit event. This is audit visibility; a dedicated reasoned stock-adjustment workflow is still not implemented.
- Removed a duplicate Arabic error-map key in `web/src/lib/api.ts` that prevented TypeScript compilation.
- Verification after these changes: `tsc --noEmit` passes; AST parsing passes for all 27 Python files under `server/app`, `agents/`, and `shared-schema/`; all 7 existing deterministic action-flow tests pass. These checks do not import/run the FastAPI app or validate the new Pydantic constraints at runtime.
- No OCR request has been enabled. The provided MicroMind example establishes a text `question` payload only, so image extraction remains blocked pending a confirmed image-input and response schema. Existing scan entry points must continue to show unavailable rather than fabricate extracted records.
- Current environment still has no `.git` metadata. Review diffs through workspace/file state; do not infer that earlier edits are tracked or committed. The isolated backend runtime is available and now passes the full 46-test suite; this does not validate PostgreSQL or production services.
- Prescription list and scan endpoints now enforce role permissions. Product scans require `manage_inventory`, prescription scans/list/review require `scan_prescription`, and invoice/receipt scans require transaction permission. Private upload access checks the same permission for its stored document purpose. `StoredUpload.document_type` is added by migration v5; existing uploads receive the conservative `prescription` purpose. See `server/app/api/ocr.py`, `server/app/db/models/__init__.py`, and `server/app/db/migrations.py`.
- FastAPI validation error arrays now receive field-aware Arabic or English messages in the shared frontend API error mapper, avoiding raw Pydantic error text. See `web/src/lib/api.ts`.
- Latest verification: frontend TypeScript check passed, seven deterministic tests passed, AST parsing passed for all 27 Python files under `server/app`, `agents/`, and `shared-schema/`, and an in-memory SQLite check confirmed the migration's new non-null column default works for existing rows. The app migration function and permission enforcement still require integration testing in a valid backend environment.
- Pending server-side actions can now be fetched from `GET /api/actions/pending`. Results are pharmacy-scoped, filtered to operations the current role may perform, normalized through the confirmation item schema, and omitted with an unavailable count if saved contents are invalid. The assistant restores valid pending cards on entry/reload and refreshes their display language. See `server/app/api/actions.py`, `web/src/lib/api.ts`, and `web/src/app/assistant/page.tsx`.
- Proposal controls now prevent overlapping actions, render API failures inline, and cancel the original saved proposal before preparing a revised request. Verification after proposal recovery/control changes: `tsc --noEmit` passed, seven deterministic tests passed, and AST parsing passed for all 27 Python files. Recovery endpoint behavior, action races, and persisted-action flow still require live API/database integration tests.
- Aligned the shared TypeScript role union with the four roles enforced by the database and backend, and brought shared proposal-item fields in line with the frontend contract. See `shared-schema/types.ts` and `shared-schema/models.py`. Runtime/generated contract drift remains because the shared schemas are not yet wired into API generation or frontend type generation.
- `npm run build` passed for the production Next.js app and generated all 12 static pages. It emitted warnings that Google font stylesheets could not be downloaded in this network-restricted environment; the build continued without those optimized font downloads.
- Registration, joining, and staff invitation now translate uniqueness races into HTTP 409 responses instead of uncaught integrity failures; their race messages are localized in the API helper. See `server/app/api/auth.py` and `web/src/lib/api.ts`.
- After auth conflict handling, frontend typecheck passed, all 27 Python files across backend/agents/shared-schema parsed, and the existing seven deterministic action tests passed. These do not execute DB uniqueness races.
- Ledger responses now mark UTC timestamps explicitly and include both confirmation and creation times. Dashboard and records show the actual Cairo-local transaction date/time instead of labeling every recent item "Today"; prescription dates use the same formatter. See `server/app/api/ledger.py`, `web/src/lib/utils.ts`, `web/src/app/page.tsx`, `web/src/app/records/page.tsx`, and `web/src/app/prescriptions/page.tsx`.
- The current production frontend build completed successfully after the reporting changes and rendered all 12 static routes. Google font stylesheet downloads remain unavailable in this environment; Next.js skipped font optimization but completed the build.
- Removed the unused product-scan helper that promised unsupported extracted purchase/selling price fields, and removed the prescription card's direct-to-sale callback. Prescription extraction content now carries an explicit review-only message and cannot start a sale from that card. See `web/src/lib/api.ts`, `web/src/components/cards/PrescriptionCard.tsx`, and `web/src/components/chat/MessageBubble.tsx`.
- After those contract/safety changes, TypeScript, the production Next.js build (12 routes), the seven focused tests, and AST parsing for all 27 backend/agent/shared Python files passed. The build continues to warn that Google font stylesheets could not be fetched.
- Product-form OCR now presents a genuinely unavailable, disabled camera action rather than a fake scanner animation. The product header loads the authenticated pharmacy name instead of displaying the sample pharmacy name. See `web/src/components/inventory/ProductForm.tsx`.
- The records empty state now describes the selected date range. Current TypeScript and production build both pass after these latest UI changes; all 12 pages generate. The same offline Google font warnings remain.
- Added a root `README.md` with Windows-oriented backend/frontend setup, environment-file locations, database behavior, available checks, demo-seed caution, MicroMind text forwarding, and the explicit OCR/prescription feature boundaries. Its commands were checked against `server/app/config.py`, the package scripts, and the existing test path; a clean-machine bootstrap has not been run in this environment.
- Pharmacy auth/profile payloads now omit owner contact, address, license, tax ID, and invite code unless the active membership has `edit_settings`. Shared pharmacy identity/display settings remain available to all tenant members. The settings page fetches staff only for owners and hides profile editing for staff. See `server/app/api/auth.py`, `web/src/types/index.ts`, and `web/src/app/settings/page.tsx`.
- Verification after this authorization/UI change: TypeScript passed, AST parsing passed for all 27 Python source files, the seven existing focused action tests passed, and the Next.js production build generated all 12 routes. Backend role-payload tests still need a working FastAPI/SQLAlchemy runtime.
- Added `tzdata` to `server/requirements.txt` after an actual Windows FastAPI startup failed to find `Africa/Cairo`; Python's `zoneinfo` requires system IANA data or the `tzdata` package on systems without a time-zone database, including Windows ([Python zoneinfo docs](https://docs.python.org/3.12/library/zoneinfo.html)). Startup then succeeded using a fresh CPython 3.12 environment and in-memory SQLite.
- Added `tests/test_api_security.py` with live FastAPI/in-memory-SQLite coverage for private profile redaction, owner-only settings/staff access, clinical scan permissions, tenant-scoped inventory/private-upload lookups, logout token revocation, fail-closed OCR, accurate health integration status, and recovered action confirmation/stock changes. The new integration tests pass in the isolated verification environment.
- Startup logging now reflects the actual MicroMind text enabled state; `/health` distinguishes configured from enabled MicroMind and reports OCR unavailable. See `server/app/main.py`.

## Latest implementation update — 2026-10-01

- Replaced deprecated `datetime.utcnow()` and `datetime.utcfromtimestamp()` calls across auth, action, chat, inventory, OCR, pharmacy, and staff API routes with the shared UTC clock in `server/app/services/clock.py`. The chat response now emits an explicit `Z` UTC timestamp and derives IDs from the system epoch clock, avoiding a local-time interpretation of naive datetimes.
- Added UTC helper tests in `tests/test_config.py`; ignored the locally-created isolated verification environment in `.gitignore`.
- Verification: full Python suite passes (57 tests); frontend TypeScript check passes; `npm run build` completes and generates 17 routes. Next reports unavailable Google Fonts stylesheets and skips font optimization in this restricted network environment. OCR/prescription extraction and clinical dispense remain incomplete pending provider contract and clinical/product rules.
- Checked public MicroMind materials while looking for image request documentation; no public image-prediction contract for the supplied Core endpoint was found. Similar-name MiroMind API docs refer to a different product, so they are not being treated as the schema for AI MicroMind.
- General-chat requests now send an explicit Arabic/English response-language instruction to the existing text-only MicroMind `question` field, with API regression coverage for both languages. Removed the unused `extract_document` and `check_drug_safety` methods that sent undocumented task/image payloads; the provider client now exposes only the documented generic JSON query path. OCR remains unavailable until a provider contract is supplied.
- Current verification after the language-routing change: all 57 backend tests pass, frontend TypeScript checking passes, and the checked-in OpenAPI document passes its freshness check.
