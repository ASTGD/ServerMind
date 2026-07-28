"""Firewall and SSH keys — who can reach this server, and who can sign in.

Both read the server on every request rather than keeping a copy. A cached firewall
rule or key list drifts from what is actually enforced, and stale access control shown
as current is worse than showing nothing — someone would trust a key that is gone, or
remove a rule that is not the one they are looking at.

That also makes the guards correct. ufw renumbers its rules after every delete, so a
removal is only safe against the listing it was chosen from; re-reading immediately
before the change is what keeps the number pointing at the right rule.
"""
from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.server import Server
from app.models.user import User
from app.services import (
    audit_service, connection_manager, file_service,
    firewall_service as fw, sshkey_service as sk,
)
from app.services.crypto_service import decrypt

router = APIRouter(prefix="/api/servers/{server_id}", tags=["access"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class RuleIn(BaseModel):
    action: str = Field(default="allow", max_length=10)
    port: str = Field(max_length=20)
    protocol: str = Field(default="tcp", max_length=5)
    source: str = Field(default="", max_length=60)
    comment: str = Field(default="", max_length=120)


class RuleRef(BaseModel):
    """Identifies a rule from the listing the customer is looking at."""
    index: int | None = None
    port: str = Field(default="", max_length=20)
    protocol: str = Field(default="tcp", max_length=5)
    source: str = Field(default="", max_length=60)
    comment: str = Field(default="", max_length=160)


class KeyIn(BaseModel):
    public_key: str = Field(max_length=sk.MAX_LINE)
    label: str = Field(default="", max_length=120)


def _ssh_only(server: Server) -> None:
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=422,
            detail="This only works on servers ServerAlly connects to over SSH.")


# ── firewall ──────────────────────────────────────────────────────────────────
async def _read_firewall(server: Server) -> fw.FirewallState:
    out, err, _code = await connection_manager.execute(
        server, fw.discovery_probe(server.port or 22))
    if not (out or "").strip():
        raise HTTPException(status_code=502,
                            detail=f"Could not read the firewall: {(err or '').strip()[:200]}")
    return fw.parse_probe(out, ssh_port=server.port or 22)


def _public(state: fw.FirewallState) -> dict:
    return {
        "manager": state.manager, "active": state.active,
        "default_incoming": state.default_incoming, "note": state.note,
        "ssh_port": state.ssh_port, "our_ip": state.our_ip,
        "manageable": state.manager in (fw.UFW, fw.FIREWALLD),
        "rules": [{
            "index": r.index, "action": r.action, "port": r.port,
            "protocol": r.protocol, "source": r.source, "comment": r.comment,
            "describes": fw.describe(r, state),
            # So the screen can grey out Remove instead of offering it and then
            # refusing — a button that always errors is worse than no button.
            "protected": bool(fw.lockout_risk(state, without=r)),
        } for r in state.rules],
    }


@router.get("/firewall")
async def get_firewall(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db)
    _ssh_only(server)
    return _public(await _read_firewall(server))


@router.post("/firewall/rules", status_code=201)
async def add_rule(server_id: str, body: RuleIn, db: DBDep,
                   current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _ssh_only(server)
    state = await _read_firewall(server)
    try:
        rule = fw.Rule(action=fw.valid_action(body.action), port=fw.valid_port(body.port),
                       protocol=fw.valid_protocol(body.protocol),
                       source=fw.valid_source(body.source), comment=body.comment.strip())
        risk = fw.lockout_risk(state, plus=rule)
        if risk:
            raise HTTPException(status_code=409, detail=risk)
        cmd = fw.add_command(state, rule)
    except fw.InvalidRule as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    out, err, code = await connection_manager.execute(server, cmd)
    if code != 0:
        raise HTTPException(status_code=502,
                            detail=f"The firewall refused that: {(err or out).strip()[:300]}")
    await audit_service.audit(db, current_user, "firewall.rule_added",
                              target_type="server", target_id=server_id,
                              meta={"action": rule.action, "port": rule.port,
                                    "protocol": rule.protocol, "source": rule.source})
    return _public(await _read_firewall(server))


@router.post("/firewall/rules/remove")
async def remove_rule(server_id: str, body: RuleRef, db: DBDep,
                      current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _ssh_only(server)
    # Re-read first. ufw renumbers on every delete, so a number chosen against an
    # older listing points at a different rule than the customer clicked.
    state = await _read_firewall(server)
    match = None
    for r in state.rules:
        if body.index is not None and r.index == body.index:
            match = r
            break
        if body.index is None and r.port == body.port and r.protocol == body.protocol \
                and r.source == body.source and r.comment == body.comment:
            match = r
            break
    if match is None:
        raise HTTPException(
            status_code=409,
            detail="That rule is not there any more — the firewall has changed since "
                   "this list was loaded. Reload and try again.")

    risk = fw.lockout_risk(state, without=match)
    if risk:
        raise HTTPException(status_code=409, detail=risk)
    try:
        cmd = fw.remove_command(state, match)
    except fw.InvalidRule as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    out, err, code = await connection_manager.execute(server, cmd)
    if code != 0:
        raise HTTPException(status_code=502,
                            detail=f"The firewall refused that: {(err or out).strip()[:300]}")
    await audit_service.audit(db, current_user, "firewall.rule_removed",
                              target_type="server", target_id=server_id,
                              meta={"port": match.port, "protocol": match.protocol,
                                    "source": match.source})
    return _public(await _read_firewall(server))


@router.post("/firewall/toggle")
async def toggle_firewall(server_id: str, db: DBDep, current_user: CurrentUser,
                          on: bool = True) -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _ssh_only(server)
    state = await _read_firewall(server)
    try:
        if on:
            risk = fw.lockout_risk(state, enabling=True)
            if risk:
                raise HTTPException(status_code=409, detail=risk)
            cmd = fw.enable_command(state)
        else:
            cmd = fw.disable_command(state)
    except fw.InvalidRule as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    out, err, code = await connection_manager.execute(server, cmd)
    if code != 0:
        raise HTTPException(status_code=502,
                            detail=f"That did not work: {(err or out).strip()[:300]}")
    await audit_service.audit(db, current_user,
                              "firewall.enabled" if on else "firewall.disabled",
                              target_type="server", target_id=server_id,
                              meta={"manager": state.manager})
    return _public(await _read_firewall(server))


# ── ssh keys ──────────────────────────────────────────────────────────────────
def _our_fingerprint(server: Server) -> str | None:
    """The fingerprint of the key we sign in with, if we sign in with one."""
    if server.auth_type != "key":
        return None
    try:
        return sk.public_from_private(decrypt(server.encrypted_cred))
    except Exception:  # noqa: BLE001
        return None


async def _read_keys(server: Server, username: str) -> tuple[str, list[sk.PublicKey], str]:
    out, err, _code = await connection_manager.execute(server, sk.home_probe(username))
    if sk.SENTINEL not in (out or ""):
        raise HTTPException(status_code=502,
                            detail=f"Could not read the keys: {(err or '').strip()[:200]}")
    return sk.parse_home_probe(out)


def _public_keys(keys: list[sk.PublicKey], ours: str | None, server: Server,
                 home: str, note: str, username: str) -> dict:
    return {
        "user": username, "home": home, "note": note,
        "auth_type": server.auth_type,
        "keys": [{
            "fingerprint": k.fingerprint, "type": k.type, "label": k.label,
            "comment": k.comment, "options": k.options, "line": k.line,
            "is_ours": bool(ours and k.fingerprint == ours),
            "protected": bool(sk.removal_risk(keys, k, our_fingerprint=ours,
                                              auth_type=server.auth_type)),
        } for k in keys],
    }
    # The key BODY is deliberately absent. It is not secret, but it is long, useless on
    # screen, and the fingerprint is what a person actually compares.


@router.get("/ssh-keys")
async def get_keys(server_id: str, db: DBDep, current_user: CurrentUser,
                   user: str = "") -> dict:
    server = await resolve_server(server_id, current_user, db)
    _ssh_only(server)
    username = (user or server.username or "root").strip()
    try:
        home, keys, note = await _read_keys(server, username)
    except sk.InvalidKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _public_keys(keys, _our_fingerprint(server), server, home, note, username)


async def _save(server: Server, home: str, keys: list[sk.PublicKey]) -> None:
    """Write the whole file through SFTP, then move it into place with the right mode.

    Staged and moved rather than written directly: a half-written authorized_keys is a
    file sshd cannot parse, and it would be the live one for as long as the write takes.
    """
    staged = f"/tmp/.serverally-keys-{secrets.token_hex(8)}"
    await file_service.write_file(server, staged, sk.render(keys))
    out, err, code = await connection_manager.execute(server,
                                                      sk.write_commands(home, staged))
    if code != 0:
        raise HTTPException(status_code=502,
                            detail=f"Could not save the keys: {(err or out).strip()[:300]}")


@router.post("/ssh-keys", status_code=201)
async def add_key(server_id: str, body: KeyIn, db: DBDep, current_user: CurrentUser,
                  user: str = "") -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _ssh_only(server)
    username = (user or server.username or "root").strip()
    try:
        key = sk.parse_key(body.public_key)
        if body.label.strip():
            key.comment = sk.parse_key(f"{key.type} {key.body} {body.label}").comment
        home, keys, note = await _read_keys(server, username)
    except sk.InvalidKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if any(k.fingerprint == key.fingerprint for k in keys):
        raise HTTPException(status_code=409,
                            detail="That key is already on this server.")
    if len(keys) >= sk.MAX_KEYS:
        raise HTTPException(status_code=409,
                            detail=f"This server already has {sk.MAX_KEYS} keys.")

    keys.append(key)
    await _save(server, home, keys)
    await audit_service.audit(db, current_user, "sshkey.added",
                              target_type="server", target_id=server_id,
                              meta={"user": username, "fingerprint": key.fingerprint,
                                    "label": key.label})
    home, keys, note = await _read_keys(server, username)
    return _public_keys(keys, _our_fingerprint(server), server, home, note, username)


@router.delete("/ssh-keys/{fingerprint:path}")
async def remove_key(server_id: str, fingerprint: str, db: DBDep,
                     current_user: CurrentUser, user: str = "") -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _ssh_only(server)
    username = (user or server.username or "root").strip()
    try:
        home, keys, note = await _read_keys(server, username)
    except sk.InvalidKey as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    target = next((k for k in keys if k.fingerprint == fingerprint), None)
    if target is None:
        raise HTTPException(status_code=404, detail="That key is not on this server.")

    risk = sk.removal_risk(keys, target, our_fingerprint=_our_fingerprint(server),
                           auth_type=server.auth_type)
    if risk:
        raise HTTPException(status_code=409, detail=risk)

    await _save(server, home, [k for k in keys if k.fingerprint != fingerprint])
    await audit_service.audit(db, current_user, "sshkey.removed",
                              target_type="server", target_id=server_id,
                              meta={"user": username, "fingerprint": fingerprint,
                                    "label": target.label})
    home, keys, note = await _read_keys(server, username)
    return _public_keys(keys, _our_fingerprint(server), server, home, note, username)
