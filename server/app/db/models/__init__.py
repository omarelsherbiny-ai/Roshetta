# server/app/db/models/__init__.py
from server.app.services.clock import utc_now_naive
from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    ForeignKey, Text, Boolean, UniqueConstraint, Index, Numeric, text
)
from sqlalchemy.orm import relationship
from server.app.db.session import Base


# ─────────────────────────────────────────────────────────────
# PHARMACY PROFILE  (one row per physical pharmacy branch)
# ─────────────────────────────────────────────────────────────
class PharmacyProfile(Base):
    __tablename__ = "pharmacy_profile"

    id               = Column(Integer, primary_key=True, index=True)
    # No demo defaults (debt item 21): every create path must set its own values.
    # pharmacy_name stays "" (not None) because PharmacyResponse.pharmacy_name is a required str.
    pharmacy_name    = Column(String(150), default="")
    owner_name       = Column(String(100), nullable=True)
    phone            = Column(String(20),  nullable=True)
    address          = Column(String(255), nullable=True)
    license_number   = Column(String(50),  nullable=True)
    tax_id           = Column(String(50),  nullable=True)
    currency         = Column(String(10),  default="EGP")
    # western = 123 | eastern = ١٢٣
    numerals_format  = Column(String(10),  default="western")
    low_stock_default= Column(Float,       default=5.0)
    language         = Column(String(10),  default="ar")
    is_initialized   = Column(Boolean,     default=False)
    # Legacy compatibility column. Secure PharmacyInvitation records now handle staff admission.
    invite_code      = Column(String(16),  unique=True, index=True, nullable=True)
    updated_at       = Column(DateTime,    default=utc_now_naive, onupdate=utc_now_naive)

    members = relationship("PharmacyMember", back_populates="pharmacy")


# ─────────────────────────────────────────────────────────────
# USER  (any person who logs in — can belong to many pharmacies)
# ─────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String(100), nullable=False)
    phone        = Column(String(20),  unique=True, index=True, nullable=False)
    pin          = Column(String(10),  default="")  # legacy plaintext PIN; cleared when upgraded
    language_pref= Column(String(10),  default="ar")
    location     = Column(String(160), nullable=True)
    photo_url    = Column(String(500), nullable=True)
    birth_date   = Column(String(10), nullable=True)  # ISO YYYY-MM-DD; optional profile detail
    is_active    = Column(Boolean,     default=True)
    created_at   = Column(DateTime,    default=utc_now_naive)
    # Every token issued before this moment is refused (set by a PIN change); NULL = none.
    tokens_valid_after = Column(DateTime, nullable=True)

    memberships  = relationship(
        "PharmacyMember",
        foreign_keys="[PharmacyMember.user_id]",
        back_populates="user"
    )


