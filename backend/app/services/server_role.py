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
