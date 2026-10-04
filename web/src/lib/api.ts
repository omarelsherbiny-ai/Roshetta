// web/src/lib/api.ts (API client with error mapping for the Arabic and English server texts)
import { 
  ActionProposal, 
  ChatMessage, 
  FinancialSummary, 
  CategoryDetail,
  CategoryMutationResult,
  InventoryItemSchema, 
  InventorySummary,
  InventoryPriceHistoryRecord,
  InventoryMatch,
  InventoryBatch,
  ProductMutationResponse,
  ProductPayload,
  ProductUpdatePayload,
  DirectRestockPayload,
  RestockResponse,
  LedgerEntryResponse,
  PharmacyActivityResponse,
  AccountSessionResponse,
  AccountRegistrationResponse,
  AccountProfileUpdateResponse,
  RegisterUserRequest,
  UserProfileUpdate,
  PendingActionsResponse,
  ConfirmedActionResponse,
  CancelledActionResponse,
  ProposedItem,
  PharmacyProfile,
  MyPharmaciesResponse,
  MyPharmacy,
  PharmacyCreate,
  CreatePharmacyResponse,
  PharmacySelectionResponse,
  AcceptedInvitationResponse,
  PharmacySummaryResponse,
  PersonalUser,
  PharmacyStaffMember,
  PharmacyLoginResponse,
  PharmacyRegistrationResponse,
  PharmacySwitchResponse,
  PharmacyProfileUpdateResponse,
  PharmacyProfileUpdate,
  RegisterPharmacyRequest,
  MyProfileResponse,
  MyProfileUpdateResponse,
  MyActivityResponse,
  PhotoUploadResponse,
  ProfileUpdate,
  PharmacyRoleDefinition,
  PharmacyRolesResponse,
  PharmacyRolesOverview,
  RoleCreate,
  RoleMutationResponse,
  RoleAssignmentResponse,
  StaffRemovalResponse,
  PharmacyInvitationSummary,
  PharmacyInvitationCreated,
  InvitationCreate,
  InvitationRevokedResponse,
  StaffWorkSummary,
  StaffActivityRecord,
  StaffShiftRecord,
  StaffShiftInput,
  ScheduleReplaceResponse,
  StaffCompensationRecord,
  StaffCompensationInput,
  CompensationCreatedResponse,
  PrescriptionRecord,
  PrescriptionReviewResponse,
  PayableResponse,
  PayablesSummaryResponse,
  PayableStatus,
  SettlementInput,
} from "@/types";
import { persistLanguage, getStoredLanguage } from '@/lib/i18n';
import { DEFAULT_LANGUAGE } from '@/lib/languages';
import { clearAuth, replaceToken } from '@/lib/auth';
export type { InventoryBatch } from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const ARABIC_API_ERRORS: Record<string, string> = {
  'الاسم ورقم الهاتف واسم الصيدلية مطلوبة للتسجيل.': 'Enter the owner name, phone number, and pharmacy name.',
  'لا توجد صيدلية مرتبطة بهذا الحساب. اقبل دعوة آمنة أو أنشئ صيدلية.': 'No pharmacy is linked to this account. Accept a secure invitation or create a pharmacy.',
  'ليس لديك صلاحية الوصول لهذه الصيدلية.': 'You do not have access to this pharmacy.',
  'هذا المستخدم عضو بالفعل في الصيدلية.': 'This user is already a member of the pharmacy.',
  'الدواء غير موجود في هذه الصيدلية.': 'Product not found in this pharmacy.',
  'الدواء غير موجود في صيدليتك.': 'Product not found in this pharmacy.',
  'الباركود مسجل بالفعل لصنف آخر في صيدليتك.': 'This barcode is already assigned to another product in your pharmacy.',
  'الباركود الجديد مسجل بالفعل لصنف آخر.': 'This barcode is already assigned to another product.',
  'فقط المالك يمكنه دعوة موظفين.': 'Only the owner can invite staff.',
  'فقط المالك يمكنه تغيير الأدوار.': 'Only the owner can change staff roles.',
  'لا يمكن تغيير دور المالك من إدارة الموظفين.': 'Owner roles cannot be changed through staff management.',
  'فقط المالك يمكنه إزالة موظفين.': 'Only the owner can remove staff.',
  'فقط المالك يمكنه تعديل إعدادات الصيدلية.': 'Only the owner can change pharmacy settings.',
  'الموظف غير موجود في هذه الصيدلية.': 'Staff member not found in this pharmacy.',
  'لا يمكن إزالة المالك.': 'The owner cannot be removed.',
  'لا تملك صلاحية عرض قائمة الموظفين.': 'You do not have permission to view the staff list.',
  'لم يتم العثور على ملف الصيدلية.': 'Pharmacy profile not found.',
  'الموظف غير موجود.': 'Staff member not found.',
};

