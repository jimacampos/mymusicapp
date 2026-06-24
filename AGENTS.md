# AGENTS.md

Operational notes for AI agents (and humans) working on this repo. Read this
before touching anything under `deploy/`, the `Dockerfile`, or the GitHub
Actions workflow — it captures hard-won gotchas from the Azure rollout that are
not obvious from the code.

## What this is

A self-hosted "Spotify for me": **FastAPI + SQLite** backend that scans a local
music library and streams audio with HTTP Range requests, plus a **React (Vite +
TypeScript)** frontend. In production the backend serves the built UI from
`frontend/dist`, so the whole app runs as **one process / one container**. See
`README.md` for local dev and the API surface.

## Deployed architecture (Azure)

```
Browser ─▶ Easy Auth (Entra ID) ─▶ Web App container (uvicorn → FastAPI)
                                       ├── serves frontend/dist (UI)
                                       └── /api/* incl. range streaming
   Azure Files mounts:  /music (library)   /data (music.db + covers)
```

- **Hosting:** Azure App Service for Containers (Linux), single B1 instance,
  Always On, 1 worker.
- **Image:** built by `az acr build` (server-side) and stored in ACR; the Web
  App pulls it using its **system-assigned managed identity** (`AcrPull`).
- **Storage:** music library and the SQLite DB + cover art live on **mounted
  Azure Files shares** (`/music`, `/data`), so they survive redeploys.
- **Auth:** Microsoft Entra ID "Easy Auth" (App Service Authentication v2) runs
  as a reverse proxy in front of the container — no app code involved.
- **CI/CD:** push to `main` → `Deploy to Azure` workflow → `az acr build` →
  `az webapp config container set` + restart. Auth is via GitHub OIDC (no stored
  cloud credentials).

## Live resources

These match the **default values** at the top of the `deploy/*.sh` scripts.
Names are overridable via env vars (e.g. `LOCATION=centralus ./deploy/azure-setup.sh`).

| Thing                | Value                                            |
|----------------------|--------------------------------------------------|
| Region               | `centralus` (see quota gotcha below)             |
| App URL              | https://whitefieldslistens-web.azurewebsites.net |
| Resource group       | `whitefieldslistens-rg`                          |
| Container registry   | `whitefieldslistens` (ACR)                        |
| Storage account      | `whitefieldslistensstore` (shares: `music`, `data`) |
| App Service plan     | `whitefieldslistens-plan` (B1 Linux)             |
| Web App              | `whitefieldslistens-web`                          |
| Auth app registration| `whitefieldslistens-auth` (single-tenant)        |
| Deploy OIDC identity | app reg used by GitHub Actions (federated)       |

Don't hardcode subscription/tenant/client IDs in the repo — discover at runtime:
`az account show`, and `az ad app list --display-name whitefieldslistens-auth --query '[0].appId' -o tsv`.

GitHub config (already set; needed by the workflow):
- **Secrets:** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- **Variables:** `ACR_NAME`, `AZURE_RESOURCE_GROUP`, `AZURE_WEBAPP_NAME`

## Setup scripts (`deploy/`)

Run in this order for a fresh environment (all are idempotent / env-overridable):

1. `find-region.sh` — probe regions for App Service compute quota (see gotcha #1).
2. `azure-setup.sh` — provision RG, ACR, storage + shares, plan, Web App; mounts
   shares; grants the Web App's identity `AcrPull`; sets app settings + Always On.
3. `github-oidc-setup.sh` — create the GitHub OIDC federated identity; grants
   **Contributor on the ACR** (needed for `az acr build`, see gotcha #2) and
   Website Contributor on the RG. Prints the GitHub secrets to set.
4. `easy-auth-setup.sh` — create/lock down Entra ID sign-in (see gotchas #4–6).

## Operational runbook

- **Redeploy the app:** push to `main` (or run the *Deploy to Azure* workflow).
  The workflow has `paths-ignore` for `**.md` and `deploy/**`, so doc/script-only
  commits do **not** trigger a rebuild.
- **Add/replace music:** upload to the `music` Azure Files share (azcopy or
  Storage Explorer), then click **Rescan** in the app (or `POST /api/rescan`).
- **Choose who can sign in:** Portal → Entra ID → Enterprise applications →
  `whitefieldslistens-auth` → Properties: *Assignment required = Yes*, then
  *Users and groups* → add the allowed accounts.
- **Logs:** `az webapp log tail -g whitefieldslistens-rg -n whitefieldslistens-web`.
- **Health check:** `curl https://whitefieldslistens-web.azurewebsites.net/api/health`.

## Gotchas (these cost real time — don't re-learn them)

1. **App Service quota is 0 per-region on Visual Studio Enterprise subs.**
   `az appservice plan create` fails with "Current Limit (Total VMs): 0" in many
   regions (eastus, eastus2, westus2, westus3 all failed); `centralus` worked.
   Quota is **per region**. Use `deploy/find-region.sh` to find one with quota.

2. **A federated (OIDC) service principal cannot `az acr login`.** Federated
   logins have no AAD refresh token, so `az acr login` (even `--expose-token` or
   a manual oauth2 token exchange) returns 401 (`CONNECTIVITY_REFRESH_TOKEN_ERROR`).
   **Fix:** build server-side with `az acr build` (management-plane auth). That
   requires **Contributor** on the ACR — `AcrPush` is not enough (it lacks the
   `scheduleRun` permission). The workflow and `github-oidc-setup.sh` already do this.

3. **Web App pull = `ACRTokenRetrievalFailure ... Unauthorized`.** The Web App's
   system-assigned identity needs `AcrPull` on the registry **and**
   `acrUseManagedIdentityCreds=true`. `azure-setup.sh` sets both, but the grant
   occasionally doesn't land on first run — re-grant `AcrPull` to the Web App's
   identity and restart if you see this.

4. **Easy Auth: "Cannot use auth v2 commands when the app is using auth v1."**
   The site can carry a legacy v1 ("classic") auth config that blocks the
   `az webapp auth` (v2) CLI. **Fix:** write config via REST — disable v1 with a
   PUT to `config/authsettings` (`enabled:false`), then PUT `config/authsettingsV2`
   directly. `easy-auth-setup.sh` does this with `az rest`.

5. **Easy Auth: blank page at `/.auth/login/aad/callback` (token rejected).**
   The login ID token's `aud` is the **bare client-id GUID**, not `api://<clientId>`.
   If `allowedAudiences` only lists `api://<clientId>`, validation fails silently
   → blank callback. **Fix:** include *both* `api://<clientId>` and the bare
   `<clientId>` in `allowedAudiences` (the script does this now).

6. **Easy Auth: `AADSTS650056` "Misconfigured application".** A CLI-created app
   registration has **no API permissions and no admin consent** (the Portal
   wizard adds these automatically). **Fix:** add Microsoft Graph `User.Read`
   (delegated) and grant tenant admin consent
   (`az ad app permission add ... && az ad app permission admin-consent ...`).
   `easy-auth-setup.sh` now does this.

## Constraints — do not violate

- **Single instance only.** SQLite lives on an SMB-mounted Azure Files share;
  concurrent writers corrupt it. Do **not** scale the plan out (>1 instance) or
  add a second writer. The scanner is the only writer.
- Track `file_path`s are absolute but the library is always mounted at `/music`,
  so they stay valid across redeploys. Re-run Rescan only when the library changes.
