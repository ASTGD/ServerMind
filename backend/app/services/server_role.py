"""What ServerAlly IS to one Linux server.

Two products meet on this page. On some servers ServerAlly is the control panel — we
install the web server, we write the vhosts, we own the certificates. On others a real
control panel owns the machine and we are the thing watching it. Everything follows from
which one it is: the menu, what Ally will do, who renews the certificates.

Until now that fact was only ever INFERRED and never stated. A fresh server quietly became
ours the moment somebody pressed Set up — which is a decision, made without being offered.

**Derived, never stored.** A column would go stale the day somebody installs CyberPanel by
hand, and then the screen would insist we run a server the panel has taken over. The
detector already notices a panel; reading the answer off the facts means the page cannot
disagree with the machine.
"""
from __future__ import annotations

#: `undecided` — a clean server; both doors are open.
#: `serverally` — we are the panel here.
#: `panel`      — a control panel owns it and we watch it.
ROLES = ("undecided", "serverally", "panel")

PANEL_LABELS = {
    "cyberpanel": "CyberPanel",
    "cpanel": "cPanel",
    "whm": "WHM",
    "plesk": "Plesk",
    "directadmin": "DirectAdmin",
    "hestiacp": "HestiaCP",
    "aapanel": "aaPanel",
    "cloudpanel": "CloudPanel",
}


#: What makes a machine "not fresh" for this decision.
#:
#: Runtimes and open ports are deliberately excluded. python3 and sshd are on every Ubuntu
#: that has ever booted, so counting them would mean no server is ever fresh and the word
#: would stop meaning anything — while a web server, a database, a container or a panel are
#: each something one of the two paths would install over or fight with.
NOT_FRESH = ("web_servers", "databases", "containers", "panels")


def setup_applies(finished_at, identity_changed_at) -> bool:
    """Does a finished setup still describe the machine that is there now?

    No when it finished before the customer told us this is different hardware — that setup
    installed nginx, PHP and a database on a machine that no longer exists, and counting it
    is what kept a rebuilt server claiming ServerAlly was its control panel, so the setup
    choice never came back.

    A setup with no finish time is still running; treating that as "before the rebuild"
    would discard work happening right now.
    """
    if identity_changed_at is None or finished_at is None:
        return True
    return finished_at > identity_changed_at


def is_fresh(found: dict | None) -> bool | None:
    """Is this machine empty enough that both paths are honest?

    ``None`` when we could not look. Not the same as True, and the page must not treat it
    as such: "we could not check" and "there is nothing here" lead somewhere different.
    """
    if found is None:
        return None
    return not any(found.get(key) for key in NOT_FRESH)


def panel_label(panel_type: str | None) -> str:
    """The word the customer knows. A panel we have no name for keeps a generic one rather
    than showing a raw database value."""
    return PANEL_LABELS.get((panel_type or "").lower(), "A control panel")


def decide(*, connection_type: str, panel_type: str | None, setup_done: bool,
           site_count: int, setup_running: bool = False) -> dict:
    """Which of the two ServerAlly is here, and whether that is still open to change.

    Pure, so every branch is directly testable. The order is the meaning:

    1. a panel that is actually installed wins over anything we believe about the server —
       it is on the machine and we are not going to argue with it;
    2. our own setup having run means we already installed nginx, PHP and a database, so
       the panel door is shut: a control panel wants a clean machine, and the only way back
       is rebuilding the server;
    3. sites already being served, even ones we merely found, closes it for the same
       reason — the box is in use, and both doors involve changing what serves it.

    Anything else is a clean server with a real choice in front of it, which is the one
    moment this decision can be made cheaply.
    """
    if connection_type != "ssh":
        # Windows, RDP and hosting connections do not host sites through us at all, so the
        # question does not arise. Saying "not applicable" is honest; picking one is not.
        return {"applies": False, "role": None, "can_choose": False,
                "panel": None, "panel_label": None, "why": None}

    if panel_type:
        return {
            "applies": True, "role": "panel", "can_choose": False,
            "panel": panel_type, "panel_label": panel_label(panel_type),
            "why": f"{panel_label(panel_type)} is installed on this server.",
        }

    if setup_done:
        return {
            "applies": True, "role": "serverally", "can_choose": False,
            "panel": None, "panel_label": None,
            "why": "This server was set up by ServerAlly, so a control panel would need it "
                   "rebuilt from scratch.",
        }

    if site_count > 0:
        return {
            "applies": True, "role": "serverally", "can_choose": False,
            "panel": None, "panel_label": None,
            "why": "This server is already serving websites, so it is not a clean machine "
                   "for a control panel to install onto.",
        }

    if setup_running:
        # Still undecided — the setup has not finished, so nothing is installed yet — but
        # the choice is no longer open, and showing the two doors again would throw away
        # the customer's answer while the work they asked for is running.
        return {
            "applies": True, "role": "undecided", "can_choose": False,
            "panel": None, "panel_label": None,
            "why": "A setup is running on this server.",
        }

    return {
        "applies": True, "role": "undecided", "can_choose": True,
        "panel": None, "panel_label": None, "why": None,
    }
