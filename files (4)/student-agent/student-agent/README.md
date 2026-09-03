# Student Intelligence System — Agent Prototype

A working MVP slice of the full architecture: a FastAPI backend with a Claude
tool-calling agent, a simple web chat page, and a WhatsApp webhook adapter,
all sharing one identical `/agent/message` pipeline.

This is a **simplified subset** of the full schema/architecture document —
enough tables and tools to prove the real thing end to end (student profile,
missing documents, academic results with deterministic averaging, welfare
case intake) without building all 20+ tables on day one. See the architecture
doc's Section 21 (MVP Definition) for what's intentionally deferred.

## What you need before this runs

1. **Python 3.11+** on a machine with internet access (this was written in an
   offline sandbox — syntax-checked but never executed against a live API,
   so read through it once before trusting it in front of real students).
2. **An Anthropic API key** — https://console.anthropic.com
3. **A WhatsApp Business Cloud API app** (if you want the WhatsApp side working):
   - Create a Meta developer app: https://developers.facebook.com/apps
   - Add the WhatsApp product, get a temporary access token + phone number ID
     from "API Setup"
   - You'll need a public HTTPS URL for the webhook (use `ngrok` for local
     testing: `ngrok http 8000`, then point the webhook at
     `https://<ngrok-url>/webhook/whatsapp`)
   - Set the same "Verify Token" in both Meta's dashboard and your `.env`

   **If the "extension" you already installed is something other than the
   official Cloud API** (Twilio, 360dialog, whatsapp-web.js, etc.) — you don't
   need to redo any of the rest of this system. Only `app/whatsapp/client.py`
   (sending messages) and the top of `app/routers/whatsapp.py` (receiving
   messages) are provider-specific. Tell me which one and I'll rewrite just
   those two files.

## Setup

```bash
cd student-agent
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: at minimum set ANTHROPIC_API_KEY and JWT_SECRET
```

Generate a real JWT secret:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Run it

```bash
python -m app.seed        # creates one sample university + student
uvicorn app.main:app --reload --port 8000
```

Open:
- `http://localhost:8000/app/index.html` — the web chat
- `http://localhost:8000/docs` — interactive API docs (Swagger UI)

**Logging in as the seeded test student:** the seed script prints a phone
number (`+213500000000`). On the web chat, enter that number, click "Send
code" — since no SMS provider is wired up yet, the 6-digit OTP is printed to
your terminal (search for `[DEV ONLY] OTP for`). Enter it in the app.

## Wiring up WhatsApp

1. Start the server and expose it publicly (`ngrok http 8000` for testing).
2. In the Meta app dashboard, set the webhook URL to
   `https://<your-url>/webhook/whatsapp` and the verify token to whatever you
   put in `WHATSAPP_VERIFY_TOKEN` in `.env`.
3. Message your WhatsApp test number from a phone. First message: it'll ask
   for your student number, then send an OTP (again printed to console until
   you wire up real SMS) to link that WhatsApp number to a student record.
4. After linking, ask it things like "what documents am I missing?" —
   identical agent, identical tools, identical audit trail as the web chat.

## What's real vs. stubbed right now

| Piece | Status |
|---|---|
| Agent tool-calling loop (Claude) | Real — will actually call the API once you add a key |
| Fast-path routing (missing docs, average, records) | Real, no LLM call needed for these |
| Database + audit logging | Real (SQLite by default; swap `DATABASE_URL` to Postgres for production) |
| Web chat | Real, functional, deliberately plain — swap for the Next.js version from the architecture doc when you want richer UI |
| WhatsApp send/receive | Real against the official Cloud API, **not yet tested against a live account** since this was built offline |
| OTP delivery (SMS) | **Stubbed** — codes print to console. Wire up an SMS provider (Twilio Verify, Africa's Talking, etc.) or route OTPs through WhatsApp once a number is linked |
| Document upload + OCR extraction pipeline | **Not yet built** — this prototype covers profile/documents-status/academic-results/welfare; the document upload + vision-extraction pipeline (architecture doc Section 7) is the next piece worth building once this loop is confirmed working end to end |
| Staff web dashboard | **Not yet built** — the staff REST endpoints exist (`/staff/search-students`, `/documents/{id}/verify`, `/academic-results/{id}/verify`) but there's no staff login flow or UI yet; test them via `/docs` with a manually-created `staff_users` row for now |

## Suggested next steps, in order

1. Get this running locally end-to-end with the seeded student, confirm the
   agent actually responds sensibly to a few real questions.
2. Wire up one real SMS provider for OTP delivery.
3. Connect WhatsApp for real, test the identity-linking flow with your own number.
4. Build the document upload endpoint + vision-extraction pipeline (Section 7
   of the architecture doc) — this is the biggest remaining piece.
5. Add a minimal staff login + document/academic verification UI.
