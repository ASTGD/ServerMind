"""MCP OAuth consent + login page (docs/MCP-SERVER-PLAN.md §5.3).

The SDK's /authorize handler redirects the browser here with a signed transaction. The
user signs in with their ServerAlly credentials and approves; we mint an authorization
code bound to that user and redirect back to the client. Denials redirect back with
``error=access_denied``.

Because there is no ambient browser session (ServerAlly auth is bearer-JWT, not cookies),
the user proves who they are by signing in on this page — which also makes the approval
inherently CSRF-safe (no ambient credential to ride on). The signed, short-lived txn
carries the request, so nothing is stored between /authorize and approval.
"""
from __future__ import annotations

import html
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.mcp.oauth_provider import ALL_SCOPES, DEFAULT_SCOPES, mcp_enabled_for, oauth_provider, verify_txn
from app.models.user import User
from app.services import audit_service, auth_service, totp_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["mcp-oauth"])

# A constant hash so an unknown email costs the same time as a known one.
_DUMMY_HASH = auth_service.hash_password("mcp-oauth-timing-guard")

_INVALID_LINK = "This authorization request is invalid or has expired. Please start again from your AI client."


def _redirect_back(data: dict, params: dict) -> RedirectResponse:
    """302 back to the client's redirect_uri with the given query params (+ state)."""
    if data.get("state") is not None:
        params = {**params, "state": data["state"]}
    redirect_uri = data["redirect_uri"]
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)


def _page(*, client_name: str, txn: str, error: str = "", email: str = "", need_totp: bool = False) -> str:
    """Render the login + consent page. All interpolated values are HTML-escaped —
    ``client_name`` in particular is attacker-controlled (from DCR)."""
    cn = html.escape(client_name or "An application")
    err_html = (
        f'<div class="err">{html.escape(error)}</div>' if error else ""
    )
    totp_html = f"""
        <label>Two-factor code {'' if need_totp else '<span class="opt">(if enabled)</span>'}
          <input name="totp_code" inputmode="numeric" autocomplete="one-time-code"
                 placeholder="123456" {'autofocus' if need_totp else ''} />
        </label>""" if True else ""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect to ServerAlly</title>