const ENGLISH_API_ERRORS: Record<string, string> = {
  'Current PIN is incorrect.': 'رمز PIN الحالي غير صحيح.',
  'The new PIN must be different from the current PIN.': 'يجب أن يختلف رمز PIN الجديد عن الحالي.',
  'PIN changed.': 'تم تغيير رمز PIN.',
  'Too many attempts. Try again in 15 minutes.': 'محاولات كثيرة. حاول مرة أخرى بعد 15 دقيقة.',
  'This phone number already has an account. Sign in instead.': 'يوجد حساب بالفعل بهذا الرقم. سجّل الدخول بدلاً من ذلك.',
  'An account was created for this phone number. Please join again using its PIN.': 'تم إنشاء حساب لهذا الرقم بالفعل. أعد الانضمام باستخدام رمز PIN الخاص بالحساب.',
  'An account was created for this phone number. Invite the existing account instead.': 'تم إنشاء حساب لهذا الرقم بالفعل. أرسل دعوة إلى الحساب الموجود.',
  'This user is already a member of the pharmacy.': 'هذا المستخدم عضو بالفعل في الصيدلية.',
  'Phone number or PIN is incorrect.': 'رقم الهاتف أو رمز PIN غير صحيح.',
  'Name and phone number are required.': 'الاسم ورقم الهاتف مطلوبان.',
  'This pharmacy membership is inactive.': 'عضويتك في هذه الصيدلية غير مفعّلة.',
  'Authentication required.': 'يجب تسجيل الدخول أولاً.',
  'Invalid authorization header.': 'بيانات التحقق من تسجيل الدخول غير صالحة.',
  'This session has been signed out.': 'تم تسجيل الخروج من هذه الجلسة.',
  'User account is inactive or no longer exists.': 'الحساب غير مفعّل أو لم يعد موجوداً.',
  'User account not found.': 'لم يتم العثور على الحساب الشخصي.',
  'An account can own up to five pharmacies.': 'يمكن للحساب امتلاك خمس صيدليات كحد أقصى.',
  'Invitation is invalid, expired, or already used.': 'الدعوة غير صالحة أو منتهية أو سبق استخدامها.',
  'This account already has a membership in that pharmacy.': 'هذا الحساب عضو بالفعل في هذه الصيدلية.',
  'The invitation role is no longer available.': 'الدور المحدد في الدعوة لم يعد متاحاً.',
  "Return to the pharmacy hub before accepting an invitation.": 'ارجع إلى محور الصيدليات قبل قبول الدعوة.',
  "Pharmacy not found in this account's memberships.": 'الصيدلية غير موجودة ضمن عضويات هذا الحساب.',
  'Pharmacy access is inactive or no longer exists.': 'الوصول إلى الصيدلية غير مفعّل أو لم يعد موجوداً.',
  'Invalid or expired authentication token.': 'رمز تسجيل الدخول غير صالح أو انتهت صلاحيته.',
  'PIN must contain 4 to 6 digits.': 'يجب أن يتكون رمز PIN من 4 إلى 6 أرقام.',
  'Invalid role.': 'الدور المحدد غير صالح.',
  'Invalid staff role.': 'دور الموظف المحدد غير صالح.',
  'Only the pharmacy owner can create a staff account.': 'يقتصر إنشاء حسابات الموظفين على مالك الصيدلية.',
  'Reusable invitation codes are retired. Use a secure invitation link.': 'تم إيقاف رموز الدعوة القابلة لإعادة الاستخدام. استخدم رابط دعوة آمن.',
  'Staff accounts must join using a secure invitation link.': 'يجب على حساب الموظف الانضمام عبر رابط دعوة آمن.',
  'Use the pharmacy-scoped staff role endpoint.': 'استخدم مسار إدارة الدور المرتبط بمعرّف الصيدلية.',
  'Use the pharmacy-scoped staff removal endpoint.': 'استخدم مسار إزالة الموظف المرتبط بمعرّف الصيدلية.',
  'Staff member not found.': 'لم يتم العثور على الموظف.',
  'The ownership limit was reached by another request. Refresh the pharmacy list.': 'وصل الحساب إلى حد الملكية في طلب آخر. حدّث قائمة الصيدليات.',
  'The saved proposal is unreadable.': 'تعذر قراءة الإجراء المحفوظ.',
  'The saved proposal is incomplete.': 'بيانات الإجراء المحفوظ غير مكتملة.',
  'Action proposal not found.': 'لم يتم العثور على الإجراء المقترح.',
  'This action is already being processed.': 'يجري تنفيذ هذا الإجراء بالفعل.',
  'This proposal has expired. Ask the assistant again.': 'انتهت صلاحية هذا الاقتراح. اطلب من المساعد مرة أخرى.',
  'Unsupported action type.': 'نوع الإجراء غير مدعوم.',
  'Your role cannot confirm this action.': 'صلاحيتك لا تسمح بتأكيد هذا الإجراء.',
  'The proposal contains invalid line items.': 'تحتوي تفاصيل الإجراء على أصناف غير صالحة.',
  'The proposal line items cannot be added or removed during confirmation.': 'لا يمكن إضافة أصناف أو حذفها أثناء تأكيد الإجراء.',
  'Unsupported payment method.': 'طريقة الدفع غير مدعومة.',
  'Product names cannot be changed during confirmation.': 'لا يمكن تغيير أسماء الأصناف أثناء تأكيد الإجراء.',
  'Inventory matches cannot be changed during confirmation.': 'لا يمكن تغيير مطابقة المخزون أثناء تأكيد الإجراء.',
  'Match each product to pharmacy inventory before confirming.': 'طابق كل صنف مع مخزون الصيدلية قبل التأكيد.',
  "A proposed product no longer exists in this pharmacy's inventory.": 'لم يعد أحد الأصناف المقترحة موجوداً في مخزون هذه الصيدلية.',
  'The action total must be greater than zero.': 'يجب أن يكون إجمالي الإجراء أكبر من صفر.',
  'Inventory changed during confirmation. Review the proposal again.': 'تغير المخزون أثناء التأكيد. راجع الإجراء المقترح مرة أخرى.',
  'This action has already been confirmed.': 'تم تأكيد هذا الإجراء بالفعل.',
  'Product names cannot be blank.': 'لا يمكن ترك أسماء الأصناف فارغة.',
  'A category with this name already exists.': 'توجد فئة بهذا الاسم بالفعل.',
  'Category not found.': 'الفئة غير موجودة.',
  'Category name cannot be blank.': 'لا يمكن ترك اسم الفئة فارغًا.',
  'Category name is too long.': 'اسم الفئة أطول من الحد المسموح.',
  'The category was created at the same moment by someone else. Try again.': 'تم إنشاء الفئة في نفس اللحظة بواسطة مستخدم آخر. حاول مرة أخرى.',
  'The product could not be saved because of a data conflict.': 'تعذر حفظ الصنف بسبب تعارض في البيانات. حدّث الصفحة ثم حاول مرة أخرى.',
  'Use either a single day or a date range.': 'استخدم يوماً واحداً أو نطاقاً زمنياً، وليس كليهما.',
  'Both start_day and end_day are required for a date range.': 'يجب تحديد تاريخ البداية والنهاية معاً.',
  'The report end date cannot be earlier than its start date.': 'لا يمكن أن يسبق تاريخ النهاية تاريخ البداية.',
  'Could not switch pharmacy.': 'تعذر التبديل إلى الصيدلية.',
  'Prescription not found.': 'لم يتم العثور على الوصفة الطبية.',
  'Prescription data cannot be reviewed because its saved extraction is invalid.': 'تعذر مراجعة الوصفة لأن بيانات الاستخراج المحفوظة غير صالحة.',
  'This prescription has safety alerts. Record it as held while the alerts are unresolved.': 'تحتوي الوصفة على تنبيهات سلامة. سجّلها كموضوعة قيد المتابعة حتى معالجة التنبيهات.',
  'Image not found.': 'لم يتم العثور على الصورة.',
  'Image file is unavailable.': 'ملف الصورة غير متاح.',
  'Unsupported document type.': 'نوع المستند غير مدعوم.',
  'Your role cannot access this document.': 'صلاحيتك لا تسمح بالوصول إلى هذا المستند.',
  'Document extraction is unavailable because no OCR provider adapter is configured.': 'استخراج المستندات غير متاح لعدم إعداد مزود OCR.',
  'The assigned pharmacy role is no longer active.': 'الدور المعيّن في الصيدلية لم يعد مفعّلاً.',
  'Select a pharmacy before using this operation.': 'اختر صيدلية قبل استخدام هذه العملية.',
  'Pharmacy not found.': 'لم يتم العثور على الصيدلية.',
  'Pharmacy not found in the selected workspace.': 'لم يتم العثور على الصيدلية في مساحة العمل المحددة.',
  'Only the pharmacy owner can manage custom roles and compensation.': 'يقتصر إنشاء الأدوار المخصصة وإدارة التعويضات على مالك الصيدلية.',
  'You cannot manage pharmacy invitations.': 'لا تملك صلاحية إدارة دعوات الصيدلية.',
  'Active staff member not found.': 'لم يتم العثور على موظف نشط.',
  'The protected owner role cannot be created as a custom role.': 'لا يمكن إنشاء دور مخصص باسم دور المالك المحمي.',
  'A role with this name already exists in the pharmacy.': 'يوجد دور بهذا الاسم بالفعل في الصيدلية.',
  'Role not found.': 'لم يتم العثور على الدور.',
  'The protected owner role cannot be renamed.': 'لا يمكن تغيير اسم دور المالك المحمي.',
  'Reassign active staff before removing this role.': 'أعد تعيين الموظفين النشطين قبل تعطيل هذا الدور.',
  'The protected owner membership cannot be reassigned.': 'لا يمكن إعادة تعيين عضوية المالك المحمية.',
  'Active custom role not found in this pharmacy.': 'لم يتم العثور على دور مخصص نشط في هذه الصيدلية.',
  'Only the pharmacy owner can invite members with a custom role.': 'يقتصر إرسال دعوات الأدوار المخصصة على مالك الصيدلية.',
  'Invitation not found.': 'لم يتم العثور على الدعوة.',
  'You cannot view another staff member\'s work summary.': 'لا تملك صلاحية عرض ملخص عمل موظف آخر.',
  'You cannot view this staff schedule.': 'لا تملك صلاحية عرض جدول هذا الموظف.',
  'Owner availability is managed outside staff shifts.': 'يُدار توافر المالك خارج جداول الموظفين.',
  'Compensation details are private to the employee and owner.': 'تفاصيل التعويضات خاصة بالموظف ومالك الصيدلية.',
  'Owner compensation is not managed as staff payroll.': 'لا تُدار تعويضات المالك ضمن رواتب الموظفين.',
  'Product not found in this pharmacy.': 'لم يتم العثور على الصنف في هذه الصيدلية.',
  'Stock quantity can only change through a confirmed stock movement.': 'لا يمكن تغيير كمية المخزون إلا من خلال حركة مخزون مؤكدة.',
  'birth_date must be YYYY-MM-DD.': 'يجب إدخال تاريخ الميلاد بالصيغة سنة-شهر-يوم.',
  'Use a JPEG, PNG, or WebP profile image.': 'استخدم صورة شخصية بصيغة JPEG أو PNG أو WebP.',
  'Profile image must be 5 MB or smaller.': 'يجب ألا يتجاوز حجم الصورة الشخصية 5 ميغابايت.',
  'The image content does not match its declared type.': 'محتوى الصورة لا يطابق نوع الملف المعلن.',
  'Profile image not found.': 'لم يتم العثور على الصورة الشخصية.',
  'Not a member of that pharmacy.': 'أنت لست عضواً في هذه الصيدلية.',
  'Your role cannot cancel this action.': 'صلاحيتك لا تسمح بإلغاء هذا الإجراء.',
  'The action is already being processed.': 'يجري تنفيذ هذا الإجراء بالفعل.',
  'Credit restock not found in this pharmacy.': 'لم يتم العثور على توريد آجل في هذه الصيدلية.',
  'The payment amount must be at least 0.01.': 'يجب ألا يقل مبلغ الدفعة عن 0.01.',
  'This restock is already fully paid.': 'تم سداد هذا التوريد بالكامل.',
  'The payment exceeds the remaining balance of this restock.': 'مبلغ الدفعة أكبر من المتبقي على هذا التوريد.',
};