class UserCredential(Base):
    """Separate hashed credentials so the existing users table needs no destructive migration."""
    __tablename__ = "user_credentials"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    pin_salt = Column(String(64), nullable=False)
    pin_hash = Column(String(128), nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    user = relationship("User")


class AuthThrottle(Base):
    """Persistent per-client authentication throttling state."""
    __tablename__ = "auth_throttles"

    key          = Column(String(64), primary_key=True)
    failures     = Column(Integer, nullable=False, default=0)
    window_start = Column(DateTime, nullable=False, default=utc_now_naive)
    blocked_until= Column(DateTime, nullable=True)


class RevokedAccessToken(Base):
    """Revoked signed sessions retained only until their original expiry."""
    __tablename__ = "revoked_access_tokens"

    token_id   = Column(String(64), primary_key=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=False, default=utc_now_naive)


# ─────────────────────────────────────────────────────────────
# PHARMACY MEMBER  (junction: user ↔ pharmacy + role + perms)
#
#  role values:
#    owner       – full control: settings, staff, reports, all writes
#    pharmacist  – clinical: all sales, prescriptions, drug-safety
#    cashier     – sales only: log sales & expenses; no settings/reports
#    viewer      – read-only: reports only; no writes whatsoever
# ─────────────────────────────────────────────────────────────
class PharmacyMember(Base):
    __tablename__ = "pharmacy_members"
    __table_args__ = (UniqueConstraint("user_id", "pharmacy_id", name="uq_user_pharmacy"),)

    id           = Column(Integer,    primary_key=True, index=True)
    pharmacy_id  = Column(Integer,    ForeignKey("pharmacy_profile.id"), nullable=False)
    user_id      = Column(Integer,    ForeignKey("users.id"),            nullable=False)
    role         = Column(String(20), default="cashier")   # owner|pharmacist|cashier|viewer
    custom_role_id = Column(Integer, ForeignKey("pharmacy_roles.id"), nullable=True)
    invited_by   = Column(Integer,    ForeignKey("users.id"), nullable=True)
    is_active    = Column(Boolean,    default=True)
    joined_at    = Column(DateTime,   default=utc_now_naive)

    pharmacy     = relationship("PharmacyProfile", back_populates="members")
    user         = relationship("User", foreign_keys=[user_id], back_populates="memberships")
    custom_role  = relationship("PharmacyRole")


class PharmacyOwnershipSlot(Base):
    __tablename__ = "pharmacy_ownership_slots"
    __table_args__ = (
        UniqueConstraint("user_id", "slot_number", name="uq_user_pharmacy_owner_slot"),
        UniqueConstraint("pharmacy_id", name="uq_owned_pharmacy_slot"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False)
    slot_number = Column(Integer, nullable=False)  # 1..5, enforced by the creation service
    created_at = Column(DateTime, default=utc_now_naive)


class PharmacyRole(Base):
    __tablename__ = "pharmacy_roles"
    __table_args__ = (UniqueConstraint("pharmacy_id", "name", name="uq_pharmacy_role_name"),)

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    name = Column(String(60), nullable=False)
    scopes_json = Column(Text, nullable=False, default="[]")
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)


class PharmacyInvitation(Base):
    __tablename__ = "pharmacy_invitations"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    fixed_role = Column(String(20), nullable=True)
    custom_role_id = Column(Integer, ForeignKey("pharmacy_roles.id"), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    max_uses = Column(Integer, nullable=False, default=1)
    used_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)

    custom_role = relationship("PharmacyRole")


class StaffShift(Base):
    __tablename__ = "staff_shifts"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # Monday=0 through Sunday=6
    start_time = Column(String(5), nullable=False)  # local HH:MM
    end_time = Column(String(5), nullable=False)
    timezone = Column(String(64), nullable=False)
    effective_from = Column(String(10), nullable=True)
    effective_until = Column(String(10), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)


class StaffCompensation(Base):
    __tablename__ = "staff_compensation"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pay_type = Column(String(24), nullable=False)  # monthly|hourly|daily|commission|other
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), nullable=False, default="EGP")
    details = Column(Text, nullable=True)
    effective_from = Column(String(10), nullable=True)
    effective_until = Column(String(10), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)


# ─────────────────────────────────────────────────────────────
# ROLE PERMISSIONS MATRIX  (enforced server-side)
# ─────────────────────────────────────────────────────────────
ROLE_PERMISSIONS = {
    "owner": {
        "log_sale", "log_expense", "log_restock",
        "view_reports", "view_inventory", "manage_inventory", "manage_staff",
        "view_audit", "view_staff_activity", "edit_settings", "scan_prescription",
        "manage_roles", "manage_schedule", "manage_compensation",
        "manage_payables",
    },
    "pharmacist": {
        "log_sale", "log_expense", "log_restock",
        "view_reports", "view_inventory", "manage_inventory",
        "view_audit", "scan_prescription", "manage_payables",
    },
    "cashier": {
        "log_sale", "log_expense",
        "view_reports", "view_inventory",  # only their own shift and product lookup
    },
    "viewer": {
        "view_reports",
    },
}


def has_permission(role: str, permission: str, scopes: list[str] | None = None) -> bool:
    if role == "owner":
        return True
    if scopes is not None:
        if permission == "view_inventory" and "manage_inventory" in scopes:
            return True
        return permission in scopes
    return permission in ROLE_PERMISSIONS.get(role, set())


