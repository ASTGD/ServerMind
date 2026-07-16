# Phase 1 — proving the WHMCS money path

> **Status: READY TO RUN (2026-07-16).** Phase 1 of
> [SAAS-LAUNCH-PLAN.md](SAAS-LAUNCH-PLAN.md) §9.
>
> The WHMCS module (`whmcs/serverally/serverally.php`) is **fully built and has never
> run once.** It is the money path: pricing, the upgrade walls, the marketing order
> button and every customer's plan all depend on it behaving the way we assume. This
> doc proves it — or finds out now, rather than after the marketing page is live.
>
> **Two bugs are already known from reading the code (§5).** Confirm them; do not be
> surprised by them.

---

## 1. What you need

- A **staging** WHMCS (never production — this creates orders and accounts).
- A **staging** ServerAlly with `ENTITLEMENT_API_KEY` and `APP_BASE_URL` set in
  `backend/.env`. If `ENTITLEMENT_API_KEY` is empty the whole entitlement API returns
  503 and nothing below works.
- Two throwaway email addresses you can receive mail at.
- ~45 minutes.

**Test in this order.** Part A proves ServerAlly's side alone. If it passes, any later
failure is on the WHMCS side — and knowing which side broke saves most of the debugging.

---

## 2. Part A — the API smoke test *(5 minutes, automated)*

```bash
API_URL=https://staging.example.com \
ENTITLEMENT_KEY=<the ENTITLEMENT_API_KEY value> \
./whmcs/test-entitlements.sh
```

It makes exactly the calls the PHP module makes: auth, validation, provisioning, the
claim link, idempotency, the full suspend → unsuspend → terminate cycle, and the
client-area status figures. It asks you to type `staging` first, because it writes.

**Expected: 26 passed, 0 failed, 1 known issue** (the known issue is BUG-W1's enabler —
see §5.1; it is *supposed* to warn).

If it says `Cannot reach` → wrong URL, app down, or a firewall.
If it says `ENTITLEMENT_API_KEY is empty` → set it and restart the backend.

Two accounts are left behind (`phase1-test-*@serverally-test.invalid`). There is no
delete endpoint — by design, nothing is ever deleted. Remove them from the staging DB
by hand if you want a clean slate.

---

## 3. Part B — the WHMCS lifecycle *(manual — only you can run this)*

### Setup

1. Copy `whmcs/serverally/` → `<whmcs>/modules/servers/serverally/`
   (copy the **folder**, not `test-entitlements.sh` — that stays in this repo).
2. **Setup → Products/Services → Create a New Product**
   - Type: **Other**, Name: **ServerAlly Pro**
   - **Module Settings → Module: ServerAlly**
   - **API URL**: your staging ServerAlly base URL, no trailing slash
   - **API Key**: the `ENTITLEMENT_API_KEY` value
   - **Plan**: `pro`
3. Set a monthly price.

Keep **Utilities → Logs → Module Log** open in another tab for every test below. It is
the only place you can see what the module actually sent and received.

### The tests

| # | Test | Do this | Expect |
|---|---|---|---|
| **T1** | Connection | Module Settings → **Test Connection** | Green success |
| **T2** | Bad key | Change API Key to junk → Test Connection → **change it back** | A clear `ServerAlly: Bad entitlement key` — not a blank or a PHP error |
| **T3** | CreateAccount | Order the product for a **new** email → mark the invoice **Paid** | Module Log: `POST /set` → `created: true` + a `claim_url`. ServerAlly has the account on **pro** |
| **T4** | Claim | Open the service in the **client area** → click **Set your password** | The ServerAlly `/claim` page opens → set a password → signed in as **Pro** |
| **T5** | Client area | Reload the service page | Plan **Pro**, Ally actions `0 / 1000`, Servers `0 / 15` |
| **T6** | Suspend | Admin → the service → **Suspend** | Plan → **free**. Client area shows `0 / 30` and `0 / 2` |
| **T7** | Unsuspend | **Unsuspend** | Plan → **pro**, limits back to `1000` / `15` |
| **T8** | Terminate | **Terminate** | Plan → **free** — and **log into ServerAlly: every server, mission and file is still there.** Nothing may be deleted |
| **T9** | ChangePackage | Make a second product (Plan `free`) → **Upgrade/Downgrade** the service to it | Plan follows the **new** product |
| **T10** | App-first | Sign up in ServerAlly as Free with a *second* email → order the product with the **same** email → mark Paid | `created: false`, **no** second account, plan → pro, their existing servers untouched |
| **T11** | **Renewal** | Let a renewal invoice generate → mark it **Paid** | **The Module Log stays EMPTY.** Nothing is called — see §4 |
| **T12** | App down | Stop staging ServerAlly → order the product → mark Paid → **start it again** | WHMCS shows a module error and the customer is **not** Pro. **Note who would notice this in production** — see §4 |

