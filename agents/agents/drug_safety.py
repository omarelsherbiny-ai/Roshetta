from typing import List, Dict, Any
from agents.state import AgentState


def drug_safety_agent(state: AgentState) -> AgentState:
    """
    Drug Interaction & Safety Agent.
    Cross-checks prescription medicines and flags critical contraindications.
    Never auto-approves a prescription fill without pharmacist review.
    """
    prescription = state.get("prescription")
    if not prescription:
        return state

    medicines = prescription.get("medicines", [])
    med_names = [m.get("name", "").lower() for m in medicines]

    alerts: List[Dict[str, Any]] = []

    # Known severe interaction pairs for pharmacy safety
    rules = [
        {
            "pair": ["brufen", "warfarin"],
            "severity": "critical",
            "drug_a": "Brufen (Ibuprofen)",
            "drug_b": "Warfarin",
            "desc_ar": "خطر نزيف حاد وقاتل بالجهاز الهضمي نتيجة تداخل البروفين مع مضادات التجلط.",
            "desc_en": "Severe gastrointestinal hemorrhage risk when combining NSAIDs with anticoagulants."
        },
        {
            "pair": ["ketofan", "warfarin"],
            "severity": "critical",
            "drug_a": "Ketofan (Ketoprofen)",
            "drug_b": "Warfarin",
            "desc_ar": "خطر نزيف شديد - يمنع الجمع بين الكيتوفان ومضادات التجلط.",
            "desc_en": "High risk of bleeding with Ketoprofen + Warfarin."
        },
        {
            "pair": ["augmentin", "methotrexate"],
            "severity": "critical",
            "drug_a": "Augmentin",
            "drug_b": "Methotrexate",
            "desc_ar": "يزيد الأموكسيسيللين من سمية الميثوتريكسات بسبب تقليل إفرازه الكلوي.",
            "desc_en": "Penicillins reduce methotrexate renal clearance, increasing risk of toxicity."
        },
        {
            "pair": ["ciprofloxacin", "antacid"],
            "severity": "warning",
            "drug_a": "Ciprofloxacin",
            "drug_b": "Antacids",
            "desc_ar": "تقلل مضادات الحموضة من امتصاص السيبروفلوكساسين بدرجة كبيرة؛ يجب الفصل بساعتين.",
            "desc_en": "Antacids drastically decrease ciprofloxacin bioavailability; space by at least 2 hours."
        }
    ]

    for rule in rules:
        matches = [p for p in rule["pair"] if any(p in name for name in med_names)]
        if len(matches) == len(rule["pair"]):
            alerts.append({
                "severity": rule["severity"],
                "drug_a": rule["drug_a"],
                "drug_b": rule["drug_b"],
                "description_ar": rule["desc_ar"],
                "description_en": rule["desc_en"],
            })

    prescription["safety_alerts"] = alerts
    return {
        **state,
        "prescription": prescription,
        "safety_alerts": alerts
    }
