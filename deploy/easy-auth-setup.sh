#!/usr/bin/env bash
#
# Lock the app behind Microsoft Entra ID using App Service Authentication
# ("Easy Auth"). This runs as a reverse proxy in front of the container, so the
# app itself needs no code changes — unauthenticated requests are redirected to
# the Entra login page.
#
# EASIEST PATH (recommended): do this in the Azure Portal instead of this
# script — it auto-creates the app registration and wires everything up:
#   Portal -> your Web App -> Settings -> Authentication -> Add identity provider
#     Provider:                 Microsoft
#     App registration type:    Create new app registration
#     Supported account types:  "Current tenant - Single tenant"   <-- restricts to your org
#     Restrict access:          "Require authentication"
#     Unauthenticated requests: "HTTP 302 Redirect to log in (recommended)"
#   Then optionally lock to specific people: Entra ID -> Enterprise applications
#   -> <this app> -> Properties: "Assignment required" = Yes, then Users and
#   groups -> add only the accounts allowed in.
#
# The script below does the same via CLI. Requires `az login` and rights to
# create an app registration. Run after the app is deployed and reachable.
set -euo pipefail

# ---- Configure these (match azure-setup.sh) -------------------------------
RESOURCE_GROUP="${RESOURCE_GROUP:-whitefieldslistens-rg}"
WEBAPP_NAME="${WEBAPP_NAME:-whitefieldslistens-web}"
AUTH_APP_NAME="${AUTH_APP_NAME:-whitefieldslistens-auth}"   # Entra app registration for sign-in
# ---------------------------------------------------------------------------

TENANT_ID="$(az account show --query tenantId -o tsv)"
APP_URL="https://${WEBAPP_NAME}.azurewebsites.net"
CALLBACK="${APP_URL}/.auth/login/aad/callback"

echo "==> Single-tenant app registration ($AUTH_APP_NAME)"
AUTH_CLIENT_ID="$(az ad app create \
  --display-name "$AUTH_APP_NAME" \
  --sign-in-audience AzureADMyOrg \
  --web-redirect-uris "$CALLBACK" \
  --enable-id-token-issuance true \
  --query appId -o tsv)"
az ad sp create --id "$AUTH_CLIENT_ID" --output none 2>/dev/null || true

echo "==> Client secret"
AUTH_CLIENT_SECRET="$(az ad app credential reset \
  --id "$AUTH_CLIENT_ID" --display-name easyauth --query password -o tsv)"

echo "==> Store the secret as an app setting"
az webapp config appsettings set --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" \
  --settings MICROSOFT_PROVIDER_AUTHENTICATION_SECRET="$AUTH_CLIENT_SECRET" --output none

echo "==> Enable Easy Auth (require authentication, redirect to login)"
az webapp auth microsoft update --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" \
  --client-id "$AUTH_CLIENT_ID" \
  --client-secret-setting-name MICROSOFT_PROVIDER_AUTHENTICATION_SECRET \
  --issuer "https://login.microsoftonline.com/${TENANT_ID}/v2.0" \
  --allowed-token-audiences "api://${AUTH_CLIENT_ID}" --yes --output none
az webapp auth update --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" \
  --enabled true \
  --action RedirectToLoginPage \
  --redirect-provider azureactivedirectory \
  --unauthenticated-client-action RedirectToLoginPage --output none

cat <<EOF

Done. $APP_URL now requires Entra ID sign-in.

To restrict to specific people (not the whole tenant):
  Portal -> Entra ID -> Enterprise applications -> $AUTH_APP_NAME
    Properties: "Assignment required?" = Yes
    Users and groups: add only the accounts allowed in.
EOF
