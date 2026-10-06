# tests/test_create_product_proposal.py
"""Add-a-product from the assistant chat (task 6b): the request parser and the card.

Plain functions, no database. The confirm endpoint is checked by hand (task 6b in the project doc).
"""
from agents.agents.product_intake import parse_product_request, product_gate
from agents.agents.verification import verification_agent

INVENTORY = [
    {"id": 1, "name_ar": "بنادول اكسترا (أحمر)", "name_en": "Panadol Extra", "stock_qty": 10,
     "unit_sell_price": 35.0, "unit_buy_price": 28.0, "price_batches": []},
    {"id": 2, "name_ar": "بروفين 400 مجم", "name_en": "Brufen 400mg", "stock_qty": 5,
     "unit_sell_price": 42.0, "unit_buy_price": 30.0, "price_batches": []},
]


def _card(text, language="en", inventory=None):
    state = product_gate({"user_query": text, "language": language, "inventory_data": inventory or []})
    assert state.get("intent") == "create_product"
    return verification_agent(state)


def test_english_request_reads_name_and_prices():
    parsed = parse_product_request("could you add new product called pandol price 10 sell 15")
    assert parsed == {"name": "pandol", "unit_buy_price": 10.0, "unit_sell_price": 15.0, "stock_qty": None, "min_threshold": None, "category": None}


def test_arabic_request_with_eastern_digits():
    parsed = parse_product_request("أضف منتج جديد اسمه بنادول سعر الشراء ١٠ سعر البيع ١٥")
    assert parsed["name"] == "بنادول"
    assert (parsed["unit_buy_price"], parsed["unit_sell_price"]) == (10.0, 15.0)


def test_sell_price_and_buy_price_words_in_either_order():
    parsed = parse_product_request("create product Augmentin 1g sell price 115 buy price 90")
    assert parsed["name"] == "Augmentin 1g"
    assert (parsed["unit_buy_price"], parsed["unit_sell_price"]) == (90.0, 115.0)


def test_minimum_level_and_category_are_read():
    parsed = parse_product_request(
        "سجل لي صنف جديد: بنادول أدفانس 24 قرص، سعر الشراء 35 جنيه وسعر البيع 48 جنيه، والحد الأدنى للنواقص 10 علب في قسم المسكنات"
    )
    assert (parsed["unit_buy_price"], parsed["unit_sell_price"], parsed["min_threshold"]) == (35.0, 48.0, 10.0)
    assert parsed["category"] == "المسكنات"
    assert parsed["name"].startswith("بنادول أدفانس 24")
    english = parse_product_request("add product Cetal buy 12 sell 18 min 8 category Analgesics")
    assert english["name"] == "Cetal" and english["min_threshold"] == 8.0 and english["category"] == "Analgesics"


def test_other_messages_are_not_add_product_requests():
    for text in [
        "how do I add a product?",
        "sold 2 panadol",
        "add 5 boxes of product panadol restock",
        "Show today's summary",
        "how many i buy today",
    ]:
        assert parse_product_request(text) is None, text
        assert "intent" not in product_gate({"user_query": text})


def test_card_has_no_line_items_and_nothing_is_created():
    proposal = _card("add product pandol buy 10 sell 15 qty 20")["proposal"]
    assert proposal["action_type"] == "create_product"
    assert proposal["status"] == "pending_confirmation"
    assert proposal["items"] == [] and proposal["total_amount"] == 0.0
    assert proposal["product"] == {
        "name_ar": "pandol", "name_en": "pandol", "unit_buy_price": 10.0,
        "unit_sell_price": 15.0, "stock_qty": 20.0, "min_threshold": 5.0, "category": None,
    }
    assert proposal["id"].startswith("prop-")


def test_missing_sell_price_asks_instead_of_proposing():
    result = _card("add new product pandol")
    assert result["proposal"] is None
    assert "sell price" in result["answer_text"]


def test_similar_spelling_is_flagged_as_a_possible_duplicate():
    proposal = _card("add product pandol buy 10 sell 15", inventory=INVENTORY)["proposal"]
    assert [row["id"] for row in proposal["duplicates"]] == [1]
    assert proposal["duplicates"][0]["exact"] is False
    assert any("similar" in warning for warning in proposal["warnings"])


def test_exact_name_is_flagged_exact():
    proposal = _card("add product Brufen 400mg buy 20 sell 42", inventory=INVENTORY)["proposal"]
    assert proposal["duplicates"][0]["id"] == 2 and proposal["duplicates"][0]["exact"] is True
    assert proposal["duplicates"][0]["stock_qty"] == 5.0 and proposal["duplicates"][0]["unit_sell_price"] == 42.0


def test_warns_when_buy_price_missing_or_above_sell_price():
    missing = _card("أضف منتج بنادول بيع 15", language="ar")["proposal"]
    # Two warnings: the missing buy price and (since Session 123) the missing category.
    assert missing["product"]["unit_buy_price"] == 0.0 and len(missing["warnings"]) == 2
    assert any("سعر الشراء" in warning for warning in missing["warnings"])
    assert any("القسم" in warning for warning in missing["warnings"])
    loss = _card("add product Cetal buy 20 sell 15")["proposal"]
    assert any("lower than the buy price" in warning for warning in loss["warnings"])