const ARABIC_ROLE_NAMES: Record<string, string> = {
  owner: 'المالك', pharmacist: 'الصيدلاني', cashier: 'الكاشير', viewer: 'المراقب',
};

const ARABIC_PERMISSION_NAMES: Record<string, string> = {
  log_sale: 'تسجيل المبيعات',
  log_expense: 'تسجيل المصروفات',
  log_restock: 'تسجيل التوريد',
  view_reports: 'عرض التقارير',
  view_inventory: 'عرض المخزون',
  manage_inventory: 'إدارة المخزون',
  manage_staff: 'إدارة الموظفين',
  view_audit: 'عرض سجل التدقيق',
  view_staff_activity: 'عرض نشاط الموظفين',
  edit_settings: 'تعديل إعدادات الصيدلية',
  scan_prescription: 'مراجعة الوصفات الطبية',
  manage_roles: 'إدارة الأدوار',
  manage_schedule: 'إدارة الجداول',
  manage_compensation: 'إدارة التعويضات',
  manage_payables: 'تسجيل مدفوعات الموردين',
};

const VALIDATION_FIELDS: Record<string, { ar: string; en: string }> = {
  name: { ar: 'الاسم', en: 'name' },
  owner_name: { ar: 'اسم المالك', en: 'owner name' },
  pharmacy_name: { ar: 'اسم الصيدلية', en: 'pharmacy name' },
  phone: { ar: 'رقم الهاتف', en: 'phone number' },
  pin: { ar: 'رمز PIN', en: 'PIN' },
  name_ar: { ar: 'اسم الدواء بالعربية', en: 'Arabic product name' },
  name_en: { ar: 'اسم الدواء بالإنجليزية', en: 'English product name' },
  barcode: { ar: 'الباركود', en: 'barcode' },
  active_ingredient: { ar: 'المادة الفعالة', en: 'active ingredient' },
  category: { ar: 'الفئة', en: 'category' },
  stock_qty: { ar: 'كمية المخزون', en: 'stock quantity' },
  min_threshold: { ar: 'حد التنبيه للمخزون', en: 'low-stock threshold' },
  unit_buy_price: { ar: 'سعر الشراء', en: 'purchase price' },
  unit_sell_price: { ar: 'سعر البيع', en: 'selling price' },
  expiry_date: { ar: 'تاريخ الصلاحية', en: 'expiry date' },
  address: { ar: 'العنوان', en: 'address' },
  license_number: { ar: 'رقم الترخيص', en: 'license number' },
  tax_id: { ar: 'الرقم الضريبي', en: 'tax ID' },
  role: { ar: 'الدور الوظيفي', en: 'staff role' },
  pharmacy_id: { ar: 'الصيدلية', en: 'pharmacy' },
  amount: { ar: 'مبلغ الدفعة', en: 'payment amount' },
  payment_method: { ar: 'طريقة الدفع', en: 'payment method' },
  supplier_name: { ar: 'اسم المورد', en: 'supplier name' },
  supplier_notes: { ar: 'ملاحظات المورد', en: 'supplier notes' },
};

