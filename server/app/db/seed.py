import asyncio
from sqlalchemy.future import select
from server.app.db.session import AsyncSessionLocal, Base, engine
from server.app.db.migrations import upgrade_schema
from server.app.services.security import hash_pin
from server.app.config import settings
from server.app.db.models import (
    User, UserCredential, PharmacyProfile, PharmacyMember,
    InventoryItem, DrugInteractionRule, LedgerEntry, LedgerEntryItem, PharmacyOwnershipSlot
)


async def seed_data():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await upgrade_schema(conn)

    if not settings.SEED_DEMO_DATA:
        return

    async with AsyncSessionLocal() as session:
        # Skip if already seeded
        result = await session.execute(select(User).limit(1))
        if result.scalars().first():
            return

        # ── 1. Pharmacy Profile ──────────────────────────────────────
        pharmacy = PharmacyProfile(
            pharmacy_name="صيدلية روشتة النموذجية",
            owner_name="د. عمر ممدوح",
            phone="01012345678",
            address="شارع التحرير، الدقي، الجيزة",
            license_number="EG-PH-88921",
            tax_id="TR-4432190",
            currency="EGP",
            numerals_format="western",
            low_stock_default=5.0,
            language="ar",
            is_initialized=True,
        )
        session.add(pharmacy)
        await session.flush()   # get pharmacy.id

        # ── 2. Users ────────────────────────────────────────────────
        # Owner
        owner = User(
            name="د. عمر ممدوح (مالك)", phone="01012345678",
            pin="", language_pref="ar", is_active=True
        )
        # Senior pharmacist
        pharmacist = User(
            name="د. سارة أحمد (صيدلانية)", phone="01098765432",
            pin="", language_pref="ar", is_active=True
        )
        # Cashier
        cashier = User(
            name="محمد علي (كاشير)", phone="01111111111",
            pin="", language_pref="ar", is_active=True
        )
        session.add_all([owner, pharmacist, cashier])
        await session.flush()
        credentials = []
        for user, initial_pin in ((owner, "1234"), (pharmacist, "5678"), (cashier, "0000")):
            salt, digest = hash_pin(initial_pin)
            credentials.append(UserCredential(user_id=user.id, pin_salt=salt, pin_hash=digest))
        session.add_all(credentials)

        # ── 3. Membership links ─────────────────────────────────────
        session.add_all([
            PharmacyMember(
                pharmacy_id=pharmacy.id, user_id=owner.id,
                role="owner", invited_by=None
            ),
            PharmacyMember(
                pharmacy_id=pharmacy.id, user_id=pharmacist.id,
                role="pharmacist", invited_by=owner.id
            ),
            PharmacyMember(
                pharmacy_id=pharmacy.id, user_id=cashier.id,
                role="cashier", invited_by=owner.id
            ),
        ])
        session.add(PharmacyOwnershipSlot(user_id=owner.id, pharmacy_id=pharmacy.id, slot_number=1))

        # ── 4. Egyptian Pharmacy Inventory ──────────────────────────
        items = [
            dict(barcode="6221123456781", name_ar="بنادول اكسترا (أحمر)",    name_en="Panadol Extra (Red)",
                 active_ingredient="Paracetamol + Caffeine",  category="Analgesic",
                 stock_qty=48, min_threshold=10, unit_buy_price=28, unit_sell_price=35, expiry_date="2027-06-01"),
            dict(barcode="6221123456782", name_ar="بنادول أزرق (عادي)",      name_en="Panadol Blue",
                 active_ingredient="Paracetamol",             category="Analgesic",
                 stock_qty=30, min_threshold=8,  unit_buy_price=22, unit_sell_price=28, expiry_date="2027-08-01"),
            dict(barcode="6221123456783", name_ar="أوجمنتين 1 جم أقراص",   name_en="Augmentin 1g Tablets",
                 active_ingredient="Amoxicillin + Clavulanic Acid", category="Antibiotic",
                 stock_qty=14, min_threshold=5,  unit_buy_price=95, unit_sell_price=115, expiry_date="2026-12-01"),
            dict(barcode="6221123456784", name_ar="هاي بيوتك 1 جم",          name_en="Hibiotic 1g",
                 active_ingredient="Amoxicillin + Clavulanic Acid", category="Antibiotic",
                 stock_qty=22, min_threshold=6,  unit_buy_price=78, unit_sell_price=95,  expiry_date="2027-01-01"),
            dict(barcode="6221123456785", name_ar="كونجستال أقراص",           name_en="Congestal Tablets",
                 active_ingredient="Paracetamol + Pseudoephedrine", category="Cold & Flu",
                 stock_qty=4,  min_threshold=10, unit_buy_price=24, unit_sell_price=31,  expiry_date="2027-03-01"),
            dict(barcode="6221123456786", name_ar="بروفين 400 مجم",            name_en="Brufen 400mg",
                 active_ingredient="Ibuprofen",               category="NSAID",
                 stock_qty=18, min_threshold=8,  unit_buy_price=32, unit_sell_price=42,  expiry_date="2027-05-01"),
            dict(barcode="6221123456787", name_ar="كيتوفان 50 مجم",            name_en="Ketofan 50mg",
                 active_ingredient="Ketoprofen",              category="NSAID",
                 stock_qty=25, min_threshold=5,  unit_buy_price=20, unit_sell_price=27,  expiry_date="2027-09-01"),
            dict(barcode="6221123456788", name_ar="فلاجيل 500 مجم",            name_en="Flagyl 500mg",
                 active_ingredient="Metronidazole",           category="Antiparasitic",
                 stock_qty=2,  min_threshold=8,  unit_buy_price=18, unit_sell_price=24,  expiry_date="2026-11-01"),
            dict(barcode="6221123456789", name_ar="أنتينال كبسول",              name_en="Antinal Capsules",
                 active_ingredient="Nifuroxazide",            category="Antidiarrheal",
                 stock_qty=35, min_threshold=10, unit_buy_price=26, unit_sell_price=34,  expiry_date="2027-10-01"),
            dict(barcode="6221123456790", name_ar="أوتريفين بخاخ أنف",          name_en="Otrivin Nasal Spray",
                 active_ingredient="Xylometazoline",          category="Decongestant",
                 stock_qty=12, min_threshold=5,  unit_buy_price=16, unit_sell_price=22,  expiry_date="2027-04-01"),
        ]
        for d in items:
            session.add(InventoryItem(pharmacy_id=pharmacy.id, **d))

        # ── 5. Drug interaction rules ────────────────────────────────
        interactions = [
            dict(drug_a="Ibuprofen",      drug_b="Warfarin",
                 severity="critical",
                 description_ar="خطر نزيف حاد بالجهاز الهضمي مع مضادات التجلط.",
                 description_en="Severe GI hemorrhage risk: NSAIDs + anticoagulants."),
            dict(drug_a="Ketoprofen",     drug_b="Warfarin",
                 severity="critical",
                 description_ar="خطر نزيف شديد — يمنع الجمع بين كيتوفان ووارفارين.",
                 description_en="High bleeding risk: Ketoprofen + Warfarin."),
            dict(drug_a="Paracetamol",    drug_b="Alcohol",
                 severity="warning",
                 description_ar="زيادة خطر تسمم الكبد مع جرعات مرتفعة من الباراسيتامول.",
                 description_en="Hepatotoxicity risk with excessive paracetamol + alcohol."),
            dict(drug_a="Ciprofloxacin",  drug_b="Antacids",
                 severity="warning",
                 description_ar="تقلل مضادات الحموضة من امتصاص السيبروفلوكساسين — افصل بساعتين.",
                 description_en="Antacids reduce ciprofloxacin absorption; separate by 2h."),
            dict(drug_a="Sildenafil",     drug_b="Nitroglycerin",
                 severity="critical",
                 description_ar="انخفاض حاد وقاتل في ضغط الدم — يُمنع الجمع تمامًا.",
                 description_en="Fatal hypotensive crisis: PDE5 inhibitor + nitrates."),
        ]
        for d in interactions:
            session.add(DrugInteractionRule(**d))

        # ── 6. Sample ledger entry ───────────────────────────────────
        entry = LedgerEntry(
            id="init-entry-001", pharmacy_id=pharmacy.id,
            entry_type="log_sale", total_amount=150.0,
            payment_method="cash", notes="وردية الصباح الافتتاحية",
            created_by=owner.id, confirmed_by=owner.id
        )
        session.add(entry)
        await session.flush()
        session.add_all([
            LedgerEntryItem(entry_id="init-entry-001", item_id=1,
                            item_name="بنادول اكسترا (أحمر)", quantity=2, unit_price=35, unit_cost=28, subtotal=70),
            LedgerEntryItem(entry_id="init-entry-001", item_id=4,
                            item_name="هاي بيوتك 1 جم",        quantity=1, unit_price=80, unit_cost=78, subtotal=80),
        ])

        await session.commit()
        print("Roshetta database seeded successfully.")


if __name__ == "__main__":
    asyncio.run(seed_data())
