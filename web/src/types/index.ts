// web/src/types/index.ts (frontend type aliases over the generated OpenAPI DTOs)
import type {
  InventoryBatchResponse,
  InventoryItemResponse,
  InventoryMatchResponse,
  InventoryPriceHistoryResponse,
  InventorySummaryResponse,
  FinancialSummaryResponse,
  LedgerEntryResponse,
  PharmacyActivityResponse,
  AccountSessionResponse,
  AccountRegistrationResponse,
  AccountProfileUpdateResponse,
  UserResponse,
  PharmacyResponse,
  PharmacyStaffResponse,
  PendingActionsResponse,
  ConfirmedActionResponse,
  CancelledActionResponse,
  PharmacyLoginResponse,
  PharmacyRegistrationResponse,
  PharmacySwitchResponse,
  PharmacyProfileUpdateResponse,
  RegisterPharmacyRequest,
  PharmacyProfileUpdate as PharmacyProfileUpdatePayload,
  MyProfileResponse,
  MyProfileUpdateResponse,
  MyActivityResponse,
  PhotoUploadResponse,
  ProfileUpdate,
  HubPharmacyResponse,
  MyPharmaciesResponse as MyPharmaciesResponseSchema,
  PharmacyCreate,
  CreatePharmacyResponse,
  PharmacySelectionResponse,
  PharmacySummaryResponse,
  AcceptedInvitationResponse,
  PharmacyRoleResponse,
  RoleCreate,
  RolesListResponse,
  RolesOverviewResponse,
  RoleOverviewItem,
  RoleMutationResponse,
  RoleAssignmentResponse,
  StaffRemovalResponse,
  InvitationCreate,
  InvitationCreatedResponse,
  InvitationResponse,
  InvitationRevokedResponse,
  PersonalAuditEntryResponse,
  WorkSummaryResponse,
  StaffShiftResponse,
  ShiftInput,
  ScheduleReplaceResponse,
  StaffCompensationResponse,
  CompensationInput,
  CompensationCreatedResponse,
  ChatResponse,
  PrescriptionRecordResponse,
  PrescriptionReviewResponse,
  PayableResponse,
  SettlementCreate,
} from "./openapi.generated";
export type {
  DirectRestockPayload,
  ProductMutationResponse,
  ProductPayload,
  ProductUpdatePayload,
  RestockResponse,
} from "./openapi.generated";
export type {
  FinancialSummaryResponse,
  LedgerEntryResponse,
  PharmacyActivityResponse,
  AccountSessionResponse,
  AccountRegistrationResponse,
  AccountProfileUpdateResponse,
  UserResponse,
  RegisterUserRequest,
  UserProfileUpdate,
  PendingActionsResponse,
  ConfirmedActionResponse,
  CancelledActionResponse,
  PharmacyLoginResponse,
  PharmacyRegistrationResponse,
  PharmacySwitchResponse,
  PharmacyProfileUpdateResponse,
  RegisterPharmacyRequest,
  MyProfileResponse,
  MyProfileUpdateResponse,
  MyActivityResponse,
  PhotoUploadResponse,
  ProfileUpdate,
  HubPharmacyResponse,
  RoleCreate,
  PharmacyCreate,
  CreatePharmacyResponse,
  PharmacySelectionResponse,
  PharmacySummaryResponse,
  AcceptedInvitationResponse,
  PharmacyRoleResponse,
  RolesListResponse,
  RolesOverviewResponse,
  RoleOverviewItem,
  RoleMutationResponse,
  RoleAssignmentResponse,
  StaffRemovalResponse,
  InvitationCreate,
  InvitationCreatedResponse,
  InvitationResponse,
  InvitationRevokedResponse,
  PersonalAuditEntryResponse,
  WorkSummaryResponse,
  StaffShiftResponse,
  ShiftInput,
  ScheduleReplaceResponse,
  StaffCompensationResponse,
  CompensationInput,
  CompensationCreatedResponse,
  ChatResponse,
  PrescriptionRecordResponse,
  PrescriptionReviewResponse,
  PayableResponse,
  PayablesSummaryResponse,
  SettlementCreate,
  SettlementResponse,
} from "./openapi.generated";

export type UserRole = 'owner' | 'pharmacist' | 'cashier' | 'viewer';