/**
 * The server's error texts and the chat endpoint exist only in Arabic and English.
 * Every other registry language gets the English texts until the server sends error codes
 * and the client translates them (Next task c, flag). This is the one place that decides it.
 */
type ServerLanguage = 'ar' | 'en';

function serverLanguageOf(code: string): ServerLanguage {
  return code === 'ar' ? 'ar' : 'en';
}

function formatValidationErrors(detail: unknown, language: ServerLanguage): string | undefined {
  if (!Array.isArray(detail) || detail.length === 0) return undefined;
  const messages = detail.flatMap((error) => {
    if (!error || typeof error !== 'object') return [];
    const issue = error as { loc?: unknown[]; type?: unknown };
    const field = Array.isArray(issue.loc)
      ? [...issue.loc].reverse().find((part) => typeof part === 'string' && part !== 'body' && part !== 'query' && part !== 'path') as string | undefined
      : undefined;
    const fieldName = field ? VALIDATION_FIELDS[field]?.[language] : undefined;
    const label = fieldName ?? (language === 'ar' ? 'أحد الحقول' : 'a field');
    const type = typeof issue.type === 'string' ? issue.type : '';
    if (language === 'ar') {
      if (type === 'missing') return [`حقل ${label} مطلوب.`];
      if (type === 'string_too_short') return [`قيمة ${label} أقصر من الحد المسموح.`];
      if (type === 'string_too_long') return [`قيمة ${label} أطول من الحد المسموح.`];
      if (type.startsWith('greater_than') || type.startsWith('less_than')) return [`قيمة ${label} خارج النطاق المسموح.`];
      if (type.endsWith('_parsing')) return [`أدخل قيمة صحيحة في حقل ${label}.`];
      return [`تحقق من قيمة حقل ${label}.`];
    }
    if (type === 'missing') return [`${label} is required.`];
    if (type === 'string_too_short') return [`${label} is shorter than allowed.`];
    if (type === 'string_too_long') return [`${label} is longer than allowed.`];
    if (type.startsWith('greater_than') || type.startsWith('less_than')) return [`${label} is outside the allowed range.`];
    if (type.endsWith('_parsing')) return [`Enter a valid value for ${label}.`];
    return [`Check the value for ${label}.`];
  });
  return messages.length ? messages.join(language === 'ar' ? ' ' : ' ') : undefined;
}

function translateDynamicEnglishError(message: string): string | undefined {
  const status = message.match(/^Action is already (processing|confirmed|cancelled)\.$/);
  if (status) {
    const statusLabel = { processing: 'قيد التنفيذ', confirmed: 'مؤكد', cancelled: 'ملغي' }[status[1] as 'processing' | 'confirmed' | 'cancelled'];
    return `حالة هذا الإجراء: ${statusLabel}.`;
  }
  const stock = message.match(/^Insufficient stock for (.+)\.$/);
  if (stock) return `الكمية المتاحة غير كافية للصنف ${stock[1]}.`;
  const permission = message.match(/^Current role \(([^)]+)\) cannot perform this operation \(([^)]+)\)\.$/);
  if (permission) {
    const role = ARABIC_ROLE_NAMES[permission[1]] ?? permission[1];
    const permissionName = ARABIC_PERMISSION_NAMES[permission[2]] ?? permission[2];
    return `صلاحية ${role} لا تسمح بتنفيذ هذه العملية (${permissionName}).`;
  }
}

function apiErrorMessage(detail: unknown, fallbackEnglish: string, fallbackArabic?: string): string {
  const message = typeof detail === 'string' ? detail : '';
  const language = serverLanguageOf(getStoredLanguage());
  const validationMessage = formatValidationErrors(detail, language);
  if (validationMessage) return validationMessage;
  if (language === 'ar') {
    if (!message) return fallbackArabic ?? 'تعذر إكمال الطلب.';
    const translated = ENGLISH_API_ERRORS[message] ?? translateDynamicEnglishError(message);
    if (translated) return translated;
    return /[\u0600-\u06FF]/.test(message) ? message : fallbackArabic ?? 'تعذر إكمال الطلب.';
  }
  if (!message) return fallbackEnglish;
  if (ARABIC_API_ERRORS[message]) return ARABIC_API_ERRORS[message];
  return /[\u0600-\u06FF]/.test(message) ? fallbackEnglish : message;
}