# ─────────────────────────────────────────────────────────────
# INVENTORY
# ─────────────────────────────────────────────────────────────
class InventoryItem(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        Index(
            "uq_inventory_pharmacy_barcode",
            "pharmacy_id",
            "barcode",
            unique=True,
            sqlite_where=text("barcode IS NOT NULL"),
            postgresql_where=text("barcode IS NOT NULL"),
        ),
    )

    id               = Column(Integer,   primary_key=True, index=True)
    pharmacy_id      = Column(Integer,   ForeignKey("pharmacy_profile.id"), nullable=True)
    barcode          = Column(String(50),index=True, nullable=True)
    name_ar          = Column(String(150),index=True, nullable=False)
    name_en          = Column(String(150),index=True, nullable=False)
    active_ingredient= Column(String(150),index=True, nullable=True)
    category         = Column(String(50), nullable=True)
    stock_qty        = Column(Float,      default=0.0)
    min_threshold    = Column(Float,      default=5.0)
    unit_buy_price   = Column(Float,      default=0.0)
    unit_sell_price  = Column(Float,      default=0.0)
    expiry_date      = Column(String(20), nullable=True)
    created_at       = Column(DateTime,   default=utc_now_naive)

    batches = relationship("InventoryBatch", back_populates="item", cascade="all, delete-orphan")


