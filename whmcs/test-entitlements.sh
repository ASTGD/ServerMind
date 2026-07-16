#!/usr/bin/env bash
#
# Phase 1, Part A — ServerAlly entitlement API smoke test.
#
# Proves the ServerAlly SIDE of the WHMCS integration works, before you touch WHMCS.
# Every call here is exactly what whmcs/serverally/serverally.php makes, so if this
# passes, any later failure is on the WHMCS side — which is worth knowing up front.
#
# Usage:
#   API_URL=https://staging.example.com ENTITLEMENT_KEY=xxx ./whmcs/test-entitlements.sh
#
# ⚠️  THIS SCRIPT WRITES. It creates test accounts and changes their plans. Run it
#     against STAGING only. It refuses to run without an explicit confirmation.
#
# See docs/WHMCS-PHASE1-TEST.md for the full runbook (Part B = the WHMCS lifecycle).

set -uo pipefail

URL="${API_URL:-}"
KEY="${ENTITLEMENT_KEY:-}"
STAMP="$(date +%s)"
EMAIL="phase1-test-${STAMP}@example.com"
EMAIL2="phase1-test-${STAMP}-renamed@example.com"

if [[ -z "$URL" || -z "$KEY" ]]; then
  echo "Usage: API_URL=https://staging.example.com ENTITLEMENT_KEY=xxx $0" >&2
  exit 2
fi
URL="${URL%/}"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
PASS=0; FAIL=0; WARN=0
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

echo
echo "  ServerAlly entitlement API — Phase 1 smoke test"
echo "  Target : $URL"
echo "  Test as: $EMAIL"
echo
echo "  ${YELLOW}This creates accounts and changes plans on the target.${OFF}"
read -rp "  Type 'staging' to confirm this is NOT production: " ok
[[ "$ok" == "staging" ]] || { echo "  Aborted."; exit 1; }
echo

# req METHOD PATH [JSON_BODY] [KEY_OVERRIDE] -> sets STATUS, BODY
# NOTE: ${4-$KEY} (no colon) on purpose — it substitutes only when the arg is UNSET.
# With ${4:-$KEY} an explicitly-empty key would fall back to the real one, and the
# "missing key is rejected" check below would silently pass while testing nothing.
req() {
  local method=$1 path=$2 body=${3:-} key=${4-$KEY}
  local args=(-s -o "$TMP/body" -w '%{http_code}' --max-time 20 -X "$method"
              -H "X-Entitlement-Key: $key" -H 'Content-Type: application/json'
              -H 'Accept: application/json')
  [[ -n "$body" ]] && args+=(-d "$body")
  # curl already prints 000 on a connection failure — do NOT add another via `|| echo`,
  # or the status reads "000000" and the check output becomes nonsense.
  STATUS="$(curl "${args[@]}" "$URL$path" 2>/dev/null || true)"
  STATUS="${STATUS:-000}"
  BODY="$(cat "$TMP/body" 2>/dev/null || true)"
}

# field NAME -> the JSON value as text ('' if absent). python3 avoids a jq dependency.
field() {
  python3 -c "
import json,sys
try: v = json.loads(sys.stdin.read()).get('$1','')
except Exception: v = ''
print('' if v is None else v)
" <<< "$BODY" 2>/dev/null
}

check() { # check "label" "expected" "actual"
  if [[ "$2" == "$3" ]]; then
    printf '  %s✓%s %s\n' "$GREEN" "$OFF" "$1"; ((PASS++))
  else
    printf '  %s✗%s %s\n      expected: %s\n      actual  : %s\n' "$RED" "$OFF" "$1" "$2" "$3"; ((FAIL++))
  fi
}
warn() { printf '  %s!%s %s\n' "$YELLOW" "$OFF" "$1"; ((WARN++)); }
note() { printf '     %s%s%s\n' "$DIM" "$1" "$OFF"; }

section() { printf '\n  %s\n' "$1"; }

# ── 0. Reachability ──────────────────────────────────────────────────────────
# Fail fast and clearly: an unreachable target would otherwise surface as a wall of
# confusing assertion failures instead of "the URL is wrong / the app is down".
req GET /api/admin/entitlements/ping
if [[ "$STATUS" == "000" ]]; then
  echo "  ${RED}Cannot reach $URL${OFF}"
  echo "  Nothing is listening, DNS failed, or TLS was rejected. Check API_URL,"
  echo "  that the app is running, and that this machine can reach it."
  exit 1
fi

# ── 1. Auth ──────────────────────────────────────────────────────────────────
section "1. Authentication"

req GET /api/admin/entitlements/ping "" "wrong-key-$STAMP"
if [[ "$STATUS" == "503" ]]; then
  echo
  echo "  ${RED}ENTITLEMENT_API_KEY is empty on the target — the whole API is disabled.${OFF}"
  echo "  Set it in backend/.env and restart, then re-run."
  exit 1
fi
check "a wrong key is rejected (401)" "401" "$STATUS"

req GET /api/admin/entitlements/ping "" ""
check "a missing key is rejected (401)" "401" "$STATUS"

req GET /api/admin/entitlements/ping
check "the real key is accepted (200)" "200" "$STATUS"
check "ping reports ok" "True" "$(field ok)"

# ── 2. Validation ────────────────────────────────────────────────────────────
section "2. Input validation"