/** Returns the Authorization header from sessionStorage if a token is stored. */
export function getAuthHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem('roshetta_token') : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Calls where a 401 means "wrong credentials" or is handled by the caller, not "this session is dead". */
const SESSION_NEUTRAL_PATHS = [
  '/api/auth/login',
  '/api/auth/account-login',
  '/api/auth/register-user',
  '/api/auth/register-pharmacy',
  '/api/auth/logout',
];

let sessionEnding = false;

/**
 * fetch for every API call. A 401 on a signed-in call means the saved token expired, was revoked or is
 * invalid: the saved session is cleared and the person goes to the sign-in page (/onboarding) instead of
 * staying on a page full of "not authorized" errors. A pending invitation token is kept so the person can
 * finish accepting it after signing in. After the redirect starts the returned promise never settles, so
 * the calling page does not flash an error or clear anything on its way out. 403 (no permission) is untouched.
 */
async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, init);
  if (res.status !== 401 || typeof window === 'undefined') return res;
  if (SESSION_NEUTRAL_PATHS.some((path) => input.includes(path))) return res;

  const stored = sessionStorage.getItem('roshetta_token');
  const sent = new Headers(init?.headers).get('Authorization');
  // A call made with some other token than the saved one (for example switch-pharmacy) is the caller's business.
  if (sent && stored && sent !== `Bearer ${stored}`) return res;

  if (!sessionEnding) {
    sessionEnding = true;
    clearAuth();
    if (!window.location.pathname.startsWith('/onboarding')) {
      window.location.replace('/onboarding');
    } else {
      sessionEnding = false;
      return res;
    }
  }
  return new Promise<Response>(() => {});
}

export async function logoutSession(): Promise<void> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/logout`, {
    method: 'POST',
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err.detail, 'Could not revoke this session.', 'تعذر إنهاء الجلسة على الخادم.'));
  }
}

export async function returnToAccountScope(): Promise<AccountSessionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/account-scope`, {
    method: 'POST',
    headers: { ...getAuthHeader() },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not return to My Pharmacies.', 'تعذر الرجوع إلى محور صيدلياتي'));
  return data;
}

export async function loginPharmacist(phone: string, pin: string, pharmacyId?: number): Promise<PharmacyLoginResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, pin, pharmacy_id: pharmacyId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err.detail, 'Sign-in failed.', 'فشل تسجيل الدخول'));
  }
  return res.json();
}

/** Create a personal account without creating or selecting a pharmacy. */
export async function registerPersonalAccount(payload: RegisterUserRequest): Promise<AccountRegistrationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/register-user`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Account registration failed.', 'فشل إنشاء الحساب الشخصي'));
  return data;
}

/** Sign in to the personal account scope, independent of pharmacy membership. */
export async function loginPersonalAccount(phone: string, pin: string): Promise<AccountSessionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/account-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, pin }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Sign-in failed.', 'فشل تسجيل الدخول'));
  return data;
}

export type PinChangeFailure = 'wrong_pin' | 'throttled' | 'network' | 'other';

/** A failed PIN change. `failure` tells the page what to show; a wrong current PIN (403) is a plain message, never a dead session. */
export class PinChangeError extends Error {
  readonly failure: PinChangeFailure;
  constructor(failure: PinChangeFailure, message: string) {
    super(message);
    this.name = 'PinChangeError';
    this.failure = failure;
  }
}

export interface ChangePinResult {
  success: boolean;
  message: string;
  token: string;
}

/**
 * POST /api/auth/change-pin. The server revokes the session used for the call and returns a fresh
 * token with the same scope: it is saved here, so this device stays signed in (every other device is signed out).
 */
export async function changePin(currentPin: string, newPin: string): Promise<ChangePinResult> {
  let res: Response;
  try {
    res = await apiFetch(`${API_BASE_URL}/api/auth/change-pin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
      body: JSON.stringify({ current_pin: currentPin, new_pin: newPin }),
    });
  } catch {
    throw new PinChangeError('network', 'Could not reach the server.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const failure: PinChangeFailure = res.status === 403 ? 'wrong_pin' : res.status === 429 ? 'throttled' : 'other';
    throw new PinChangeError(failure, apiErrorMessage(data.detail, 'Could not change your PIN.', 'تعذر تغيير رمز PIN.'));
  }
  if (typeof data.token === 'string' && data.token) replaceToken(data.token);
  return data;
}

export async function getPersonalAccount(): Promise<PersonalUser> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/me`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load your account.', 'تعذر تحميل بيانات الحساب'));
  return data;
}

export async function updatePersonalAccount(payload: UserProfileUpdate): Promise<AccountProfileUpdateResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/me`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not update your account.', 'تعذر تحديث بيانات الحساب'));
  if (payload.language_pref) persistLanguage(payload.language_pref);
  return data;
}

/** Load real owned and joined memberships for the signed-in account. */
export async function getMyPharmacies(): Promise<MyPharmaciesResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load pharmacies.', 'تعذر تحميل الصيدليات'));
  return data;
}

/** Create an owned pharmacy using the backend-enforced five-pharmacy cap. */
export async function createMyPharmacy(payload: PharmacyCreate): Promise<CreatePharmacyResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not create the pharmacy.', 'تعذر إنشاء الصيدلية'));
  return data;
}

/** Select a pharmacy membership; the backend issues a pharmacy-scoped token. */
export async function selectMyPharmacy(pharmacyId: number): Promise<PharmacySelectionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/select`, {
    method: 'POST',
    headers: { ...getAuthHeader() },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not open this pharmacy.', 'تعذر فتح الصيدلية'));
  return data;
}

/** The server answered and refused the invitation (expired, used up, revoked, wrong session...). A dropped connection is a plain Error instead. */
export class InvitationRefusedError extends Error {}

/** Accept an owner-issued invitation while using an account-scoped session. */
export async function acceptPharmacyInvitation(token: string): Promise<AcceptedInvitationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/invitations/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify({ token: token.trim() }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new InvitationRefusedError(apiErrorMessage(data.detail, 'Could not accept the invitation.', 'تعذر قبول الدعوة'));
  return data;
}

export async function switchPharmacy(pharmacyId: number, accessToken: string): Promise<PharmacySwitchResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/switch-pharmacy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ pharmacy_id: pharmacyId }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not switch pharmacy.', 'تعذر التبديل إلى الصيدلية.'));
  return data;
}

export async function registerPharmacy(payload: RegisterPharmacyRequest): Promise<PharmacyRegistrationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/register-pharmacy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err.detail, 'Pharmacy registration failed.', 'فشل تسجيل الصيدلية الجديدة'));
  }
  return res.json();
}

export async function getPharmacyProfile(): Promise<PharmacyProfile> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/profile`, {
    headers: { ...getAuthHeader() },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load the pharmacy profile.', 'فشل جلب بيانات الصيدلية'));
  return data;
}