export type ActionType =
  | 'log_sale'
  | 'log_expense'
  | 'log_restock'
  | 'create_product'
  | 'update_product'
  | 'create_category'
  | 'create_invite'
  | 'prescription_scan'
  | 'invoice_scan'
  | 'query'
  | 'reduce_stock'
  | 'general_chat';

export type ActionStatus =
  | 'pending_confirmation'
  | 'confirmed'
  | 'cancelled'
  | 'rejected';

export interface ProposedItem {
  id?: number | null;
  item_name: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
  matched_inventory_id?: number | null;
  stock_available?: number | null;
  category?: string | null;
  not_in_inventory?: boolean | null;
  suggestions?: { id: number; name_ar: string; stock_qty: number; unit_sell_price: number }[];
}

export type PharmacyProfile = PharmacyResponse;
export type PharmacyProfileUpdate = PharmacyProfileUpdatePayload;
export type PharmacyStaffMember = PharmacyStaffResponse;

/** Pharmacy membership returned by GET /api/pharmacies for the signed-in person. */
export type MyPharmacy = HubPharmacyResponse;
export type MyPharmaciesResponse = MyPharmaciesResponseSchema;

export type PersonalUser = UserResponse;

export type PharmacyRoleDefinition = PharmacyRoleResponse;
export type PharmacyRolesResponse = RolesListResponse;
/** GET /api/pharmacies/{id}/roles/overview: built-in and custom roles with `grantable` for the caller. */
export type PharmacyRolesOverview = RolesOverviewResponse;
export type PharmacyRoleOverviewItem = RoleOverviewItem;
export type PharmacyInvitationSummary = InvitationResponse;
export type PharmacyInvitationCreated = InvitationCreatedResponse;
export type StaffWorkSummary = WorkSummaryResponse;
export type StaffActivityRecord = PersonalAuditEntryResponse;
export type StaffShiftRecord = StaffShiftResponse;
export type StaffShiftInput = ShiftInput;

export type StaffPayType = 'monthly' | 'hourly' | 'daily' | 'commission' | 'other';

export type StaffCompensationRecord = StaffCompensationResponse;
export type StaffCompensationInput = CompensationInput;

/** Product data of a `create_product` proposal (server: ProductDraftResponse). */
export interface ProductDraft {
  name_ar: string;
  name_en: string;
  unit_buy_price: number;
  unit_sell_price: number;
  stock_qty: number;
  min_threshold: number;
  category?: string | null;
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
  status: ActionStatus;
  created_at: string | null;
  raw_text?: string | null;
  source_image_url?: string | null;
  warnings?: string[];
  product?: ProductDraft | null;
  /** `update_product`: the values now, and the names of the fields the card changes. */
  before?: Record<string, unknown> | null;
  changed_fields?: string[] | null;
  /** `create_category`: the name the card will create. */
  category_name?: string | null;
  /** `reduce_stock`: the count now, the count after the change and the difference. */
  stock_change?: { item_name: string; before: number; after: number; difference: number; reason?: string | null } | null;
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
  source_image_url?: string | null;
}

export interface PrescriptionRecord {
  id: string;
  doctor_name?: string | null;
  patient_name?: string | null;
  image_url?: string | null;
  safety_status: string;
  review_decision?: 'reviewed' | 'held' | null;
  review_notes?: string | null;
  reviewed_by?: number | null;
  reviewed_at?: string | null;
  created_at?: string | null;
  extracted?: Partial<PrescriptionExtraction> | null;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  text: string;
  timestamp: string;
  proposal?: ActionProposal | null;
  prescription?: PrescriptionExtraction | null;
  grounded_data?: Record<string, any> | null;
  isStreaming?: boolean;
}

export type FinancialSummary = FinancialSummaryResponse;

export type InventoryItemSchema = InventoryItemResponse;
export type InventorySummary = InventorySummaryResponse;
export type InventoryPriceHistoryRecord = InventoryPriceHistoryResponse;
export type InventoryBatch = InventoryBatchResponse;
export type InventoryMatch = InventoryMatchResponse;

export type PayableStatus = PayableResponse['status'];
export type SettlementInput = SettlementCreate;

/** One category of the pharmacy with its product count (empty categories included). Matches GET /api/inventory/categories/details. */
export interface CategoryDetail {
  id: number;
  name: string;
  item_count: number;
}

/** Answer of the category write routes (POST, PATCH, DELETE under /api/inventory/categories). */
export interface CategoryMutationResult {
  success: boolean;
  message: string;
  category: CategoryDetail | null;
  affected_items: number;
}