# Adish's Clinderma changes

## Handoff period

- Date range: 12-13 October 2026
- Branch: `main`
- Includes the already-pushed commit `84ddcac` (`feat: support live admin chat and offer context`) and the follow-up implementation committed with this document.
- Existing demo/seed data has been retained. New operational changes are persisted and reflected in the UI.

## Executive summary

The chatbot and administration experience were moved away from placeholder behavior toward database-backed operations. The main work covers clinically meaningful escalation, real chat lifecycle state, live admin takeover, offer-aware product recommendations, persistent orders/leads, role-based authentication, doctor-focused dashboards, and more useful admin analytics.

## Chatbot and response behavior

### Offer-aware answers

- `chat.py` now loads active offers from the offers table for each request.
- `rag_engine.py` answers explicit offer, discount, coupon, and promotion questions using only currently valid database records.
- Product recommendations include applicable active offers.
- Product-specific offers are matched against configured applicable products; global offers remain eligible.
- The bot explicitly says when no valid offer exists instead of inventing a discount or coupon code.

### Response completeness

- Generated answers are compacted at complete sentence boundaries.
- Incomplete/truncated LLM output falls back to a complete grounded response.
- The response target was increased to roughly 60-70 words when the question needs that detail.
- Formatting cleanup removes unnecessary headings, article-style lead-ins, and encoded spacing without cutting off the final thought.

### Persistent order tracking

- Removed dependence on fabricated mock orders as the default runtime source.
- Added a persistent `orders` table and database order provider.
- Added admin order upsert support through `PUT /api/admin/orders/{order_id}`.
- Chat order tracking and revenue analytics now read the same stored operational order data.

## Clinical triage and escalation

### Semantic escalation logic

- Added `backend/app/services/clinical_triage.py`.
- Triage now composes symptom concepts, severity/intensity, persistence, progression, visible skin changes, personal reporting, and nearby negation.
- The classifier recognizes paraphrases rather than requiring one exact keyword string.
- Negated warning signs such as "no trouble breathing or facial swelling" do not create false critical escalations.
- Safety-critical deterministic overrides remain for airway symptoms, facial/oral/throat swelling, serious allergic reactions, spreading hives, severe infection, chemical/barrier injury, and dangerous active combinations.
- Prescription-retinoid and dosage questions enter clinician review.
- Severe/persistent itching with visible skin changes enters moderate clinical review.
- Explicit requests for a human/skin coach enter the support queue.
- Clinical triage runs before phone gating, products, order handling, retrieval, and LLM synthesis so urgent cases cannot be hidden by another intent.

### Queue correctness

- Real clinical handoffs are separated from records created only for lead capture.
- Severity, reason, AI clinical summary, transcript, notes, and resolution state are persisted.
- Critical, pending, and resolved filters use stored values rather than placeholder cards.
- Admin takeover can create a handoff record, but queue and dashboard calculations exclude lead-only records.

## Chat lifecycle and live operations

### Real live/ended status

- Added persistent `chat_session_state` storage.
- A chat is live based on actual customer activity rather than a static seed status.
- After two minutes of customer inactivity, the widget asks whether the user wants to continue.
- If there is no response within another 30 seconds, the chat is persisted as ended.
- Ending an inactive chat does not automatically resolve its clinical escalation ticket.
- Returning customer activity restores the session to live state.

### Admin takeover and handback

- Customer messages continue to be recorded while the bot is paused for admin takeover.
- Admins can send direct replies from Customer Chats.
- Admins can hand the conversation back to the bot.
- Customer and admin views poll for updates, so takeover, messages, handback, inactivity prompts, and ended state appear without a manual page refresh.
- The implementation uses short polling, not WebSockets.

### Customer Chat administration

- Customer Chats now includes all real sessions, not only escalated handoffs.
- Added status filters for live, ended, clinically escalated, and taken-over conversations.
- Added inclusive From/To date filtering based on the actual conversation start time.
- Search, date, and status filters work together.
- Added escalation and lifecycle badges to conversation cards.
- Added date-range validation and a clear-date action.

## Skin Coach Dashboard

- The Doctor Console sidebar and the top navbar now open the exact same `/dashboard.html` page.
- The dashboard uses the single name **Skin Coach Dashboard** everywhere.
- The old browser HTTP Basic Auth prompt was removed.
- The dashboard has a doctor-ID login and stores a doctor JWT in the browser, so switching pages does not prompt for credentials repeatedly.
- Clinical APIs remain protected even though the HTML shell itself can load without authentication.
- The dashboard now focuses on doctor-relevant information:
  - patient intakes;
  - pending clinical reviews;
  - total escalated clinical cases;
  - resolved cases;
  - critical/urgent workload over seven days;
  - dermatological concern distribution;
  - clinical escalation queue and transcripts;
  - doctor observations and case resolution;
  - patient intake registry.