class Category(Base):
    """A product category owned by one pharmacy; exists with or without products.

    Products still carry the category as plain text in ``inventory.category``;
    this table is what makes an empty category possible. Names are unique per
    pharmacy ignoring letter case (the index below).
    """
    __tablename__ = "categories"
    __table_args__ = (
        Index("uq_categories_pharmacy_name", "pharmacy_id", text("lower(name)"), unique=True),
    )

    id          = Column(Integer,    primary_key=True, index=True)
    pharmacy_id = Column(Integer,    ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    name        = Column(String(50), nullable=False)
    created_at  = Column(DateTime,   default=utc_now_naive, nullable=False)


class InventoryBatch(Base):
    """Specific stock lot/batch with discrete purchase and selling prices."""
    __tablename__ = "inventory_batches"

    id              = Column(Integer, primary_key=True, index=True)
    pharmacy_id     = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    item_id         = Column(Integer, ForeignKey("inventory.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_number    = Column(String(60), nullable=True)
    quantity        = Column(Float, nullable=False, default=0.0)
    unit_buy_price  = Column(Float, nullable=False, default=0.0)
    unit_sell_price = Column(Float, nullable=False, default=0.0)
    expiry_date     = Column(String(20), nullable=True)
    created_at      = Column(DateTime, default=utc_now_naive)
    updated_at      = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    item = relationship("InventoryItem", back_populates="batches")


class InventoryPriceHistory(Base):
    """Append-only snapshots of product price changes within a pharmacy."""
    __tablename__ = "inventory_price_history"

    id                       = Column(Integer, primary_key=True, index=True)
    pharmacy_id              = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    item_id                  = Column(Integer, ForeignKey("inventory.id"), nullable=False, index=True)
    previous_unit_buy_price  = Column(Float, nullable=True)
    previous_unit_sell_price = Column(Float, nullable=True)
    unit_buy_price           = Column(Float, nullable=False)
    unit_sell_price          = Column(Float, nullable=False)
    changed_by               = Column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at              = Column(DateTime, nullable=False, default=utc_now_naive)


# ─────────────────────────────────────────────────────────────
# LEDGER
# ─────────────────────────────────────────────────────────────
class LedgerEntry(Base):
    __tablename__ = "entries"

    id             = Column(String(50), primary_key=True, index=True)
    pharmacy_id    = Column(Integer,    ForeignKey("pharmacy_profile.id"), nullable=True)
    entry_type     = Column(String(20), nullable=False)   # log_sale|log_expense|log_restock
    total_amount   = Column(Float,      nullable=False)
    payment_method = Column(String(20), default="cash")   # cash|card|credit
    notes          = Column(Text,       nullable=True)
    supplier_name  = Column(String(150), nullable=True)   # free text; restocks only
    created_by     = Column(Integer,    ForeignKey("users.id"), nullable=True)
    confirmed_by   = Column(Integer,    ForeignKey("users.id"), nullable=True)
    confirmed_at   = Column(DateTime,   default=utc_now_naive)
    created_at     = Column(DateTime,   default=utc_now_naive)

    items = relationship("LedgerEntryItem", back_populates="entry", cascade="all, delete-orphan")


class LedgerEntryItem(Base):
    __tablename__ = "entry_items"

    id         = Column(Integer,    primary_key=True, index=True)
    entry_id   = Column(String(50), ForeignKey("entries.id"), nullable=False)
    item_id    = Column(Integer,    ForeignKey("inventory.id"), nullable=True)
    item_name  = Column(String(150),nullable=False)
    quantity   = Column(Float,      nullable=False)
    unit_price = Column(Float,      nullable=False)
    unit_cost  = Column(Float,      nullable=True)  # cost snapshot for gross-profit reporting
    subtotal   = Column(Float,      nullable=False)

    entry = relationship("LedgerEntry", back_populates="items")


class RestockSettlement(Base):
    """A payment made to a supplier against one credit restock (supplier payables).

    Settlements are not expenses: cost of goods is recognised at sale from FIFO
    unit_cost, so they never change profit. Remaining = entry total - sum of settlements.
    """
    __tablename__ = "restock_settlements"

    id             = Column(Integer,    primary_key=True, index=True)
    pharmacy_id    = Column(Integer,    ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    entry_id       = Column(String(50), ForeignKey("entries.id"), nullable=False, index=True)
    amount         = Column(Float,      nullable=False)
    payment_method = Column(String(20), nullable=False)   # cash|card
    paid_by        = Column(Integer,    ForeignKey("users.id"), nullable=False)
    paid_at        = Column(DateTime,   nullable=False, default=utc_now_naive)
    created_at     = Column(DateTime,   default=utc_now_naive)


# ─────────────────────────────────────────────────────────────
# PRESCRIPTIONS
# ─────────────────────────────────────────────────────────────
class PrescriptionRecord(Base):
    __tablename__ = "prescriptions"

    id             = Column(String(50), primary_key=True, index=True)
    pharmacy_id    = Column(Integer,    ForeignKey("pharmacy_profile.id"), nullable=True)
    doctor_name    = Column(String(100),nullable=True)
    patient_name   = Column(String(100),nullable=True)
    image_url      = Column(String(255),nullable=True)
    extracted_json = Column(Text,       nullable=True)
    safety_status  = Column(String(50), default="pending_review")
    reviewed_by    = Column(Integer,    ForeignKey("users.id"), nullable=True)   # must be pharmacist/owner
    review_decision = Column(String(30), nullable=True)  # reviewed | held
    review_notes   = Column(Text,       nullable=True)
    reviewed_at    = Column(DateTime,   nullable=True)
    created_at     = Column(DateTime,   default=utc_now_naive)


class StoredUpload(Base):
    """Private tenant-scoped file metadata for prescription and inventory images."""
    __tablename__ = "stored_uploads"

    id           = Column(Integer, primary_key=True, index=True)
    storage_key  = Column(String(80), unique=True, index=True, nullable=False)
    pharmacy_id  = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    uploaded_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    content_type = Column(String(100), nullable=False)
    document_type = Column(String(30), nullable=False, default="prescription")
    created_at   = Column(DateTime, default=utc_now_naive)


class PendingAction(Base):
    """Server-owned proposal awaiting confirmation or cancellation."""
    __tablename__ = "pending_actions"

    id           = Column(String(100), primary_key=True)
    pharmacy_id  = Column(Integer, ForeignKey("pharmacy_profile.id"), nullable=False, index=True)
    created_by   = Column(Integer, ForeignKey("users.id"), nullable=True)
    action_type  = Column(String(40), nullable=False)
    status       = Column(String(30), nullable=False, default="pending_confirmation")
    payload_json = Column(Text, nullable=False)
    created_at   = Column(DateTime, default=utc_now_naive)
    updated_at   = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


# ─────────────────────────────────────────────────────────────
# DRUG INTERACTIONS
# ─────────────────────────────────────────────────────────────
class DrugInteractionRule(Base):
    __tablename__ = "drug_interactions"

    id            = Column(Integer, primary_key=True, index=True)
    drug_a        = Column(String(100), index=True, nullable=False)
    drug_b        = Column(String(100), index=True, nullable=False)
    severity      = Column(String(20),  default="warning")   # critical|warning|info
    description_ar= Column(Text,        nullable=False)
    description_en= Column(Text,        nullable=False)


# ─────────────────────────────────────────────────────────────
# AUDIT LOG  (immutable — never deleted)
# ─────────────────────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_log"

    id          = Column(Integer,   primary_key=True, index=True)
    pharmacy_id = Column(Integer,   ForeignKey("pharmacy_profile.id"), nullable=True)
    action_type = Column(String(50),nullable=False)
    entity_type = Column(String(50),nullable=False)
    entity_id   = Column(String(50),nullable=False)
    user_id     = Column(Integer,   nullable=True)
    user_name   = Column(String(100),nullable=True)
    user_role   = Column(String(20), nullable=True)    # snapshot of role at time of action
    details_json= Column(Text,       nullable=True)
    timestamp   = Column(DateTime,   default=utc_now_naive)