<style>
  :root {{ color-scheme: light dark; --bg:#f6f7fb; --card:#fff; --fg:#0f172a; --muted:#64748b;
           --border:#e2e8f0; --brand1:#6366f1; --brand2:#8b5cf6; --err:#dc2626; --field:#fff; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0b1120; --card:#111827; --fg:#e5e7eb; --muted:#94a3b8; --border:#1f2937;
             --err:#f87171; --field:#0b1120; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; padding:24px; }}
  .card {{ width:100%; max-width:420px; background:var(--card); border:1px solid var(--border);
          border-radius:16px; padding:28px; box-shadow:0 10px 40px rgba(2,6,23,.12); }}
  .brand {{ display:flex; align-items:center; gap:9px; font-weight:700; font-size:15px; margin-bottom:20px; }}
  .dot {{ width:22px; height:22px; border-radius:7px; background:linear-gradient(135deg,var(--brand1),var(--brand2)); }}
  h1 {{ font-size:19px; margin:0 0 6px; line-height:1.3; }}
  .sub {{ color:var(--muted); margin:0 0 18px; font-size:14px; }}
  .perm {{ background:color-mix(in srgb, var(--brand1) 7%, transparent); border:1px solid var(--border);
           border-radius:12px; padding:14px 16px; margin:0 0 20px; font-size:13.5px; }}
  .perm ul {{ margin:8px 0 0; padding-left:18px; color:var(--muted); }}
  .perm li {{ margin:3px 0; }}
  .perm .safe {{ color:var(--fg); font-weight:600; }}
  .level {{ margin:0 0 18px; display:flex; flex-direction:column; gap:8px; }}
  .lvl {{ display:flex; gap:9px; align-items:flex-start; font-size:13px; font-weight:400; margin:0; cursor:pointer; }}
  .lvl input {{ width:auto; margin-top:3px; }}
  .lvl em {{ color:var(--muted); font-style:normal; }}
  label {{ display:block; font-size:13px; font-weight:600; margin:0 0 14px; }}
  .opt {{ color:var(--muted); font-weight:400; }}
  input {{ width:100%; margin-top:6px; padding:10px 12px; font-size:14px; border:1px solid var(--border);
          border-radius:9px; background:var(--field); color:var(--fg); }}
  input:focus {{ outline:2px solid var(--brand1); outline-offset:0; border-color:transparent; }}
  .row {{ display:flex; gap:10px; margin-top:22px; }}
  button {{ flex:1; padding:11px 14px; font-size:14px; font-weight:600; border-radius:10px; cursor:pointer; border:1px solid transparent; }}
  .approve {{ color:#fff; background:linear-gradient(135deg,var(--brand1),var(--brand2)); }}
  .approve:hover {{ opacity:.94; }}
  .deny {{ background:transparent; border-color:var(--border); color:var(--muted); }}
  .deny:hover {{ color:var(--fg); }}
  .err {{ background:color-mix(in srgb, var(--err) 12%, transparent); color:var(--err);
          border:1px solid color-mix(in srgb, var(--err) 30%, transparent);
          border-radius:9px; padding:9px 12px; font-size:13px; margin:0 0 16px; }}
  .foot {{ margin-top:16px; font-size:12px; color:var(--muted); text-align:center; }}
</style></head>
<body>
  <form class="card" method="post" action="/oauth/consent" autocomplete="on">
    <div class="brand"><span class="dot"></span> ServerAlly</div>
    <h1>{cn} wants to connect to your ServerAlly account</h1>
    <p class="sub">Sign in to approve. Your AI assistant will then manage your servers on your behalf.</p>
    <div class="perm">
      It will be able to:
      <ul>
        <li>See your servers and their status, metrics, and security findings</li>
        <li>Run the actions you ask it to (read-only to start)</li>
      </ul>
      <div style="margin-top:10px"><span class="safe">It will never see</span> your passwords, SSH keys, or host fingerprints.</div>
    </div>
    <div class="level">
      <label class="lvl"><input type="radio" name="access_level" value="read" checked />
        <span><strong>Read-only</strong> — see status, metrics, security &amp; sites <em>(recommended)</em></span></label>
      <label class="lvl"><input type="radio" name="access_level" value="full" />
        <span><strong>Full access</strong> — also run scans &amp; playbooks, create sites &amp; databases</span></label>
    </div>
    {err_html}
    <label>Email
      <input name="email" type="email" value="{html.escape(email)}" required autocomplete="username" {'' if need_totp else 'autofocus'} />
    </label>
    <label>Password
      <input name="password" type="password" required autocomplete="current-password" />
    </label>
    {totp_html}
    <input type="hidden" name="txn" value="{html.escape(txn)}" />
    <div class="row">
      <button class="deny" name="action" value="deny" type="submit">Deny</button>
      <button class="approve" name="action" value="approve" type="submit">Approve access</button>
    </div>
    <div class="foot">You can revoke this anytime in ServerAlly → Settings.</div>
  </form>
</body></html>"""


@router.get("/oauth/consent", response_class=HTMLResponse)
async def consent_page(request: Request) -> HTMLResponse:
    """Render the login + consent page for a signed authorization transaction."""
    data = verify_txn(request.query_params.get("txn", ""))
    if not data:
        return HTMLResponse(_page(client_name="", txn="", error=_INVALID_LINK), status_code=400)
    return HTMLResponse(_page(client_name=data.get("client_name") or "", txn=request.query_params["txn"]))


@router.post("/oauth/consent")
async def consent_submit(
    request: Request,
    txn: str = Form(...),
    action: str = Form(...),
    email: str = Form(""),
    password: str = Form(""),
    totp_code: str = Form(""),
    access_level: str = Form("read"),
):
    """Handle the approve/deny submission: authenticate, then mint a code + redirect."""
    data = verify_txn(txn)
    if not data:
        return HTMLResponse(_page(client_name="", txn="", error=_INVALID_LINK), status_code=400)

    client_name = data.get("client_name") or ""

    if action == "deny":
        return _redirect_back(data, {"error": "access_denied"})

    email = email.strip()

    def _reject(msg: str, need_totp: bool = False) -> HTMLResponse:
        return HTMLResponse(
            _page(client_name=client_name, txn=txn, error=msg, email=email, need_totp=need_totp),
            status_code=401,
        )

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            auth_service.verify_password(password, _DUMMY_HASH)  # constant-time-ish
            return _reject("Invalid email or password.")
        if not auth_service.verify_password(password, user.password_hash):
            return _reject("Invalid email or password.")
        if not user.is_active:
            return _reject("This account is disabled.")
        if user.totp_enabled:
            if not (totp_code and totp_service.verify(user.totp_secret, totp_code)):
                return _reject("Enter your two-factor code to continue.", need_totp=True)

        # Plan gate — MCP is a paid-tier feature (only enforced when plan limits are on).
        if not mcp_enabled_for(user):
            return HTMLResponse(
                _page(client_name=client_name, txn=txn, email=email,
                      error="Connecting an AI client requires a Pro plan. Upgrade in ServerAlly, then try again."),
                status_code=403,
            )

        # Access level the user chose: Full = read + write; Read-only = read only (default).
        scopes = ALL_SCOPES if access_level == "full" else DEFAULT_SCOPES
        redirect_url = await oauth_provider.create_authorization_code(data, str(user.id), scopes=scopes)
        await audit_service.audit(
            db, user, "mcp.oauth.approve", request=request,
            meta={"client_id": data.get("client_id"), "client_name": client_name, "scopes": scopes},
        )

    logger.info("MCP OAuth: %s approved %s access for client %s", email, access_level, data.get("client_id"))
    return RedirectResponse(redirect_url, status_code=302)
