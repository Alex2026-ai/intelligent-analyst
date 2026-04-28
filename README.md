# Intelligent Analyst Enterprise

Entity resolution and decision-evidence platform for regulated data workflows.

Intelligent Analyst combines deterministic matching, fuzzy/vector resolution,
human review boundaries, and verifiable evidence artifacts. This public-safe
branch includes the marketing website, an unauthenticated browser demo, the
authenticated dashboard shell, backend service code, and public protocol docs.

## Try It First

The fastest path is the web preview. It does not require Firebase, Google
Cloud, API keys, or customer data.

```bash
cd web
npm install
npm run dev
```

Open:

- `http://localhost:5173/` for the marketing website.
- `http://localhost:5173/preview` for the public dashboard demo.
- `http://localhost:5173/app` for the authenticated dashboard shell.

The `/preview` route uses bundled sample data, simulates an upload locally,
updates the sample batch history, and generates a sample evidence-pack ZIP in
the browser. No files leave your machine.

## Public Readiness Gate

Before opening a PR or publishing the repo, run:

```bash
cd web
npm run test:public
```

This builds the website and checks that the public preview bundle contains the
expected demo flow, public assets, and no old debug/demo strings. The same gate
runs in GitHub Actions through `.github/workflows/public-web-smoke.yml`.

## What Is Included

- Marketing website source.
- Interactive public dashboard preview.
- Authenticated dashboard shell.
- Backend source for review and local development.
- Public IAVP protocol documentation.
- Public-safe Firebase hosting example: `firebase.example.json`.

## What Is Intentionally Excluded

- Real Firebase targets and Cloud Build triggers.
- Operator deployment scripts.
- Production snapshots, diagnostics logs, and runbooks.
- Private users, customer-like records, and local auth files.
- Internal pricing, sales, legal, and partner strategy notes.
- Raw sanctions or AML demo datasets.

This is deliberate. A public repo should show the product and the engineering
shape without publishing private operating details.

## Known Public Limits

- `/preview` is an interactive sample demo, not the full enterprise backend.
- `/app` requires real Firebase and backend environment variables.
- Public sample upload is local simulation only.
- The sample evidence pack shows the artifact shape without exposing customer
  data.
- Production deployment is environment-specific and must be configured outside
  this public repo.

## Environment Configuration

Use the web templates as starting points:

```bash
cp web/.env.demo.example web/.env.local
```

For the authenticated dashboard, replace the placeholder Firebase and backend
values in `web/.env.local`. Without those values, sign-in is intentionally
disabled instead of failing unpredictably.

## Web Commands

```bash
cd web
npm install
npm run dev
npm run build
npm run test:public
```

## Backend Notes

Backend source is included for transparency and local development, but public
deployment files are not included. Use `.env.example` as the starting point and
provide your own cloud project, Firebase project, storage buckets, and secrets.

For local checks, point API clients at your own local or deployed backend:

```bash
backend/test-batch.sh <firebase_id_token> http://localhost:8080
```

## Project Structure

```text
intelligent-analyst-enterprise/
├── apps/                 # Split API/worker service modules
├── backend/              # Backend service code and tests
├── docs/                 # Public protocol docs only
├── functions/            # Firebase function source
├── packages/             # Shared Python models
├── web/                  # Marketing site, preview, and dashboard shell
├── firebase.example.json # Public-safe hosting example
└── README.md
```

## Public Protocol Docs

See `docs/README.md` for the curated public documentation set, including:

- IAVP public spec.
- Evidence schema.
- Verification walkthrough.
- Transparency public API.
- External verification demo.

## Security Posture

- No committed `.env` files.
- No committed user registry.
- No production logs or infrastructure snapshots.
- No live deployment targets in public configuration defaults.
- Authenticated dashboard requires explicit Firebase configuration.
- Backend secrets must come from environment variables or a secret manager.

## License

Proprietary source-available license. See `LICENSE`.

---

Entity resolution with verifiable evidence.
