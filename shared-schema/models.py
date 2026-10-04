"""
Shared Pydantic Models for Roshetta Pharmacy System.
Used across FastAPI backend and LangGraph agents.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    OWNER = "owner"
    PHARMACIST = "pharmacist"
    CASHIER = "cashier"
    VIEWER = "viewer"


class ActionType(str, Enum):
    LOG_SALE = "log_sale"
    LOG_EXPENSE = "log_expense"
    LOG_RESTOCK = "log_restock"
    PRESCRIPTION_SCAN = "prescription_scan"
    INVOICE_SCAN = "invoice_scan"
    QUERY = "query"
    GENERAL_CHAT = "general_chat"


class ActionStatus(str, Enum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ProposedItem(BaseModel):
    id: Optional[int] = None
    item_name: str
    quantity: float = 1.0
    unit_price: float = 0.0
    subtotal: float = 0.0
    matched_inventory_id: Optional[int] = None
    stock_available: Optional[float] = None
    category: Optional[str] = None
    not_in_inventory: bool = False
    suggestions: List[Dict[str, Any]] = Field(default_factory=list)


class ActionProposal(BaseModel):
    id: str
    action_type: ActionType
    title: str
    summary_ar: str
    summary_en: str
    items: List[ProposedItem] = Field(default_factory=list)
    total_amount: float = 0.0
    payment_method: str = "cash"
    confidence: float = 1.0
    status: ActionStatus = ActionStatus.PENDING_CONFIRMATION
    created_at: str
    raw_text: Optional[str] = None
    source_image_url: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class DrugInteractionAlert(BaseModel):
    severity: str  # critical | warning | info
    drug_a: str
    drug_b: str
    description_ar: str
    description_en: str


class PrescriptionMedicine(BaseModel):
    name: str
    active_ingredient: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    matched_inventory_id: Optional[int] = None
    stock_available: Optional[float] = None
    unit_price: Optional[float] = None
    generic_alternatives: List[str] = Field(default_factory=list)


class PrescriptionExtraction(BaseModel):
    id: str
    doctor_name: Optional[str] = None
    patient_name: Optional[str] = None
    date: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines: List[PrescriptionMedicine] = Field(default_factory=list)
    safety_alerts: List[DrugInteractionAlert] = Field(default_factory=list)
    confidence: float = 1.0
    source_image_url: Optional[str] = None


class ChatMessage(BaseModel):
    id: str
    sender: str  # user | assistant | system
    text: str
    timestamp: str
    proposal: Optional[ActionProposal] = None
    prescription: Optional[PrescriptionExtraction] = None
    grounded_data: Optional[Dict[str, Any]] = None


class FinancialSummary(BaseModel):
    date: str
    total_sales: float = 0.0
    total_expenses: float = 0.0
    cost_of_goods: Optional[float] = None
    gross_profit: Optional[float] = None
    net_profit: Optional[float] = None
    profit_complete: bool = False
    sales_count: int = 0
    expenses_count: int = 0


class InventoryItemSchema(BaseModel):
    id: int
    barcode: Optional[str] = None
    name_ar: str
    name_en: str
    active_ingredient: Optional[str] = None
    category: str
    stock_qty: float
    min_threshold: float
    unit_buy_price: float
    unit_sell_price: float
    expiry_date: Optional[str] = None


class ActionConfirmRequest(BaseModel):
    edited_items: Optional[List[ProposedItem]] = None
    payment_method: Optional[str] = "cash"
    notes: Optional[str] = None
    confirmed_by_user_id: Optional[int] = None
