"""Persistence model.

Deviations from the initial entity list (justified in docs/architecture.md):
- ``rule_conditions`` / ``rule_actions`` are not separate tables: a rule is a
  JSON document validated by ``RuleDefinition`` (schema-versioned). Nested
  condition trees map poorly to relational rows and are always loaded whole.
  ``rule_versions`` keeps every saved revision.
- ``catalog`` == the active snapshot of a source (1:1 in this phase).
- ``product_attributes`` is replaced by a JSON ``data`` column on products,
  plus denormalized columns for indexed search/sort.
- ``channel_profiles`` are code-level validation profiles (google), selected by
  ``channels.kind``; ``channel_mappings`` live in ``channels.settings``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from feedstudio.db import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30), default="admin")


class Source(Base, TimestampMixin):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))  # upload | url
    url: Mapped[str | None] = mapped_column(Text)
    item_tag: Mapped[str | None] = mapped_column(String(200))
    schedule: Mapped[str] = mapped_column(String(20), default="manual")  # manual | interval | daily
    schedule_config: Mapped[dict | None] = mapped_column(JSONType)  # see feedstudio/scheduling.py
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_scheduled_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id", use_alter=True, ondelete="SET NULL"))
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    active_snapshot: Mapped["SourceSnapshot | None"] = relationship(foreign_keys=[active_snapshot_id], post_update=True)


class SourceCredential(Base, TimestampMixin):
    """Reserved for OAuth/SFTP credentials (Phase 3). Secrets are never returned by the API."""

    __tablename__ = "source_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    encrypted_secret: Mapped[str] = mapped_column(Text)


class SourceSnapshot(Base, TimestampMixin):
    __tablename__ = "source_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|processing|ready|failed
    storage_key: Mapped[str | None] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str | None] = mapped_column(String(20))
    item_tag: Mapped[str | None] = mapped_column(String(300))
    namespaces: Mapped[dict | None] = mapped_column(JSONType)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[dict | None] = mapped_column(JSONType)

    fields: Mapped[list["SourceSchemaField"]] = relationship(cascade="all, delete-orphan", order_by="SourceSchemaField.position")


class SourceSchemaField(Base):
    __tablename__ = "source_schema_fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("source_snapshots.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(200))
    qname: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20))
    inferred_type: Mapped[str] = mapped_column(String(20))
    present_count: Mapped[int] = mapped_column(Integer)
    empty_count: Mapped[int] = mapped_column(Integer)
    max_repeat: Mapped[int] = mapped_column(Integer)
    coverage: Mapped[float] = mapped_column()
    samples: Mapped[list] = mapped_column(JSONType)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("source_snapshots.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    external_id: Mapped[str | None] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSONType)
    # Denormalized for indexed search & sort.
    title: Mapped[str | None] = mapped_column(String(500))
    brand: Mapped[str | None] = mapped_column(String(200))
    product_type: Mapped[str | None] = mapped_column(String(750))
    availability: Mapped[str | None] = mapped_column(String(50))
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    search_text: Mapped[str | None] = mapped_column(Text)
    issue_level: Mapped[str] = mapped_column(String(20), default="valid")
    issue_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_products_snapshot_position", "snapshot_id", "position"),
        Index("ix_products_snapshot_external", "snapshot_id", "external_id"),
        Index("ix_products_snapshot_issue", "snapshot_id", "issue_level"),
    )


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))  # google | csv
    public_token: Mapped[str] = mapped_column(String(64), unique=True)
    settings: Mapped[dict] = mapped_column(JSONType, default=dict)
    # Publish automatically after each scheduled/pipeline run (safety threshold still applies).
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    published_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("feed_versions.id", use_alter=True, ondelete="SET NULL")
    )


class GoogleAccount(Base, TimestampMixin):
    """A Google account connected with OAuth (scope drive.file). The refresh token
    is stored encrypted and never returned by the API."""

    __tablename__ = "google_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    scopes: Mapped[str] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | invalid


class ChannelDestination(Base, TimestampMixin):
    """Where a channel's published feed is delivered after each publication."""

    __tablename__ = "channel_destinations"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="gdrive")
    google_account_id: Mapped[int | None] = mapped_column(ForeignKey("google_accounts.id", ondelete="SET NULL"))
    folder_id: Mapped[str | None] = mapped_column(String(200))
    file_name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    remote_file_id: Mapped[str | None] = mapped_column(String(200))
    remote_url: Mapped[str | None] = mapped_column(Text)
    last_status: Mapped[str | None] = mapped_column(String(20))  # succeeded | failed
    last_error: Mapped[str | None] = mapped_column(Text)
    last_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_version_id: Mapped[int | None] = mapped_column(ForeignKey("feed_versions.id", ondelete="SET NULL"))


class Rule(Base, TimestampMixin):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    definition: Mapped[dict] = mapped_column(JSONType)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str | None] = mapped_column(String(200))


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(200))


class ProcessingJob(Base, TimestampMixin):
    __tablename__ = "processing_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # import | generate
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    progress: Mapped[float] = mapped_column(default=0.0)
    message: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict | None] = mapped_column(JSONType)
    result: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[dict | None] = mapped_column(JSONType)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    events: Mapped[list] = mapped_column(JSONType, default=list)


class FeedVersion(Base, TimestampMixin):
    __tablename__ = "feed_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("source_snapshots.id", ondelete="CASCADE"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="building")  # building|ready|failed
    storage_key: Mapped[str | None] = mapped_column(String(500))
    csv_storage_key: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    rules_snapshot: Mapped[list | None] = mapped_column(JSONType)
    stats: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[dict | None] = mapped_column(JSONType)


class FeedItem(Base):
    __tablename__ = "feed_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("feed_versions.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    external_id: Mapped[str | None] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSONType)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    changed: Mapped[bool] = mapped_column(Boolean, default=False)
    changes: Mapped[list] = mapped_column(JSONType, default=list)
    rule_ids: Mapped[str] = mapped_column(String(2000), default="")  # ",3,5," for LIKE filtering
    issue_level: Mapped[str] = mapped_column(String(20), default="valid")
    rule_issues: Mapped[list] = mapped_column(JSONType, default=list)

    __table_args__ = (
        Index("ix_feed_items_version_position", "version_id", "position"),
        Index("ix_feed_items_version_external", "version_id", "external_id"),
    )


class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("feed_versions.id", ondelete="CASCADE"))
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(20))
    attribute: Mapped[str | None] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        Index("ix_issues_version_code", "version_id", "code"),
        Index("ix_issues_snapshot_code", "snapshot_id", "code"),
        Index("ix_issues_product", "product_id"),
    )


class FeedPublication(Base):
    __tablename__ = "feed_publications"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("feed_versions.id", ondelete="CASCADE"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_by: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(20), default="publish")  # publish | rollback
    note: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
