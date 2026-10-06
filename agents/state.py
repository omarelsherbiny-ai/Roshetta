# agents/state.py
from typing import List, Optional, Dict, Any
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    user_query: str
    context_id: str
    intent: str  # log_sale, log_expense, log_restock, create_product, query_finance, query_stock, prescription_scan, invoice_scan, general_chat
    extracted_items: List[Dict[str, Any]]
    total_amount: float
    payment_method: str
    notes: Optional[str]
    # create_product: name and prices read from the message (None when not given)
    product_draft: Optional[Dict[str, Any]]
    
    # Financial grounding
    financial_data: Optional[Dict[str, Any]]
    
    # Inventory grounding
    inventory_data: Optional[List[Dict[str, Any]]]
    
    # Safety checks
    safety_alerts: Optional[List[Dict[str, Any]]]
    
    # Final output
    proposal: Optional[Dict[str, Any]]
    prescription: Optional[Dict[str, Any]]
    answer_text: str
    language: str  # 'ar' | 'en'
    error: Optional[str]