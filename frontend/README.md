# Agenclave, Frontend (Stage 1 demo)

A minimal single-page React + Vite app for the Agenclave bug-triage classifier.
Enter an issue title and body, click **Triage**, and see the predicted label,
severity, their confidences, and the top contributing tokens.

## Run

```bash
npm install
npm run dev
```

Then open the printed URL (default http://localhost:5173).

## Backend

The app expects the FastAPI service on **http://localhost:8000**. Start it from
the repo root with:

```bash
uvicorn agenclave.api.main:app --port 8000
```

The Vite dev server proxies `/triage` and `/health` to `:8000` (see
`vite.config.js`), so the app uses relative fetch URLs and there is no CORS
setup to do.

If the API is down you get a friendly error; if it returns **503** (models not
trained yet), the app tells you to train the classifier and restart the API.

## Build

```bash
npm run build   # type-free production build, proves the app compiles
```

## Notes

- Plain React + Vite + plain CSS. No routing, no state library, no UI framework.
- API contract: `POST /triage` with `{ title, body }` returns
  `{ label, confidence, severity, severity_confidence, top_tokens }`.
