#!/usr/bin/env bash
#
# One-shot setup + deploy for the ADO companion on Databricks.
#
# It will:
#   1. check prerequisites (databricks CLI, python3, node, npm)
#   2. verify (or start) Databricks auth
#   3. create the `ado` secret scope and store your ADO PAT
#   4. write your ADO org URL into src/app.yaml
#   5. build the React frontend
#   6. deploy + run the Databricks App, then print its URL
#
# Usage (values can be passed as env vars or you'll be prompted):
#   DBX_HOST=https://<workspace>.cloud.databricks.com \
#   ADO_ORG_URL=https://dev.azure.com/<org> \
#   ADO_PAT=<token> \
#   TARGET=dev \
#   ./scripts/setup.sh
#
set -euo pipefail

TARGET="${TARGET:-dev}"
SCOPE="ado"
KEY="ado_pat"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

say()  { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
die()  { printf "\n\033[1;31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing prerequisite: $1"; }

# 1. Prerequisites ------------------------------------------------------------
say "Checking prerequisites"
need databricks; need python3; need node; need npm
echo "databricks: $(databricks version 2>/dev/null || echo '?')"
echo "node: $(node --version)   npm: $(npm --version)"

# 2. Auth ---------------------------------------------------------------------
say "Verifying Databricks auth"
if ! databricks current-user me >/dev/null 2>&1; then
  : "${DBX_HOST:?Set DBX_HOST=https://<workspace>... or run 'databricks auth login' first}"
  databricks auth login --host "$DBX_HOST"
fi
WHO="$(databricks current-user me --output json | python3 -c 'import sys,json;print(json.load(sys.stdin).get("userName","?"))')"
echo "Authenticated as: $WHO"

# 3. Secret -------------------------------------------------------------------
say "Storing ADO PAT in secret scope '$SCOPE'"
if [ -z "${ADO_PAT:-}" ]; then read -r -s -p "Azure DevOps PAT: " ADO_PAT; echo; fi
[ -n "$ADO_PAT" ] || die "ADO_PAT is empty"
databricks secrets create-scope "$SCOPE" 2>/dev/null || echo "scope '$SCOPE' already exists, reusing"
databricks secrets put-secret "$SCOPE" "$KEY" --string-value "$ADO_PAT"
echo "secret $SCOPE/$KEY set"

# 4. Org URL into app.yaml ----------------------------------------------------
say "Setting ADO org URL in src/app.yaml"
if [ -z "${ADO_ORG_URL:-}" ]; then read -r -p "Azure DevOps org URL (https://dev.azure.com/<org>): " ADO_ORG_URL; fi
[ -n "$ADO_ORG_URL" ] || die "ADO_ORG_URL is empty"
python3 - "$ADO_ORG_URL" <<'PY'
import re, sys
url = sys.argv[1]
p = "src/app.yaml"
s = open(p).read()
# replace the value: line that follows `name: ADO_ORG_URL`
s = re.sub(r'(- name: ADO_ORG_URL\n\s*value: )"[^"]*"', r'\1"%s"' % url, s)
open(p, "w").write(s)
print("app.yaml ADO_ORG_URL ->", url)
PY

# 5. Build frontend -----------------------------------------------------------
say "Building React frontend -> src/static"
( cd frontend && npm ci && npm run build )

# 6. Deploy + run -------------------------------------------------------------
say "Deploying bundle (target: $TARGET)"
databricks bundle deploy -t "$TARGET"
say "Starting the app"
databricks bundle run ado_app -t "$TARGET" || true

say "Done. App status:"
databricks apps get ado-companion --output json 2>/dev/null \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("URL:",d.get("url","?"));print("state:",d.get("compute_status",{}).get("state") or d.get("app_status",{}).get("state","?"))' \
  || echo "Run 'databricks apps get ado-companion' to see the URL."
