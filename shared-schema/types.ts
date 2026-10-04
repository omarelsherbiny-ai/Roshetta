/**
 * Shared TypeScript definitions for Roshetta Frontend and Mobile.
 * Synchronized with shared-schema/models.py.
 */

export type UserRole = 'owner' | 'pharmacist' | 'cashier' | 'viewer';

export type ActionType =
  | 'log_sale'
  | 'log_expense'
  | 'log_restock'
  | 'prescription_scan'
  | 'invoice_scan'
  | 'query'
  | 'general_chat';

export type ActionStatus =
  | 'pending_confirmation'
  | 'confirmed'
  | 'cancelled'
  | 'rejected';

export interface ProposedItem {
  id?: number;
  item_name: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
  matched_inventory_id?: number | null;
  stock_available?: number | null;
  category?: string | null;
  not_in_inventory?: boolean;
  suggestions?: { id: number; name_ar: string; stock_qty: number; unit_sell_price: number }[];
}

export interface ActionProposal {
  id: string;
  action_type: ActionType;
  title: string;
  summary_ar: string;
  summary_en: string;
  items: ProposedItem[];
  total_amount: number;
  payment_method: string;
  confidence: number;
  status: ActionStatus;
  created_at: string;
  raw_text?: string | null;
  source_image_url?: string | null;
  warnings?: string[];
}

export interface DrugInteractionAlert {
  severity: 'critical' | 'warning' | 'info';
  drug_a: string;
  drug_b: string;
  description_ar: string;
  description_en: string;
}

export interface PrescriptionMedicine {
  name: string;
  active_ingredient?: string | null;
  dosage?: string | null;
  frequency?: string | null;
  duration?: string | null;
  matched_inventory_id?: number | null;
  stock_available?: number | null;
  unit_price?: number | null;
  generic_alternatives?: string[];
}

export interface PrescriptionExtraction {
  id: string;
  doctor_name?: string | null;
  patient_name?: string | null;
  date?: string | null;
  diagnosis?: string | null;
  medicines: PrescriptionMedicine[];
  safety_alerts: DrugInteractionAlert[];
  confidence: number;
  source_image_url?: string | null;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  text: string;
  timestamp: string;
  proposal?: ActionProposal | null;
  prescription?: PrescriptionExtraction | null;
  grounded_data?: Record<string, any> | null;
}

export interface FinancialSummary {
  date: string;
  total_sales: number;
  total_expenses: number;
  cost_of_goods?: number | null;
  gross_profit?: number | null;
  net_profit: number | null;
  profit_complete: boolean;
  sales_count: number;
  expenses_count: number;
}

export interface InventoryItemSchema {
  id: number;
  barcode?: string | null;
  name_ar: string;
  name_en: string;
  active_ingredient?: string | null;
  category: string;
  stock_qty: number;
  min_threshold: number;
  unit_buy_price: number;
  unit_sell_price: number;
  expiry_date?: string | null;
}

export interface InventorySummary {
  item_count: number;
  total_units: number;
  potential_sales_value: number;
  stock_cost_value: number | null;
  stock_cost_value_complete: boolean;
}

export interface ActionConfirmRequest {
  edited_items?: ProposedItem[];
  payment_method?: string;
  notes?: string;
  confirmed_by_user_id?: number;
}