req POST /api/admin/entitlements/set "{\"email\":\"$EMAIL\",\"plan\":\"enterprise\"}"
check "an unknown plan is refused (422)" "422" "$STATUS"
note "a typo in the WHMCS product's Plan field must never silently create a plan"

req POST /api/admin/entitlements/set '{"email":"not-an-email","plan":"pro"}'
check "a malformed email is refused (422)" "422" "$STATUS"

# ── 3. Provisioning (WHMCS CreateAccount) ────────────────────────────────────
section "3. CreateAccount — a new customer orders Pro"

req POST /api/admin/entitlements/set "{\"email\":\"$EMAIL\",\"plan\":\"pro\",\"reference\":\"whmcs-service-9999\"}"
check "provisions the account (200)" "200" "$STATUS"
check "reports it created the account" "True" "$(field created)"
check "sets the plan to pro" "pro" "$(field plan)"
CLAIM="$(field claim_url)"
if [[ "$CLAIM" == *"/claim?token="* ]]; then
  printf '  %s✓%s returns a claim link\n' "$GREEN" "$OFF"; ((PASS++))
  if [[ "$CLAIM" != http* ]]; then
    warn "the claim link is relative ('$CLAIM')"
    note "APP_BASE_URL is unset on the target — the link in the WHMCS client area will be broken"
  fi
else
  check "returns a claim link" "a /claim?token=... URL" "${CLAIM:-<none>}"
fi

# ── 4. Idempotency ───────────────────────────────────────────────────────────
section "4. Idempotency — WHMCS may retry any event"

req POST /api/admin/entitlements/set "{\"email\":\"$EMAIL\",\"plan\":\"pro\"}"
check "a repeat call still succeeds (200)" "200" "$STATUS"
check "does NOT re-create the account" "False" "$(field created)"
check "returns no second claim link" "" "$(field claim_url)"
note "a second claim link would silently invalidate the first one the customer was emailed"

# ── 5. Status (what the WHMCS client area shows) ──────────────────────────────
section "5. Status — the client-area figures"

req GET "/api/admin/entitlements/$EMAIL"
check "returns the customer's status (200)" "200" "$STATUS"
check "plan is pro" "pro" "$(field plan)"
check "pro action limit" "1000" "$(field actions_limit)"
check "pro server limit" "15" "$(field servers_limit)"

req GET "/api/admin/entitlements/nobody-${STAMP}@example.com"
check "an unknown email is a clean 404" "404" "$STATUS"

# ── 6. The renewal lifecycle ─────────────────────────────────────────────────
section "6. The lifecycle — suspend, unsuspend, terminate"

req POST /api/admin/entitlements/set "{\"email\":\"$EMAIL\",\"plan\":\"free\"}"
check "SuspendAccount → free (200)" "200" "$STATUS"
req GET "/api/admin/entitlements/$EMAIL"
check "  plan is now free" "free" "$(field plan)"
check "  free action limit" "30" "$(field actions_limit)"
check "  free server limit" "2" "$(field servers_limit)"

req POST /api/admin/entitlements/set "{\"email\":\"$EMAIL\",\"plan\":\"pro\"}"
check "UnsuspendAccount → pro (200)" "200" "$STATUS"
req GET "/api/admin/entitlements/$EMAIL"
check "  plan is pro again" "pro" "$(field plan)"

req POST /api/admin/entitlements/set "{\"email\":\"$EMAIL\",\"plan\":\"free\"}"
check "TerminateAccount → free (200)" "200" "$STATUS"
req POST /api/admin/entitlements/set "{\"email\":\"$EMAIL\",\"plan\":\"free\"}"
check "a repeat terminate is harmless (200)" "200" "$STATUS"

# ── 7. Known bug: a suspend for an unknown email creates an account ───────────
section "7. Known bug — BUG-W1's enabler (see docs/WHMCS-PHASE1-TEST.md §5)"

req POST /api/admin/entitlements/set "{\"email\":\"$EMAIL2\",\"plan\":\"free\"}"
if [[ "$(field created)" == "True" ]]; then
  warn "a 'free' set for an unknown email PROVISIONED a new account"
  note "this is what lets a WHMCS email change orphan the paying account (BUG-W1):"
  note "the suspend lands on the NEW email — creating junk — while the OLD account stays Pro"
  note "expected today; the fix is Phase 2. Confirming it is the point of this check."
else
  printf '  %s✓%s a free set for an unknown email no longer provisions (BUG-W1 enabler fixed)\n' "$GREEN" "$OFF"; ((PASS++))
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo
printf '  %s%d passed%s' "$GREEN" "$PASS" "$OFF"
[[ $FAIL -gt 0 ]] && printf ', %s%d failed%s' "$RED" "$FAIL" "$OFF"
[[ $WARN -gt 0 ]] && printf ', %s%d known issue(s)%s' "$YELLOW" "$WARN" "$OFF"
echo; echo
echo "  ${DIM}Test accounts left behind (there is no delete endpoint — by design):${OFF}"
echo "  ${DIM}  $EMAIL${OFF}"
echo "  ${DIM}  $EMAIL2${OFF}"
echo "  ${DIM}Remove them from the staging DB if you want a clean slate.${OFF}"
echo
[[ $FAIL -eq 0 ]] || exit 1
echo "  ServerAlly's side is good. Now run Part B — docs/WHMCS-PHASE1-TEST.md §3."
echo
