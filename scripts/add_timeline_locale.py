# scripts/add_timeline_locale.py
"""Adds the tl_* texts of the records timeline page (/records/timeline) to the Arabic and
English locale files. Existing keys are never changed. Run from the project root:

    python scripts/add_timeline_locale.py
"""
import json
import pathlib
import sys

AR = {
    "tl_title": "سجل الحركات",
    "tl_tab_all": "الكل",
    "tl_tab_sales": "المبيعات",
    "tl_tab_restocks": "التوريدات",
    "tl_tab_expenses": "المصروفات",
    "tl_tab_payments": "سداد الموردين",
    "tl_tab_new_product": "أصناف جديدة",
    "tl_tab_edit_product": "تعديل الأصناف",
    "tl_kind_log_sale": "عملية بيع",
    "tl_kind_log_restock": "توريد",
    "tl_kind_log_expense": "مصروف",
    "tl_kind_PAY_SUPPLIER": "سداد مورد",
    "tl_kind_CREATE_PRODUCT": "إضافة صنف",
    "tl_kind_UPDATE_PRODUCT": "تعديل صنف",
    "tl_kind_other": "حدث آخر",
    "tl_person": "القائم بالعملية",
    "tl_person_all": "كل الأشخاص",
    "tl_today": "اليوم",
    "tl_yesterday": "أمس",
    "tl_loading": "جارٍ تحميل السجل",
    "tl_empty": "لا توجد حركات في هذه الفترة.",
    "tl_empty_filtered": "لا توجد حركات تطابق الفلاتر المحددة.",
    "tl_clear_filters": "مسح الفلاتر",
    "tl_load_error": "تعذر تحميل سجل الحركات.",
    "tl_retry": "إعادة المحاولة",
    "tl_more": "عرض المزيد",
    "tl_loading_more": "جارٍ التحميل...",
    "tl_more_error": "تعذر تحميل المزيد. حاول مرة أخرى.",
    "tl_limit": "وصلت إلى أقصى عدد من الحركات المعروضة. ضيّق الفترة لرؤية الأقدم.",
    "tl_showing": "المعروض: {count} حركة",
    "tl_denied_title": "لا تملك صلاحية عرض السجل",
    "tl_denied_body": "دورك الحالي لا يسمح بعرض حركات الصيدلية.",
    "tl_show_lines": "عرض التفاصيل",
    "tl_hide_lines": "إخفاء التفاصيل",
    "tl_lines_count": "{count} بند",
    "tl_payment": "طريقة الدفع:",
    "tl_pay_cash": "نقدي",
    "tl_pay_card": "بطاقة",
    "tl_pay_credit": "آجل",
    "tl_notes": "ملاحظات:",
    "tl_col_time": "الوقت",
    "tl_col_type": "النوع",
    "tl_col_person": "القائم بالعملية",
    "tl_col_summary": "الملخص",
    "tl_col_amount": "المبلغ",
    "tl_no_amount": "—",
    "tl_sort_note": "الترتيب يشمل الحركات المحمّلة حتى الآن فقط.",
    "tl_close": "إغلاق",
    "tl_apply": "تطبيق",
}
EN = {
    "tl_title": "Records timeline",
    "tl_tab_all": "All",
    "tl_tab_sales": "Sales",
    "tl_tab_restocks": "Restocks",
    "tl_tab_expenses": "Expenses",
    "tl_tab_payments": "Supplier payments",
    "tl_tab_new_product": "New products",
    "tl_tab_edit_product": "Product edits",
    "tl_kind_log_sale": "Sale",
    "tl_kind_log_restock": "Restock",
    "tl_kind_log_expense": "Expense",
    "tl_kind_PAY_SUPPLIER": "Supplier payment",
    "tl_kind_CREATE_PRODUCT": "Product added",
    "tl_kind_UPDATE_PRODUCT": "Product edited",
    "tl_kind_other": "Other event",
    "tl_person": "Done by",
    "tl_person_all": "Everyone",
    "tl_today": "Today",
    "tl_yesterday": "Yesterday",
    "tl_loading": "Loading the timeline",
    "tl_empty": "No records in this period.",
    "tl_empty_filtered": "No records match the selected filters.",
    "tl_clear_filters": "Clear filters",
    "tl_load_error": "Could not load the records timeline.",
    "tl_retry": "Try again",
    "tl_more": "Show more",
    "tl_loading_more": "Loading...",
    "tl_more_error": "Could not load more. Try again.",
    "tl_limit": "You reached the most records that can be shown. Narrow the date range to see older ones.",
    "tl_showing": "Showing {count} records",
    "tl_denied_title": "You cannot view the records",
    "tl_denied_body": "Your current role does not allow viewing pharmacy records.",
    "tl_show_lines": "Show details",
    "tl_hide_lines": "Hide details",
    "tl_lines_count": "{count} lines",
    "tl_payment": "Payment:",
    "tl_pay_cash": "Cash",
    "tl_pay_card": "Card",
    "tl_pay_credit": "Credit",
    "tl_notes": "Notes:",
    "tl_col_time": "Time",
    "tl_col_type": "Type",
    "tl_col_person": "Done by",
    "tl_col_summary": "Summary",
    "tl_col_amount": "Amount",
    "tl_no_amount": "—",
    "tl_sort_note": "Sorting covers only the records loaded so far.",
    "tl_close": "Close",
    "tl_apply": "Apply",
}


def merge(path: pathlib.Path, extra: dict) -> None:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    added = [k for k in extra if k not in data]
    for key in added:
        data[key] = extra[key]
    indent = 4 if "\n    \"" in raw else 2
    newline = "\r\n" if "\r\n" in raw else "\n"
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    path.write_text(text.replace("\n", newline) + newline, encoding="utf-8", newline="")
    print(f"{path}: added {len(added)} keys, kept {len(extra) - len(added)} existing")


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    found = {}
    for name in ("ar", "en"):
        hits = [p for p in (root / "web").rglob(f"{name}.json") if "node_modules" not in p.parts and "locales" in p.parts]
        if len(hits) != 1:
            sys.exit(f"Expected one locales/{name}.json under web/, found {len(hits)}: {hits}")
        found[name] = hits[0]
    merge(found["ar"], AR)
    merge(found["en"], EN)


if __name__ == "__main__":
    main()