- Removed doctor-irrelevant cards and labels such as model latency, grounding confidence, autonomous AI resolution rate, and CRM sync rate.

## Admin Funnel and Revenue dashboard

- Redesigned the Admin/Viewer analytics page with clearer visual hierarchy and responsive cards.
- Added a default 30-day reporting window.
- Added KPIs for:
  - website visitors;
  - chats started;
  - engaged patients/leads;
  - checkout intent;
  - persisted orders;
  - visitor-to-order conversion;
  - attributed revenue;
  - average order value.
- Added largest-stage-drop-off guidance.
- Added order-status breakdown chips.
- Improved funnel and order/revenue chart presentation.
- Analytics CSV downloads now include the JWT so authenticated exports work correctly.

## Authentication, roles, and demo access

- Admin users use salted PBKDF2-SHA256 password hashes.
- Existing legacy password hashes remain valid and are upgraded after successful login.
- JWTs are signed and expire after 24 hours.
- Startup seeds each missing development role without overwriting an existing account:
  - Admin: `admin` / `clinderma@admin2026`
  - Doctor: `doctor` / `doctor@clinderma2026`
  - Viewer: `viewer` / `viewer@clinderma2026`
- Restored one-click Admin, Doctor, and Viewer demo login buttons on the console.
- The Doctor role sees **Skin Coach Dashboard** instead of Funnel & Revenue.
- Admin and Viewer retain the commercial Funnel & Revenue dashboard.
- The standalone Skin Coach Dashboard accepts the Doctor role and keeps a separate doctor session token.
- Demo credentials are intentionally embedded for demonstration convenience and must be removed or changed before production exposure.

## Data providers, persistence, and platform work

- Default CRM mode is now `local_db`; valid lead changes persist even without an external Kylas account.
- Kylas remains available with `CRM_PROVIDER=kylas_api` and a real `KYLAS_API_KEY`.
- Default order provider is now `clinderma_db`.
- Added database tables/migrations for session lifecycle, orders, and chat metrics.
- Added safer idempotent migrations with rollback handling.
- Added PostgreSQL compatibility for auto-increment IDs and returned inserted IDs.
- Restricted CORS to configured origins through `CORS_ORIGINS` instead of combining wildcard origins with credentials.
- Updated `.env.example` and README configuration guidance.

## Main API changes

- `GET /api/chat/{session_id}/updates` - admin/system updates plus takeover and lifecycle state.
- `POST /api/chat/{session_id}/inactivity-prompt` - persist the continuation prompt once.
- `POST /api/chat/{session_id}/end` - persist inactivity-based chat ending.
- `GET /api/admin/chats` - supports `status`, `search`, `date_from`, and `date_to`.
- `POST /api/admin/chats/takeover` - pause bot handling and mark admin takeover.
- `POST /api/admin/chats/message` - send an admin response into the transcript.
- `POST /api/admin/chats/handback` - return handling to the bot.
- `PUT /api/admin/orders/{order_id}` - persist order/fulfilment changes.
- `GET /api/dashboard/stats` - doctor-focused clinical counts and seven-day workload.
- Analytics order responses now include `average_order_value` and `status_breakdown`.

## Tests and verification

The following checks passed on 13 October 2026:

- Full backend suite: **47 tests passed**.
- Python compilation for the modified APIs and application entry point.
- JavaScript parsing for `frontend/admin.html` and `frontend/dashboard.html`.
- Git whitespace/diff validation.

Coverage includes semantic triage and negation, critical/moderate cases, session inactivity lifecycle, durable phone gating, live takeover, offers, response completion, persistent orders, role authentication, dashboard protection, date filtering, analytics, exports, and RBAC.

## Files most relevant to review

- `backend/app/services/clinical_triage.py`
- `backend/app/services/session_manager.py`
- `backend/app/services/rag_engine.py`
- `backend/app/api/chat.py`
- `backend/app/api/handoff.py`
- `backend/app/api/dashboard.py`
- `backend/app/api/analytics.py`
- `backend/app/core/auth.py`
- `backend/app/core/db.py`
- `frontend/widget/chat-widget.js`
- `frontend/admin.html`
- `frontend/dashboard.html`

## Teammate setup notes

1. Pull `main` and restart the backend so migrations run.
2. Keep `CRM_PROVIDER=local_db` and `ORDER_PROVIDER=clinderma_db` for a self-contained local demo.
3. Use the one-click role buttons on `/admin.html`.
4. Use the Doctor account for `/dashboard.html`.
5. For production, set a stable strong `JWT_SECRET`, configure explicit `CORS_ORIGINS`, replace demo credentials, and remove one-click login shortcuts.
