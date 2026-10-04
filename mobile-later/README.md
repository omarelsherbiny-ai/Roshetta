# Roshetta — Mobile App (Phase 2)

This directory is designated for the native mobile build in Phase 2.

## Strategy:
1. **Architecture Continuity**:
   - The `/server` REST API and `/agents` LangGraph orchestration engine remain 100% unchanged.
   - All API endpoints follow the contract defined in `../shared-schema/openapi.yaml`.

2. **Mobile Framework Options**:
   - **Option A (Capacitor wrapper)**: Direct wrap of the mobile-first Next.js web application with native camera plugins (`@capacitor/camera`), biometric authentication, and offline sqlite sync.
   - **Option B (React Native / Expo)**: Porting the `/web/src/components` UI to React Native components using the exact same state machine and API client.

3. **Key Native Mobile Capabilities**:
   - Hardware camera auto-focus, edge detection, and document perspective-warp before upload.
   - Offline SQLite action queue: snap documents or log offline sales, sync automatically when reconnecting.
   - Background push notifications for low-stock warnings and customer medication follow-up reminders.
