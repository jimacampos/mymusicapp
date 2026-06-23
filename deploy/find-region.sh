#!/usr/bin/env bash
#
# Find an Azure region where your subscription can create a B1 (dedicated)
# App Service plan. Useful when azure-setup.sh fails with:
#   "Operation cannot be completed without additional quota ... Total VMs: 0"
# Quota is per-region, so another region often works.
#
# It probes by briefly creating + deleting a B1 plan in a throwaway resource
# group (a few cents at most). Requires `az login`.
#
# Usage:
#   ./deploy/find-region.sh                 # tests a default region list
#   ./deploy/find-region.sh westus2 westeurope centralindia   # custom list
set -euo pipefail

if [ "$#" -gt 0 ]; then
  REGIONS=("$@")
else
  REGIONS=(eastus eastus2 westus2 westus3 centralus southcentralus \
           westeurope northeurope uksouth)
fi

SKU="${SKU:-B1}"
PROBE_RG="whitefieldslistens-quota-probe-rg"
PROBE_PLAN="quota-probe-plan"

cleanup() { az group delete -n "$PROBE_RG" --yes --no-wait >/dev/null 2>&1 || true; }
trap cleanup EXIT

az group create -n "$PROBE_RG" -l "${REGIONS[0]}" --output none

FOUND=""
for r in "${REGIONS[@]}"; do
  printf 'Testing %-16s ... ' "$r"
  if az appservice plan create -g "$PROBE_RG" -n "$PROBE_PLAN" \
       --is-linux --sku "$SKU" --location "$r" --output none 2>/dev/null; then
    echo "OK — quota available"
    az appservice plan delete -g "$PROBE_RG" -n "$PROBE_PLAN" --yes --output none 2>/dev/null || true
    FOUND="$r"
    break
  else
    echo "no quota"
  fi
done

echo
if [ -n "$FOUND" ]; then
  cat <<EOF
Use region '$FOUND'. If you already started provisioning in another region,
delete those resources first, then provision there:

    az group delete -n whitefieldslistens-rg --yes
    LOCATION=$FOUND ./deploy/azure-setup.sh
EOF
else
  cat <<EOF
None of the tested regions had B1 quota. Your subscription is likely
quota-capped for dedicated App Service compute (common on Free Trial / Student).
Options:
  - Request a quota increase: Portal -> Subscription -> Usage + quotas -> Microsoft.Web
  - Upgrade a Free Trial to Pay-As-You-Go
  - Deploy to Azure Container Apps instead (different quota model; ask to switch)
Try more regions: ./deploy/find-region.sh <region1> <region2> ...
EOF
fi
