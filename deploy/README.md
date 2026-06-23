# Deploying mymusicapp to Azure

Runs the whole app as a single container on **Azure App Service for Containers**,
with the music library and database on **mounted Azure Files shares**, gated by
**Easy Auth** (Microsoft Entra ID). Images are built and shipped by the
`Deploy to Azure` GitHub Actions workflow.

```
Browser ─▶ Easy Auth (Entra ID) ─▶ Web App container (uvicorn → FastAPI)
                                       ├── serves frontend/dist (UI)
                                       └── /api/* incl. range streaming
   Azure Files mounts:  /music (library)   /data (music.db + covers)
```

## One-time setup

Install the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
and `az login` first. Edit the variables at the top of each script (names marked
"globally unique" must be unique across Azure).

1. **Provision infrastructure**
   ```bash
   ./deploy/azure-setup.sh
   ```
   Creates the resource group, ACR, storage account + `music`/`data` shares,
   App Service plan, and the Web App (shares mounted at `/music` and `/data`).
   Prints the GitHub **Variables** to set.

2. **Create the GitHub OIDC identity**
   ```bash
   ./deploy/github-oidc-setup.sh
   ```
   Prints the GitHub **Secrets** to set. Add all secrets + variables under
   *repo → Settings → Secrets and variables → Actions*:
   - Secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
   - Variables: `ACR_NAME`, `AZURE_RESOURCE_GROUP`, `AZURE_WEBAPP_NAME`

3. **Ship the image** — push to `main` (or run the *Deploy to Azure* workflow
   manually). It builds the container, pushes to ACR, and points the Web App at
   the new tag.

4. **Upload your music** to the `music` share, e.g. with
   [azcopy](https://learn.microsoft.com/azure/storage/common/storage-use-azcopy-v10):
   ```bash
   azcopy copy "/path/to/your/music/*" \
     "https://<STORAGE_ACCOUNT>.file.core.windows.net/music?<SAS>" --recursive
   ```
   (Azure Storage Explorer works too.) Then open the app and click **Rescan** —
   the scanner reads `/music` and writes `music.db` + covers to `/data`.

5. **Lock it down**
   ```bash
   ./deploy/easy-auth-setup.sh
   ```
   Enables Entra ID Easy Auth (single-tenant). Optionally restrict to specific
   accounts via *Entra ID → Enterprise applications → Properties: Assignment
   required = Yes*. See the script header for the equivalent Portal click-path.

## Notes & caveats

- **Single instance only.** SQLite over SMB (Azure Files) is safe for one
  instance with one writer (the scanner). Do **not** scale out — concurrent
  writers can corrupt the DB. The plan is created with one worker + Always On.
- **Stable paths.** Track `file_path`s are absolute but the library is always
  mounted at `/music`, so they stay valid across redeploys. Re-run Rescan only
  when the library changes.
- **Cost.** An Always-On Basic plan plus audio egress bandwidth are the main
  ongoing costs; Standard Azure Files is plenty for personal streaming.
- **Updating the app.** Just push to `main`; the workflow rebuilds and redeploys.
  Your music and DB live on the mounts, so they survive deploys.
