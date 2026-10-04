# Stitch prompt: Roshetta account and pharmacy team screens

Extend the existing Roshetta Pharmacy Assistant design system using the supplied Roshetta screen references and project tokens. Generate production-ready responsive screen designs for desktop and mobile, with complete English LTR and Arabic RTL variants. Keep the same navigation, typography, spacing, colors, and component language as the supplied app; do not redesign existing onboarding, inventory, assistant, or records screens.

Create these screens and connected states:

1. **Personal profile** — read and edit only the signed-in user's name, location, photo URL, optional birth date, and language preference. Phone number is read-only. Show the saved profile values supplied by the app; never insert example people, placeholder addresses, or fake avatars as real data.
2. **Pharmacy overview/profile** — show the selected pharmacy's real name, address, currency (EGP), language, and available inventory/financial summaries. Make unavailable or incomplete figures explicit. Do not show regulatory certifications, live-sync claims, or service guarantees.
3. **Staff list** — list active pharmacy members returned by the app, their actual role name, phone, and joined date. Clearly distinguish the protected owner. Include loading, empty, error, and retry states.
4. **Role and scope editor** — present only the scopes supplied by the backend. Support one assigned role per non-owner member. Clearly mark owner access as protected and non-delegable; never offer owner as a custom role. Include empty, saving, conflict, and permission-denied states.
5. **Invitation management** — create an invitation for exactly one built-in role or one active custom role, with expiry and use limit; list expiry/use status and revoke actions. Show the raw invitation token/link only in the one-time creation result. Never invent an invite link or claim an invitation was sent.
6. **Employee work summary and activity** — employee summary may show only real sales, expenses, restocks, amounts, and quantities for a selected supported period. The personal activity feed is actor-scoped: it shows actions by the signed-in user, not activity by the whole pharmacy. Mark unavailable fields as unavailable rather than zero.
7. **Shift schedule editor** — edit weekday, start/end time, IANA timezone, and effective date range. Show validation for invalid timezone, end-before-start, mixed timezones, and overlapping shifts. Keep overnight shifts unsupported unless the backend is changed.
8. **Compensation terms** — owner can record a staff member's monthly, hourly, daily, commission, or other compensation terms in EGP, with amount/details and effective dates. State plainly that this records terms only; it does not calculate or pay payroll. Keep compensation visible only to the owner and that employee.

Use real-data states throughout: loading, empty, error, stale, and unavailable. Do not add demo controls or sample records, fabricated summaries, OCR confidence, SMS/OTP promises, payroll calculations, pharmacy regulatory claims, or external integrations. Use neutral empty-state copy until actual records exist. Do not imply any change was saved until the application confirms it. Preserve accessible labels, keyboard focus, touch-sized controls, long Arabic text wrapping, and LTR presentation of phone numbers, links, times, and amounts inside RTL layouts.

Return separate named frames for each screen at mobile and desktop sizes, and provide the English and Arabic variant for every frame. Keep each screen's states grouped with its base screen so the implementation can map them to actual loading, empty, error, stale, and unavailable responses.

Backend data contract for truthful labels and states:

- Personal profile: `GET/PATCH /api/auth/me` (`name`, `phone`, `location`, `photo_url`, `birth_date`, `language_pref`).
- Pharmacy hub/profile: `GET /api/pharmacies`; `GET/POST /api/auth/profile` for the active workspace. Account hub reports actual memberships and owned count/limit.
- Roles and staff: `/api/pharmacies/{pharmacy_id}/roles`; `/api/auth/staff`; role assignment and invitations under `/api/pharmacies/{pharmacy_id}/...`.
- Activity and summaries: `GET /api/staff/me/activity` is only the current actor's audit feed; `GET /api/staff/me/summary` and the staff summary endpoint report recorded ledger activity.
- Schedules and compensation: `/api/pharmacies/{pharmacy_id}/staff/{user_id}/schedule` and `/compensation`.
- Currency is EGP only. Scanning/OCR is unavailable until a real provider is configured. There is no payroll calculation service.

Treat this brief as design constraints. Do not create new product behavior or add fields that are absent from the data contract.
