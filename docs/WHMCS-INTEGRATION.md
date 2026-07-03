# WHMCS Integration — selling ServerAlly through FireVPS

> **Status: SHIPPED (2026-07-03).** This is "Brick 3" of the metering plan
> ([AI-METERING.md](AI-METERING.md) §9) implemented for WHMCS instead of Stripe:
> WHMCS owns customers, invoices, renewals and payment collection (Payssion or any
> gateway), and drives ServerAlly plans through a small provisioning module. Works
> for the hosted SaaS today and for self-hosted license products later.

---

## 1. The moving parts

```
Customer ──orders/pays (Payssion via WHMCS)──▶ WHMCS
WHMCS ──provisioning module (billing events)──▶ ServerAlly entitlement API
ServerAlly ──users.plan flips──▶ the two meters (PRICING v2) apply
```

- **ServerAlly side:** `POST /api/admin/entitlements/set` (+ `GET …/{email}` for status,
  `GET …/ping` for the connection test). Protected by the `X-Entitlement-Key` header —
  the shared secret in `ENTITLEMENT_API_KEY` (empty = API disabled). Every change is
  audit-logged. Plans only ever move between `free` and `pro`; **nothing is deleted.**
- **WHMCS side:** the module in [`whmcs/serverally/`](../whmcs/serverally/serverally.php).

Event mapping (all idempotent):

| WHMCS event | ServerAlly plan |
|---|---|
| CreateAccount (order paid) | the product's configured plan (`pro`) |
| SuspendAccount (overdue) | `free` |
| UnsuspendAccount (paid late) | `pro` |
| TerminateAccount (cancelled) | `free` — account, servers and data remain |
| ChangePackage | the new product's plan |

## 2. Setup — ServerAlly deployment

1. In `backend/.env`:
   ```
   ENTITLEMENT_API_KEY=<long random secret>   # python -c "import secrets; print(secrets.token_hex(32))"
   APP_BASE_URL=https://app.yourdomain.com    # used to build claim links
   ```
2. (Optional, recommended) In the frontend build env:
   ```
   VITE_UPGRADE_URL=https://firevps.example/order/serverally-pro
   ```
   The in-app "Upgrade to Pro" button then opens your WHMCS order page.

## 3. Setup — WHMCS

1. Copy `whmcs/serverally/` → `<whmcs>/modules/servers/serverally/`.
2. Create a product **ServerAlly Pro** (product type: *Other*), Module Settings →
   Module: **ServerAlly**; fill **API URL**, **API Key**, **Plan = pro**. Use the
   *Test Connection* button.
3. Pricing: monthly/annual as desired. Payments: any gateway you already run
   (Payssion included — the module never touches payments; WHMCS does).
4. Welcome email (recommended): add to the product's welcome template —
   *"Open ServerAlly: {API URL}. First time? Set your password: check the *Set your
   password* button on your service page."* (The one-time claim link is stored on the
   service and shown in the client area; it is also visible in the Module Log.)

## 4. The two customer journeys

- **FireVPS-first:** customer orders in WHMCS → pays → module provisions the
  ServerAlly account (verified email, random password) → customer clicks the one-time
  **claim link** → sets a password → signed in as Pro. Claim links expire in 7 days
  and die on first use (token_version bump) — a leaked link can't reset a password
  later.
- **App-first:** user signs up Free in ServerAlly → clicks Upgrade → lands on the
  WHMCS order page → pays with the SAME email → module flips the existing account to
  Pro (no new account, `created:false`).

## 5. Security notes

- The entitlement API does exactly one thing: move `users.plan` between two values.
  It cannot read credentials, run commands, or delete anything.
- Shared-secret comparison is constant-time; the key never appears in logs (module
  masks it in the WHMCS Module Log).
- Suspend/terminate NEVER remove data — pricing v2's free plan keeps every feature,
  only the meters shrink.

## 6. Later (not built)

- SSO from the WHMCS client area ("Open ServerAlly" auto-login).
- Top-up action packs as WHMCS addons.
- Self-hosted license keys + gateway AI subscriptions sold as WHMCS products
  (the entitlement design already fits: a license encodes plan + max_servers).
