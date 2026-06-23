#!/usr/bin/env bash
#
# Provision Azure infrastructure for mymusicapp.
#
# Creates: resource group, container registry, storage account + two file
# shares (music, data), a Linux App Service plan, and a Web App for Containers
# with the shares mounted at /music and /data and managed-identity ACR pull.
#
# Run once. Requires the Azure CLI (`az login` first). Edit the variables
# below — names marked "globally unique" must be unique across all of Azure.
# Every value can also be overridden via an environment variable without
# editing this file, e.g.:  LOCATION=eastus2 ./deploy/azure-setup.sh
#
# Hitting "Operation cannot be completed without additional quota"? That is an
# App Service compute-quota limit for the region. Find one that works with
# ./deploy/find-region.sh, then re-run with LOCATION=<that region>.
set -euo pipefail

# ---- Configure these ------------------------------------------------------
LOCATION="${LOCATION:-eastus}"
RESOURCE_GROUP="${RESOURCE_GROUP:-whitefieldslistens-rg}"
ACR_NAME="${ACR_NAME:-whitefieldslistens}"               # globally unique, 5-50 alphanumeric
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-whitefieldslistensstore}"  # globally unique, 3-24 lowercase alnum
APP_SERVICE_PLAN="${APP_SERVICE_PLAN:-whitefieldslistens-plan}"
WEBAPP_NAME="${WEBAPP_NAME:-whitefieldslistens-web}"     # globally unique -> https://<name>.azurewebsites.net
SKU="${SKU:-B1}"                          # B1+ required for Always On
MUSIC_SHARE_QUOTA_GB="${MUSIC_SHARE_QUOTA_GB:-100}"      # size of the music file share
DATA_SHARE_QUOTA_GB="${DATA_SHARE_QUOTA_GB:-5}"
IMAGE_NAME="${IMAGE_NAME:-whitefieldslistens}"
# ---------------------------------------------------------------------------

PLACEHOLDER_IMAGE="mcr.microsoft.com/azuredocs/aci-helloworld:latest"

echo "==> Resource group"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

echo "==> Container registry ($ACR_NAME)"
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" \
  --sku Basic --admin-enabled false --output none

echo "==> Storage account ($STORAGE_ACCOUNT)"
az storage account create --resource-group "$RESOURCE_GROUP" --name "$STORAGE_ACCOUNT" \
  --location "$LOCATION" --sku Standard_LRS --kind StorageV2 --output none

STORAGE_KEY="$(az storage account keys list \
  --resource-group "$RESOURCE_GROUP" --account-name "$STORAGE_ACCOUNT" \
  --query '[0].value' -o tsv)"

echo "==> File shares (music, data)"
az storage share-rm create --resource-group "$RESOURCE_GROUP" \
  --storage-account "$STORAGE_ACCOUNT" --name music \
  --quota "$MUSIC_SHARE_QUOTA_GB" --output none
az storage share-rm create --resource-group "$RESOURCE_GROUP" \
  --storage-account "$STORAGE_ACCOUNT" --name data \
  --quota "$DATA_SHARE_QUOTA_GB" --output none

echo "==> App Service plan ($APP_SERVICE_PLAN, $SKU Linux, $LOCATION)"
if ! az appservice plan create --resource-group "$RESOURCE_GROUP" --name "$APP_SERVICE_PLAN" \
  --is-linux --sku "$SKU" --location "$LOCATION" --output none; then
  cat >&2 <<EOF

ERROR: Could not create the App Service plan in '$LOCATION'.
If the message mentioned quota ("Current Limit (Total VMs): 0"), this region has
no App Service compute quota for your subscription. Fixes:
  1) Find a region that works:   ./deploy/find-region.sh
  2) Delete the half-built resources and re-run in that region:
       az group delete -n "$RESOURCE_GROUP" --yes
       LOCATION=<region> ./deploy/azure-setup.sh
  3) Or request a quota increase (Portal -> Subscription -> Usage + quotas),
     or upgrade a Free Trial to Pay-As-You-Go. See deploy/README.md.
EOF
  exit 1
fi

echo "==> Web App ($WEBAPP_NAME) — placeholder image until first CI deploy"
az webapp create --resource-group "$RESOURCE_GROUP" --plan "$APP_SERVICE_PLAN" \
  --name "$WEBAPP_NAME" --deployment-container-image-name "$PLACEHOLDER_IMAGE" \
  --output none

echo "==> Managed identity + ACR pull"
az webapp identity assign --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --output none
PRINCIPAL_ID="$(az webapp identity show \
  --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --query principalId -o tsv)"
ACR_ID="$(az acr show --name "$ACR_NAME" --query id -o tsv)"
az role assignment create --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull --scope "$ACR_ID" --output none
az webapp config set --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" \
  --generic-configurations '{"acrUseManagedIdentityCreds": true}' --output none

echo "==> Mount Azure Files shares at /music and /data"
az webapp config storage-account add --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" \
  --custom-id music --storage-type AzureFiles --account-name "$STORAGE_ACCOUNT" \
  --share-name music --access-key "$STORAGE_KEY" --mount-path /music --output none
az webapp config storage-account add --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" \
  --custom-id data --storage-type AzureFiles --account-name "$STORAGE_ACCOUNT" \
  --share-name data --access-key "$STORAGE_KEY" --mount-path /data --output none

echo "==> App settings + Always On"
az webapp config appsettings set --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" \
  --settings WEBSITES_PORT=8000 DATA_DIR=/data MUSIC_DIR=/music \
  WEBSITES_ENABLE_APP_SERVICE_STORAGE=false --output none
az webapp config set --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" \
  --always-on true --number-of-workers 1 --output none

cat <<EOF

Done. Set these GitHub Actions *Variables* (Settings -> Secrets and variables -> Actions):
  ACR_NAME             = $ACR_NAME
  AZURE_RESOURCE_GROUP = $RESOURCE_GROUP
  AZURE_WEBAPP_NAME    = $WEBAPP_NAME

Next:
  1) deploy/github-oidc-setup.sh   (create the OIDC identity + repo secrets)
  2) push to main / run the "Deploy to Azure" workflow to build + ship the image
  3) upload music to the 'music' share, then click Rescan in the app
  4) deploy/easy-auth-setup.sh     (lock the app behind Entra ID)

App URL: https://$WEBAPP_NAME.azurewebsites.net
EOF