export async function updatePharmacyProfile(profile: PharmacyProfileUpdate): Promise<PharmacyProfileUpdateResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(profile),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not update settings.', 'فشل تحديث الإعدادات'));
  return data;
}

export async function sendChatMessage(text: string, contextId: string = "default", language: string = DEFAULT_LANGUAGE): Promise<ChatMessage> {
  const res = await apiFetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader()
    },
    body: JSON.stringify({
      text,
      context_id: contextId,
      language: serverLanguageOf(language)
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(errorData.detail, `Request failed (${res.status}).`, 'تعذر إكمال الطلب.'));
  }

  return res.json();
}

export async function uploadAndScanDocument(
  file: File,
  docType: 'prescription' | 'invoice' | 'receipt' = 'receipt'
): Promise<ChatMessage> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_type', docType);

  const res = await apiFetch(`${API_BASE_URL}/api/ocr/scan`, {
    method: 'POST',
    headers: { ...getAuthHeader() },
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(errorData.detail, `Document scan failed (${res.status}).`, 'تعذر مسح المستند.'));
  }

  return res.json();
}

export async function getPrescriptionsList(): Promise<PrescriptionRecord[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/ocr/prescriptions`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) throw new Error(apiErrorMessage(undefined, 'Could not load prescriptions.', 'فشل جلب قائمة الروشتات'));
  return res.json();
}

export async function reviewPrescription(
  prescriptionId: string,
  decision: 'reviewed' | 'held',
  notes?: string,
): Promise<PrescriptionReviewResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/ocr/prescriptions/${encodeURIComponent(prescriptionId)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify({ decision, notes }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, `Prescription review failed (${res.status}).`, 'تعذرت مراجعة الوصفة.'));
  return data;
}

export async function confirmActionProposal(
  actionId: string,
  editedItems?: ProposedItem[],
  notes?: string
): Promise<ConfirmedActionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/actions/${actionId}/confirm`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader()
    },
    body: JSON.stringify({
      edited_items: editedItems,
      notes,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(errorData.detail, `Confirmation failed (${res.status}).`, 'تعذر تأكيد العملية.'));
  }

  return res.json();
}

export async function cancelActionProposal(
  actionId: string
): Promise<CancelledActionResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/actions/${actionId}/cancel`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader()
    },
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(errorData.detail, `Cancellation failed (${res.status}).`, 'تعذر إلغاء العملية.'));
  }

  return res.json();
}

export async function getPendingActionProposals(): Promise<PendingActionsResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/actions/pending`, {
    headers: { ...getAuthHeader() },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(apiErrorMessage(data.detail, 'Could not load pending actions.', 'تعذر تحميل العمليات التي تنتظر التأكيد.'));
  }
  return data;
}

export async function getFinancialSummary(day?: string, startDay?: string, endDay?: string): Promise<FinancialSummary> {
  const params = new URLSearchParams();
  if (day) params.set('day', day);
  if (startDay) params.set('start_day', startDay);
  if (endDay) params.set('end_day', endDay);
  const query = params.toString();
  const res = await apiFetch(`${API_BASE_URL}/api/ledger/daily-summary${query ? `?${query}` : ''}`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) {
    throw new Error(apiErrorMessage(undefined, `Could not load the financial summary (${res.status}).`, 'تعذر تحميل الملخص المالي.'));
  }
  return res.json();
}

export async function getInventoryItems(search?: string, category?: string): Promise<InventoryItemSchema[]> {
  const params = new URLSearchParams();
  if (search) params.append('search', search);
  if (category) params.append('category', category);

  const res = await apiFetch(`${API_BASE_URL}/api/inventory/items?${params.toString()}`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) throw new Error(apiErrorMessage(undefined, 'Could not load inventory.', 'فشل جلب قائمة الأدوية'));
  return res.json();
}

export async function getInventorySummary(): Promise<InventorySummary> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/summary`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load the inventory summary.', 'تعذر تحميل ملخص المخزون'));
  return data;
}

export async function getInventoryCategories(): Promise<string[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/categories`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load inventory categories.', 'تعذر تحميل فئات المخزون'));
  return data;
}

export async function getInventoryItem(itemId: number): Promise<InventoryItemSchema> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/items/${itemId}`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) throw new Error(apiErrorMessage(undefined, 'Could not load the product.', 'فشل جلب بيانات الدواء'));
  return res.json();
}

/** Aliases for consistent naming */
export const getInventory = getInventoryItems;
export const getProduct = getInventoryItem;


export async function getInventoryPriceHistory(itemId: number): Promise<InventoryPriceHistoryRecord[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/items/${itemId}/price-history`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load price history.', 'تعذر تحميل سجل الأسعار'));
  return data;
}

export async function getLowStockItems(): Promise<InventoryItemSchema[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/low-stock`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) {
    throw new Error(apiErrorMessage(undefined, `Could not load inventory (${res.status}).`, 'فشل جلب قائمة الأدوية'));
  }
  return res.json();
}

export async function createNewProduct(product: ProductPayload): Promise<ProductMutationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(product),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err.detail, 'Could not add the product.', 'فشل إضافة الدواء الجديد'));
  }

  return res.json();
}

export async function updateProduct(itemId: number, product: ProductUpdatePayload): Promise<ProductMutationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/items/${itemId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(product),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err.detail, 'Could not update the product.', 'فشل تعديل بيانات الدواء'));
  }

  return res.json();
}

/** Lists categories with their product counts, including categories that have no product. */
export async function getCategoryDetails(): Promise<CategoryDetail[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/categories/details`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load inventory categories.', 'تعذر تحميل فئات المخزون'));
  return data;
}

