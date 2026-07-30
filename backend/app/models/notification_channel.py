"""A place the customer wants to be told things — named once, used everywhere.

Before this, every alert rule carried its own copy of the destination. An agency watching
CPU, RAM and disk across 15 servers had 45 rules each holding the same Slack URL, and
changing that URL meant editing 45 rows by hand. A channel is defined once, given a name
the customer chooses ("Ops Slack", "My phone"), and referenced.

Where the settings live follows one rule: **the destination belongs to the channel, the
provider account does not.** A Slack webhook, an email address, a Telegram bot and chat are
all specific to one destination, so they sit here. Twilio's account credentials are
account-wide and already live in `notification_providers` — copying them into every SMS
channel would mean rotating them in several places and getting it wrong in one.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: The four the customer asked for. Adding a fifth means a sender in
#: `channel_service.deliver` and a config shape in `REQUIRED_FIELDS` — nothing else.
CHANNEL_KINDS = ("email", "slack", "telegram", "sms")


class NotificationChannel(Base):
    """One named destination for alerts."""

    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: What the customer calls it. The whole point of the feature is picking "Ops Slack"
    #: from a list instead of pasting a URL, so this is required and unique per account.
    label: Mapped[str] = mapped_column(String(80), nullable=False)

    #: AES-256-GCM at rest and NEVER returned by any endpoint — a Slack webhook URL is a
    #: bearer credential, and a Telegram bot token is a full bot takeover. Same rule as
    #: server credentials and backup destinations.
    encrypted_config: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Set when a test message actually arrived. A channel that has never been proven is
    #: shown as unverified rather than assumed working — the whole reason this feature
    #: exists is that silently-broken alerting is worse than none.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Why the last send failed, in the customer's words. Kept so the UI can say what is
    #: wrong instead of leaving them to guess.
    last_error: Mapped[str | None] = mapped_column(String(300))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    __table_args__ = (
        # Two channels called "Ops Slack" makes the picker useless, which defeats the point.
        UniqueConstraint("user_id", "label", name="uq_notification_channel_label"),
    )
