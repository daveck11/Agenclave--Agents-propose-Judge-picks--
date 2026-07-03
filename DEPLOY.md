# Deploying Agenclave (a public, clickable demo)

The whole product (React UI + FastAPI API) ships as **one process** from a single
`Dockerfile`. Goal: a public URL anyone can open on a phone, with **no risk of
spending API credits**.

## Run it locally first (sanity check)

```bash
docker build -t agenclave .
docker run --rm -p 8000:8000 -e SECRET_KEY="local-test-secret" agenclave
# open http://localhost:8000  -> Triage works; /about explains the project
```

## Deploy to a host

Any Docker host works. **Render** is the simplest free option:

1. Push this branch to GitHub.
2. Render → **New → Web Service** → connect the repo.
3. Render auto-detects the `Dockerfile`. Instance type: free/starter is fine.
4. Set environment variables (below) and deploy. You get a `*.onrender.com` URL.

Railway and Fly.io work the same way (both detect the `Dockerfile`; Fly: `fly launch`).

## Environment variables

| Var | Required | Notes |
|-----|----------|-------|
| `SECRET_KEY` | **Yes** | Any long random string. The dev default must **not** ship publicly (it signs JWTs). |
| `PORT` | Auto | Render/Railway/Fly inject this; the image honours it. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `BLACKBOX_API_KEY` | **No - leave UNSET on the public demo** | See security note. |

## Security: the public demo must not spend money

- **Do NOT set provider API keys on the public instance.** Without them, live runs
  simply can't fire, so a random visitor can never trigger paid Anthropic/OpenAI/
  Blackbox calls. Triage is free and fully works; live best-of-N + trust-scored
  routing runs only when a key is set (locally or on a private instance).
- Want to demo a *live* run for Roger? Do it locally or on a private instance with keys
  set - not on the public URL.

## Good to know

- **SQLite is ephemeral here.** The DB lives at `/app/data` and resets on redeploy.
  Fine for a demo. To persist accounts, attach a disk/volume (Render Disk, Fly Volume)
  mounted at `/app/data`.
- **Image is torch-free.** It installs `requirements-serve.txt` (the runtime subset),
  not the full training stack - fast builds, small image. Use `requirements.txt` only
  to retrain models or run tests.
- The trained classifier (`models/`) is baked into the image, so triage works out of
  the box; live best-of-N needs a provider key (see above).

## Before you share the link (checklist)

1. Open the URL on a phone, logged out - Triage returns a result, `/about` loads, no
   console errors.
2. `SECRET_KEY` is set; no provider keys on the public instance.
3. The repo link in `frontend/src/pages/AboutPage.jsx` (`REPO_URL`) points at the real
   public repo.