/** Creates a category on its own, without any product (POST). */
export async function createCategory(name: string): Promise<CategoryMutationResult> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify({ name }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err.detail, 'Could not save the category.', 'تعذر حفظ الفئة.'));
  }

  return res.json();
}

/** Sets only the category of one product (PATCH). Creates the category when it does not exist yet. */
export async function setItemCategory(itemId: number, category: string): Promise<ProductMutationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/items/${itemId}/category`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify({ category }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err.detail, 'Could not save the category.', 'تعذر حفظ الفئة.'));
  }

  return res.json();
}

export async function matchProduct(queryName: string): Promise<InventoryMatch> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify({ query_name: queryName }),
  });
  if (!res.ok) throw new Error(apiErrorMessage(undefined, 'Could not match the product.', 'فشل فحص الصنف'));
  return res.json();
}

export type LedgerEntryTypeFilter = 'log_sale' | 'log_expense' | 'log_restock';

export async function getRecentEntries(
  limit: number = 20,
  day?: string,
  startDay?: string,
  endDay?: string,
  options?: { offset?: number; entryType?: LedgerEntryTypeFilter },
): Promise<LedgerEntryResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (day) params.set('day', day);
  if (startDay) params.set('start_day', startDay);
  if (endDay) params.set('end_day', endDay);
  if (options?.offset) params.set('offset', String(options.offset));
  if (options?.entryType) params.set('entry_type', options.entryType);
  const res = await apiFetch(`${API_BASE_URL}/api/ledger/entries?${params.toString()}`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) throw new Error(apiErrorMessage(undefined, 'Could not load recent transactions.', 'فشل جلب الحركات الأخيرة'));
  return res.json();
}

export async function getRecentActivity(limit: number = 20): Promise<PharmacyActivityResponse[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/ledger/activity?limit=${limit}`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) throw new Error(apiErrorMessage(undefined, `Could not load pharmacy activity (${res.status}).`, 'تعذر تحميل نشاط الصيدلية.'));
  return res.json();
}

export async function getStaffList(): Promise<PharmacyStaffMember[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/auth/staff`, {
    headers: { ...getAuthHeader() },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(err.detail, 'Could not load staff.', 'فشل جلب قائمة الموظفين'));
  }
  return res.json();
}

export async function getPharmacyRoles(pharmacyId: number): Promise<PharmacyRolesResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/roles`, { headers: { ...getAuthHeader() }, cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load pharmacy roles.', 'تعذر تحميل أدوار الصيدلية'));
  return data;
}

export async function getPharmacyRolesOverview(pharmacyId: number): Promise<PharmacyRolesOverview> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/roles/overview`, { headers: { ...getAuthHeader() }, cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load pharmacy roles.', 'تعذر تحميل أدوار الصيدلية'));
  return data;
}

export async function createPharmacyRole(pharmacyId: number, payload: RoleCreate): Promise<RoleMutationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/roles`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...getAuthHeader() }, body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not create the role.', 'تعذر إنشاء الدور'));
  return data;
}

export async function updatePharmacyRole(pharmacyId: number, roleId: number, payload: RoleCreate): Promise<RoleMutationResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/roles/${roleId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json', ...getAuthHeader() }, body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not update the role.', 'تعذر تحديث الدور'));
  return data;
}

export async function deactivatePharmacyRole(pharmacyId: number, roleId: number): Promise<InvitationRevokedResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/roles/${roleId}`, { method: 'DELETE', headers: { ...getAuthHeader() } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not remove the role.', 'تعذر إيقاف الدور'));
  return data;
}

export async function assignPharmacyRole(pharmacyId: number, userId: number, customRoleId: number): Promise<RoleAssignmentResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/staff/${userId}/role`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json', ...getAuthHeader() }, body: JSON.stringify({ custom_role_id: customRoleId }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not assign the role.', 'تعذر إسناد الدور'));
  return data;
}

export async function assignPharmacyFixedRole(pharmacyId: number, userId: number, role: 'pharmacist' | 'cashier' | 'viewer'): Promise<RoleAssignmentResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/staff/${userId}/role`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json', ...getAuthHeader() }, body: JSON.stringify({ role }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not assign the role.', 'تعذر إسناد الدور'));
  return data;
}

export async function removePharmacyStaff(pharmacyId: number, userId: number): Promise<StaffRemovalResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/staff/${userId}`, {
    method: 'DELETE', headers: { ...getAuthHeader() },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not remove the staff member.', 'تعذر إيقاف وصول الموظف'));
  return data;
}

export async function createPharmacyInvitation(pharmacyId: number, payload: InvitationCreate): Promise<PharmacyInvitationCreated> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/invitations`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...getAuthHeader() }, body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not create the invitation.', 'تعذر إنشاء رابط الدعوة'));
  return data;
}

export async function getPharmacyInvitations(pharmacyId: number): Promise<PharmacyInvitationSummary[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/invitations`, { headers: { ...getAuthHeader() }, cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load invitations.', 'تعذر تحميل روابط الدعوة'));
  return data;
}

export async function revokePharmacyInvitation(pharmacyId: number, invitationId: number): Promise<InvitationRevokedResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/invitations/${invitationId}`, { method: 'DELETE', headers: { ...getAuthHeader() } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not revoke the invitation.', 'تعذر إلغاء رابط الدعوة'));
  return data;
}

export async function getMyStaffActivity(limit = 50): Promise<StaffActivityRecord[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/staff/me/activity?limit=${encodeURIComponent(limit)}`, { headers: { ...getAuthHeader() }, cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load your activity.', 'تعذر تحميل سجل نشاطك'));
  return data;
}

