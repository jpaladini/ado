#!/usr/bin/env bash
#
# One-shot setup + deploy for the ADO companion on Databricks.
#
# It will:
#   1. check prerequisites (databricks CLI, python3, node, npm)
#   2. verify (or start) Databricks auth
#   3. store the ADO org URL + PAT in the per-workspace `ado` secret scope
#   4. build the React frontend
#   5. deploy + run the Databricks App, then print its URL
#
# All environment-specific config is per-workspace secrets — run this once per
# workspace (dev / stg / prod), selecting the target + CLI profile.
#
# Usage (values can be passed as env vars or you'll be prompted):
#   TARGET=dev PROFILE=dev \
#   ADO_ORG_URL=https://dev.azure.com/<org> \
#   ADO_PAT=<token> \
#   ./scripts/setup.sh
#
set -euo pipefail

TARGET="${TARGET:-dev}"
PROFILE="${PROFILE:-$TARGET}"   # CLI auth profile; defaults to the target name
SCOPE="ado"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Pass -p only if a profile is configured; otherwise use the default auth.
PROFILE_ARG=()
if databricks auth profiles 2>/dev/null | awk '{print $1}' | grep -qx "$PROFILE"; then
  PROFILE_ARG=(-p "$PROFILE")
fi

say()  { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
die()  { printf "\n\033[1;31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing prerequisite: $1"; }

# 1. Prerequisites ------------------------------------------------------------
say "Checking prerequisites"
need databricks; need python3; need node; need npm
echo "target=$TARGET  profile=$PROFILE"

# 2. Auth ---------------------------------------------------------------------
say "Verifying Databricks auth"
if ! databricks current-user me "${PROFILE_ARG[@]}" >/dev/null 2>&1; then
  : "${DBX_HOST:?Set DBX_HOST=https://<workspace>... or run 'databricks auth login' first}"
  databricks auth login --host "$DBX_HOST" --profile "$PROFILE"
  PROFILE_ARG=(-p "$PROFILE")
fi
WHO="$(databricks current-user me "${PROFILE_ARG[@]}" --output json | python3 -c 'import sys,json;print(json.load(sys.stdin).get("userName","?"))')"
echo "Authenticated as: $WHO"

# 3. Secrets (org URL + PAT) --------------------------------------------------
say "Storing config in secret scope '$SCOPE' (workspace: $PROFILE)"
if [ -z "${ADO_ORG_URL:-}" ]; then read -r -p "Azure DevOps org URL (https://dev.azure.com/<org>): " ADO_ORG_URL; fi
[ -n "$ADO_ORG_URL" ] || die "ADO_ORG_URL is empty"
if [ -z "${ADO_PAT:-}" ]; then read -r -s -p "Azure DevOps PAT: " ADO_PAT; echo; fi
[ -n "$ADO_PAT" ] || die "ADO_PAT is empty"
databricks secrets create-scope "$SCOPE" "${PROFILE_ARG[@]}" 2>/dev/null || echo "scope '$SCOPE' already exists, reusing"
databricks secrets put-secret "$SCOPE" ado_org_url --string-value "$ADO_ORG_URL" "${PROFILE_ARG[@]}"
databricks secrets put-secret "$SCOPE" ado_pat     --string-value "$ADO_PAT"     "${PROFILE_ARG[@]}"
echo "secrets $SCOPE/ado_org_url and $SCOPE/ado_pat set"

# 4. Build frontend -----------------------------------------------------------
say "Building React frontend -> src/static"
( cd frontend && npm ci && npm run build )

# 5. Deploy + run -------------------------------------------------------------
say "Deploying bundle (target: $TARGET)"
databricks bundle deploy -t "$TARGET" "${PROFILE_ARG[@]}"
say "Starting the app"
databricks bundle run ado_app -t "$TARGET" "${PROFILE_ARG[@]}" || true

say "Done. App status:"
databricks apps get ado-companion "${PROFILE_ARG[@]}" --output json 2>/dev/null \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("URL:",d.get("url","?"));print("state:",d.get("compute_status",{}).get("state") or d.get("app_status",{}).get("state","?"))' \
  || echo "Run 'databricks apps get ado-companion ${PROFILE_ARG[*]}' to see the URL."
