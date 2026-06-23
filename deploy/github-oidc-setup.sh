#!/usr/bin/env bash
#
# Create a GitHub OIDC (federated) identity so the "Deploy to Azure" workflow
# can log in to Azure without storing a client secret, then grant it the rights
# to push images to ACR and update the Web App.
#
# Run once after azure-setup.sh. Requires the Azure CLI (`az login`) with
# permission to create app registrations and role assignments.
set -euo pipefail

# ---- Configure these (match azure-setup.sh) -------------------------------
GITHUB_REPO="${GITHUB_REPO:-jimacampos/mymusicapp}"   # owner/repo
BRANCH="${BRANCH:-main}"
RESOURCE_GROUP="${RESOURCE_GROUP:-whitefieldslistens-rg}"
ACR_NAME="${ACR_NAME:-whitefieldslistens}"
APP_NAME="${APP_NAME:-whitefieldslistens-github-deploy}"   # Entra app registration display name
# ---------------------------------------------------------------------------

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"

echo "==> App registration + service principal"
APP_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
az ad sp create --id "$APP_ID" --output none 2>/dev/null || true

echo "==> Federated credential for $GITHUB_REPO@$BRANCH"
az ad app federated-credential create --id "$APP_ID" --parameters "{
  \"name\": \"github-${BRANCH}\",
  \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:${GITHUB_REPO}:ref:refs/heads/${BRANCH}\",
  \"audiences\": [\"api://AzureADTokenExchange\"]
}" --output none

echo "==> Role assignments (AcrPush on registry, Website Contributor on RG)"
ACR_ID="$(az acr show --name "$ACR_NAME" --query id -o tsv)"
az role assignment create --assignee "$APP_ID" --role AcrPush --scope "$ACR_ID" --output none
az role assignment create --assignee "$APP_ID" --role "Website Contributor" \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}" --output none

cat <<EOF

Done. Set these GitHub Actions *Secrets* (Settings -> Secrets and variables -> Actions):
  AZURE_CLIENT_ID       = $APP_ID
  AZURE_TENANT_ID       = $TENANT_ID
  AZURE_SUBSCRIPTION_ID = $SUBSCRIPTION_ID

(Variables ACR_NAME / AZURE_RESOURCE_GROUP / AZURE_WEBAPP_NAME were printed by azure-setup.sh.)
EOF