export async function getMyWorkSummary(days = 7): Promise<StaffWorkSummary> {
  const res = await apiFetch(`${API_BASE_URL}/api/staff/me/summary?days=${encodeURIComponent(days)}`, { headers: { ...getAuthHeader() }, cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load your work summary.', 'تعذر تحميل ملخص عملك'));
  return data;
}

export async function getStaffWorkSummary(pharmacyId: number, userId: number, days = 7): Promise<StaffWorkSummary> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/staff/${userId}/summary?days=${encodeURIComponent(days)}`, { headers: { ...getAuthHeader() }, cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load the staff summary.', 'تعذر تحميل ملخص الموظف'));
  return data;
}

export async function getStaffSchedule(pharmacyId: number, userId: number): Promise<StaffShiftRecord[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/staff/${userId}/schedule`, { headers: { ...getAuthHeader() }, cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load the work schedule.', 'تعذر تحميل جدول الورديات'));
  return data;
}

export async function replaceStaffSchedule(pharmacyId: number, userId: number, shifts: StaffShiftInput[]): Promise<ScheduleReplaceResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/staff/${userId}/schedule`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json', ...getAuthHeader() }, body: JSON.stringify({ shifts }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not save the work schedule.', 'تعذر حفظ جدول الورديات'));
  return data;
}

export async function getStaffCompensation(pharmacyId: number, userId: number): Promise<StaffCompensationRecord[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/staff/${userId}/compensation`, { headers: { ...getAuthHeader() }, cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load compensation settings.', 'تعذر تحميل إعدادات الأجر'));
  return data;
}

export async function addStaffCompensation(pharmacyId: number, userId: number, payload: StaffCompensationInput): Promise<CompensationCreatedResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/staff/${userId}/compensation`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...getAuthHeader() }, body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not save compensation settings.', 'تعذر حفظ إعدادات الأجر'));
  return data;
}

/** GET /api/pharmacies/{id}/summary — member count, product count, today revenue, low-stock */
export async function getPharmacySummary(pharmacyId: number): Promise<PharmacySummaryResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/pharmacies/${pharmacyId}/summary`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load pharmacy summary.', 'تعذر تحميل ملخص الصيدلية'));
  return data;
}

/** GET /api/me/activity — per-user sales/expenses/items summary */
export async function getMyActivity(pharmacyId?: number, period: 'day' | 'week' | 'month' | 'all' = 'day'): Promise<MyActivityResponse> {
  const params = new URLSearchParams({ period });
  if (pharmacyId) params.set('pharmacy_id', String(pharmacyId));
  const res = await apiFetch(`${API_BASE_URL}/api/me/activity?${params}`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load activity.', 'تعذر تحميل سجل النشاط'));
  return data;
}

/** GET /api/me — full user profile */
export async function getMyProfile(): Promise<MyProfileResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/me`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load profile.', 'تعذر تحميل الملف الشخصي'));
  return data;
}

/** PATCH /api/me — update editable profile fields */
export async function updateMyProfile(payload: ProfileUpdate): Promise<MyProfileUpdateResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/me`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not update profile.', 'تعذر تحديث الملف الشخصي'));
  return data;
}

/** POST /api/me/photo — upload profile photo */
export async function uploadMyPhoto(file: File): Promise<PhotoUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiFetch(`${API_BASE_URL}/api/me/photo`, {
    method: 'POST',
    headers: { ...getAuthHeader() },
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not upload photo.', 'تعذر رفع الصورة'));
  return data;
}

/** Load the authenticated user's private profile photo as a browser object URL. */
export async function loadMyPhotoObjectUrl(photoPath: string): Promise<string> {
  if (!photoPath.startsWith('/api/me/photo/')) throw new Error('Invalid profile photo path.');
  const res = await apiFetch(`${API_BASE_URL}${photoPath}`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(apiErrorMessage(data.detail, 'Could not load profile photo.', 'تعذر تحميل الصورة الشخصية'));
  }
  return URL.createObjectURL(await res.blob());
}

/** POST /api/inventory/items/{id}/restock — direct intake */
export async function restockProduct(
  itemId: number,
  payload: DirectRestockPayload
): Promise<RestockResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/items/${itemId}/restock`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Failed to restock item.', 'تعذر توريد الصنف'));
  return data;
}

/** GET /api/inventory/items/{id}/batches */
export async function getItemBatches(itemId: number): Promise<InventoryBatch[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/inventory/items/${itemId}/batches`, {
    headers: { ...getAuthHeader() },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Failed to load item batches.', 'تعذر تحميل دفعات الصنف'));
  return data;
}

/** GET /api/ledger/payables: credit restocks with paid and remaining amounts (newest first). */
export async function getPayables(
  options?: { limit?: number; offset?: number; status?: PayableStatus; startDay?: string; endDay?: string },
): Promise<PayableResponse[]> {
  const params = new URLSearchParams({ limit: String(options?.limit ?? 20) });
  if (options?.offset) params.set('offset', String(options.offset));
  if (options?.status) params.set('status', options.status);
  if (options?.startDay) params.set('start_day', options.startDay);
  if (options?.endDay) params.set('end_day', options.endDay);
  const res = await apiFetch(`${API_BASE_URL}/api/ledger/payables?${params.toString()}`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load supplier payables.', 'تعذر تحميل مستحقات الموردين'));
  return data;
}

/** GET /api/ledger/payables/summary: total still owed and counts per status. */
export async function getPayablesSummary(startDay?: string, endDay?: string): Promise<PayablesSummaryResponse> {
  const params = new URLSearchParams();
  if (startDay) params.set('start_day', startDay);
  if (endDay) params.set('end_day', endDay);
  const query = params.toString();
  const res = await apiFetch(`${API_BASE_URL}/api/ledger/payables/summary${query ? `?${query}` : ''}`, {
    headers: { ...getAuthHeader() },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not load the payables summary.', 'تعذر تحميل ملخص المستحقات'));
  return data;
}

/** POST /api/ledger/entries/{id}/settlements: pay a supplier against one credit restock (payer = signed-in user). */
export async function recordSettlement(entryId: string, payload: SettlementInput): Promise<PayableResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/ledger/entries/${encodeURIComponent(entryId)}/settlements`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify({ amount: payload.amount, payment_method: payload.payment_method }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail, 'Could not record the payment.', 'تعذر تسجيل الدفعة'));
  return data;
}