---

## 4. The two things T11 and T12 are really testing

**T11 — renewal is silence.** There is no `Renew` hook. A paying customer's renewal calls
nothing, because nothing needs to change: they were Pro, they stay Pro. An empty Module
Log is the **correct** result.

**T12 — but that means the system fails OPEN.** If an event never reaches us (module
error, our API down, a stopped WHMCS cron), the customer's plan silently stays wherever
it was, and **nothing tells us.** Silence means both "all fine" (T11) and "broken" (T12) —
we cannot tell them apart.

T12 shows this in the safest direction (a paying customer doesn't get Pro — they will
complain within a day). The dangerous direction is the mirror image: **a missed suspend
leaves a non-paying customer on Pro forever, and nobody ever complains.**

This is why **Phase 2 is the reconciliation cron**, not the admin area. A nightly WHMCS
job re-asserting every active service's plan makes drift self-heal within 24 hours —
and because `/set` is already idempotent, the upgrade direction needs **zero new
ServerAlly code**. Record T12's behaviour carefully; it is Phase 2's requirement.

---

## 5. Known bugs — confirm, don't be surprised

Both were found by reading the module. Neither is fixed. Confirm each, then fix in
Phase 2.

### 5.1 BUG-W1 — a WHMCS email change orphans the paying account *(High)*

`serverally_setPlan` reads the email **fresh from the WHMCS client record on every
event** (`$params['clientsdetails']['email']`). But the email is the join key between
the two systems, and WHMCS lets a client change it at any time.

**Confirm it:**
1. Order for `a@example.com` → ServerAlly `a@example.com` is **pro**.
2. In WHMCS, change that client's email to `b@example.com`.
3. **Suspend** the service.
4. Look at ServerAlly: `b@example.com` was **created as a brand-new free account**, and
   **`a@example.com` is still pro.**

**Why it matters:** the suspend lands on the wrong account. The real customer keeps Pro
without paying, a junk account appears, and a stale claim link gets written onto the
service. The same change before an upgrade is worse — the customer gets a fresh empty
account while all their servers sit on the old one.

The enabler is that `/set` **provisions on any event, including a suspend** — Part A §7
checks exactly this.

**Fix directions (Phase 2):** store the ServerAlly identity on the service at
CreateAccount and key on that rather than the live email; and/or a WHMCS hook on email
change that tells ServerAlly to rename; and/or stop `/set` provisioning when the plan is
`free` (a suspend should never create an account). The nightly reconciliation of §4 also
heals the revenue-leak half of this on its own.

### 5.2 BUG-W2 — "Set your password" never goes away *(Low)*

The claim link is stored in `tblhosting.username`, and `serverally_ClientArea` shows the
button whenever that field contains `/claim?token=`. **Nothing ever clears it.** The token
dies on first use and expires after 7 days, so a customer who already set their password
still sees a **Set your password** button that leads to a dead link.

**Confirm it:** after T4, reload the client-area service page — the button is still there;
click it and you get an invalid/expired token.

**Fix direction:** clear the field after a successful claim, or have `ClientArea` hide the
button once the account is claimed (the status endpoint could report it).

### 5.3 Note — claim links are written to the WHMCS Module Log *(Low)*

`logModuleCall` masks the API key but logs the raw response, which contains `claim_url`
for a new account. Anyone with WHMCS admin log access can read an **unclaimed** link and
set the password before the customer does. Bounded by: admin-only access, 7-day expiry,
and the link dying on first use. Accept it knowingly, or stop logging the response body
on `/set`.

---

## 6. Exit criteria

Phase 1 is done when:

- [ ] Part A: **26 passed, 0 failed**.
- [ ] T1–T11 pass as described.
- [ ] **T8 verified by hand** — after terminate, the customer's servers and data are all
      still there. This is the promise pricing v2 makes; it must be true.
- [ ] T12's behaviour is recorded (it feeds Phase 2's requirement).
- [ ] BUG-W1 and BUG-W2 confirmed and their real-world severity judged.
- [ ] The Pro price and action allowance are settled
      ([PRICING-FREE-VS-PRO.md](PRICING-FREE-VS-PRO.md) §11).

Then Phase 2: the reconciliation cron + `POST /api/admin/entitlements/reconcile`, plus
the BUG-W1 fix. **Do not flip `ENFORCE_PLAN_LIMITS` until Phase 1 passes** — arming the
walls on top of an unproven plan path means locking out real customers.
