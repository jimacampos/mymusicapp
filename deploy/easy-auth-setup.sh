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
#
# It writes the v2 auth config via the REST API. This is deliberate: the
# `az webapp auth` (v2) command group refuses to run if the site still has a
# legacy v1 ("classic") auth config, so we clear v1 and PUT v2 directly. The
# script is idempotent — re-running reuses the existing app registration/secret.
set -euo pipefail

# ---- Configure these (match azure-setup.sh) -------------------------------
RESOURCE_GROUP="${RESOURCE_GROUP:-whitefieldslistens-rg}"
WEBAPP_NAME="${WEBAPP_NAME:-whitefieldslistens-web}"
AUTH_APP_NAME="${AUTH_APP_NAME:-whitefieldslistens-auth}"   # Entra app registration for sign-in
# ---------------------------------------------------------------------------

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
APP_URL="https://${WEBAPP_NAME}.azurewebsites.net"
CALLBACK="${APP_URL}/.auth/login/aad/callback"
SECRET_SETTING="MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"
API_VER="2022-03-01"
SITE_BASE="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Web/sites/${WEBAPP_NAME}"

echo "==> Find or create single-tenant app registration ($AUTH_APP_NAME)"
AUTH_CLIENT_ID="$(az ad app list --display-name "$AUTH_APP_NAME" --query '[0].appId' -o tsv)"
if [ -z "$AUTH_CLIENT_ID" ]; then
  AUTH_CLIENT_ID="$(az ad app create --display-name "$AUTH_APP_NAME" \
    --sign-in-audience AzureADMyOrg --web-redirect-uris "$CALLBACK" \
    --enable-id-token-issuance true --query appId -o tsv)"
else
  az ad app update --id "$AUTH_CLIENT_ID" --sign-in-audience AzureADMyOrg \
    --web-redirect-uris "$CALLBACK" --enable-id-token-issuance true
fi
az ad sp create --id "$AUTH_CLIENT_ID" --output none 2>/dev/null || true

echo "==> Add Microsoft Graph User.Read + grant admin consent (required for sign-in)"
# Without a listed permission + tenant consent, sign-in fails with AADSTS650056.
GRAPH_API="00000003-0000-0000-c000-000000000000"   # Microsoft Graph
USER_READ="e1fe6dd8-ba31-4d61-89e7-88639da4683d"   # User.Read (delegated)
az ad app permission add --id "$AUTH_CLIENT_ID" --api "$GRAPH_API" \
  --api-permissions "${USER_READ}=Scope" 2>/dev/null || true
az ad app permission admin-consent --id "$AUTH_CLIENT_ID" 2>/dev/null || \
  echo "  (admin-consent failed — grant it in the Portal: app registration -> API permissions -> Grant admin consent for <tenant>)"

echo "==> Ensure a client secret is stored as an app setting"
HAS_SECRET="$(az webapp config appsettings list -g "$RESOURCE_GROUP" -n "$WEBAPP_NAME" \
  --query "[?name=='$SECRET_SETTING'].name | [0]" -o tsv)"
if [ -z "$HAS_SECRET" ]; then
  SECRET="$(az ad app credential reset --id "$AUTH_CLIENT_ID" \
    --display-name easyauth --query password -o tsv)"
  az webapp config appsettings set -g "$RESOURCE_GROUP" -n "$WEBAPP_NAME" \
    --settings "$SECRET_SETTING=$SECRET" --output none
fi

echo "==> Disable any legacy v1 auth so it can't shadow v2"
az rest --method put --url "${SITE_BASE}/config/authsettings?api-version=${API_VER}" \
  --body '{"properties":{"enabled":false}}' --output none 2>/dev/null || true

echo "==> Enable Easy Auth v2 (require authentication, redirect to Entra ID)"
BODY="$(mktemp)"
cat > "$BODY" <<JSON
{
  "properties": {
    "platform": { "enabled": true },
    "globalValidation": {
      "requireAuthentication": true,
      "unauthenticatedClientAction": "RedirectToLoginPage",
      "redirectToProvider": "azureactivedirectory"
    },
    "identityProviders": {
      "azureActiveDirectory": {
        "enabled": true,
        "registration": {
          "openIdIssuer": "https://sts.windows.net/${TENANT_ID}/",
          "clientId": "${AUTH_CLIENT_ID}",
          "clientSecretSettingName": "${SECRET_SETTING}"
        },
        "validation": {
          "allowedAudiences": ["api://${AUTH_CLIENT_ID}", "${AUTH_CLIENT_ID}"]
        }
      }
    },
    "login": { "tokenStore": { "enabled": true } }
  }
}
JSON
az rest --method put --url "${SITE_BASE}/config/authsettingsV2?api-version=${API_VER}" \
  --body "@$BODY" --output none
rm -f "$BODY"

cat <<EOF

Done. $APP_URL now requires Entra ID sign-in.

To restrict to specific people (not the whole tenant):
  Portal -> Entra ID -> Enterprise applications -> $AUTH_APP_NAME
    Properties: "Assignment required?" = Yes
    Users and groups: add only the accounts allowed in.
EOF
