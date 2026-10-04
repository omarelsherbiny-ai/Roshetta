<!-- README.md -->

# Roshetta Pharmacy System

Roshetta is a bilingual, mobile-first pharmacy application with a Next.js web client and a FastAPI backend. The backend uses SQLite by default and supports PostgreSQL through `DATABASE_URL`.

## Requirements

- Python 3.11 (the backend environment in this project was created for Python 3.11)
- Node.js 20 and npm

## Configure the backend

From the project root, copy `.env.example` to `server/.env`, then set a unique random `SERVER_SECRET_KEY` of at least 32 characters. The backend reads configuration from `server/.env`.

PowerShell:

```powershell
Copy-Item .env.example server/.env
```

Create and activate a virtual environment, install backend requirements, and run the API from the project root. The requirements include `asyncpg` for the documented `postgresql+asyncpg://` URL; PostgreSQL runtime behavior still needs validation against a PostgreSQL service.

```powershell
py -3.11 -m venv server/.venv
& .\server\.venv\Scripts\Activate.ps1
python -m pip install -r server/requirements.txt
python -m uvicorn server.app.main:app --reload --host 127.0.0.1 --port 8000
```

The API documentation is at `http://127.0.0.1:8000/docs`; `http://127.0.0.1:8000/health` reports service status. Database tables and schema migrations are applied during startup. SQLite data is stored in the path configured by `DATABASE_URL`; relative paths resolve from the backend process working directory.

The checked-in API contract is generated from the FastAPI routes. From the project root, run `python scripts/export_openapi.py` to refresh `shared-schema/openapi.json`, or add `--check` to detect a stale contract without writing files.

### Before upgrading an existing database

Migration v4 adds a partial unique index for non-empty barcodes within each pharmacy. Back up the database first, then check for conflicts with this read-only query:

```sql
SELECT pharmacy_id, barcode, COUNT(*) AS copies
FROM inventory
WHERE pharmacy_id IS NOT NULL AND barcode IS NOT NULL
GROUP BY pharmacy_id, barcode
HAVING COUNT(*) > 1;
```

For each result, inspect the product rows and verify the barcode against the package or a trusted catalog. Correct a mistyped barcode; set `barcode` to `NULL` when it is unknown or not reliably attributable. Do not delete or merge inventory rows just to make the migration pass: ledger history, stock lots, and foreign-key references may depend on them. Restart the API after resolving every duplicate. The migration will stop with an error and remain unapplied if conflicts remain.

Startup migration v10 copies each existing positive stock balance into an initial inventory lot while preserving its purchase/sale prices and expiry. Migration v11 clears the retired reusable invitation codes. Back up the database before startup migrations; these migrations are designed to retain inventory balances and remove only obsolete join codes.

The assistant endpoint `/api/chat` allows 20 messages per minute for each user in each pharmacy; above that it answers `429` with a `Retry-After` header. Change the limits with `CHAT_RATE_LIMIT_MESSAGES` and `CHAT_RATE_LIMIT_WINDOW_SECONDS` in `server/.env`. The counters live in the memory of each server process, so with several workers the real ceiling is the limit times the number of workers.

MicroMind is disabled by default: `USE_MICROMIND` defaults to `false` and `MICROMIND_API_URL` is empty, so nothing is sent externally until both are set in `server/.env`. When enabled, only the user's chat text is sent, and only when a request is classified as general chat; inventory, sales, restock, and financial requests stay on the local application path. Do not include patient identifiers or sensitive clinical details in general questions. OCR remains disabled until a supported image API contract and provider adapter are configured; scan requests currently return an unavailable response and must not be treated as extracted data.

For an isolated demo database only, set `SEED_DEMO_DATA=true` before backend startup. The seed routine creates public demo accounts and sample transactions; never enable this against production data.

## Configure and run the web client

In a second terminal, create `web/.env.local` with the API URL, then install dependencies and start Next.js:

```powershell
Set-Content -Path web/.env.local -Value 'NEXT_PUBLIC_API_URL=http://localhost:8000' -Encoding ascii
Set-Location web
npm ci
npm run dev
```

Open `http://localhost:3000`. Arabic is the default language; the language control switches between Arabic RTL and English LTR. The backend CORS allowlist is configured with `ALLOWED_ORIGINS` in `server/.env`.

## Verification

Run these from the project root unless noted:

```powershell
python -m unittest discover -s tests -v
python scripts/export_openapi.py --check
```

From `web/`:

```powershell
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json
npm run build
```

The Python suite covers deterministic inventory-grounded proposal logic and FastAPI security flows against an isolated in-memory SQLite database. It does not validate PostgreSQL behavior, production deployment, or a real OCR/MicroMind image workflow.

## Current functional boundaries

- Product creation is manual; camera-based product identification is unavailable.
- Prescription, invoice, and receipt image extraction is unavailable.
- Prescription review/hold records a review decision; it does not approve or dispense medicine and does not alter inventory.
- Pharmacy records and uploads use local storage; it is currently the only implemented storage driver. S3-compatible storage is not implemented. Production deployments need an operational database, object storage, backup, secret-management, monitoring, and migration plan.

## Personal accounts and pharmacy workspaces

The backend now has a separate account-scoped API foundation for the personal-account and pharmacy-hub flow. Existing user and pharmacy records are retained; startup migrations add optional profile fields and backfill ownership slots for existing owners.

- `POST /api/auth/register-user` and `POST /api/auth/account-login` create/authenticate a personal account without requiring a pharmacy.
- `GET/PATCH /api/auth/me` reads and updates the signed-in user's profile. Phone remains the account identifier. The profile screen supports private JPEG, PNG, and WebP photo uploads (maximum 5 MB) served through an authenticated, account-scoped route.
- `GET/POST /api/pharmacies` lists memberships and creates a pharmacy. Ownership is capped at five per account and protected by unique database ownership slots. New pharmacies default to EGP.
- `POST /api/pharmacies/{pharmacy_id}/select` issues a pharmacy-scoped session only for an active membership.
- Owner-only role endpoints create/edit/deactivate custom roles, assign one custom role to a member, and manage expiring single-use or limited-use invitation links. Invitation secrets are stored as hashes and shown only when created.
- Staff join from a personal account by accepting an expiring invitation link. Reusable pharmacy invite codes, code refresh, and legacy staff invitations that issued an initial PIN are retired; old API callers receive `410 Gone` and must move to the secure invitation endpoints.
- `/api/staff/me/activity` returns only the signed-in person's audit events across their pharmacy memberships. Summary endpoints aggregate that person's saved sales, expenses, and restocks from ledger data.
- Schedule endpoints store recurring weekday shifts with an IANA timezone and effective dates. Compensation endpoints store versioned terms; they do not calculate payroll or hours worked.

The web flow is connected to these account-scoped endpoints through `/onboarding`, `/pharmacies`, `/pharmacies/[id]`, `/pharmacies/[id]/roles`, `/pharmacies/[id]/members`, `/pharmacies/[id]/members/[userId]`, `/me`, and `/me/activity`. The member tools create/revoke scoped invitations, edit custom roles, assign roles, and maintain weekly shifts and compensation history. Personal work summaries attribute completed transactions to the confirming staff member and use Cairo business-day boundaries. Pharmacy overview metrics are returned only when the member has the corresponding inventory or report scope. Phone + PIN is retained for the account endpoints; an OTP decision can change the authentication flow later.
