"""
test_pipeline.py
Quick smoke-test for Phase 3 + 4 logic using mock data.
No real MOUSER_API_KEY or ANTHROPIC_API_KEY required.

Run from project root:
    python backend/test_pipeline.py
"""

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# ── 1. Test: Query builder fallback (no LLM) ─────────────────────────────────
from phase3_query_builder import build_mouser_query_fallback

"""DUMMY_JSON = {
    "component_name": "LT1763",
    "component_type": "LDO Regulator",
    "manufacturer": "Linear Technology",
    "description": "Micropower, low noise, low dropout regulator",
    "electrical_specs": {
        "input_voltage_min_V": 1.8,
        "input_voltage_max_V": 20,
        "output_voltage_min_V": 1.22,
        "output_voltage_max_V": 20,
        "output_voltage_fixed_V": None,
        "output_current_max_mA": 500,
        "dropout_voltage_typical_mV": 300,
        "quiescent_current_uA": 30,
        "output_noise_uVrms": 20,
        "psrr_dB": 65,
        "shutdown_current_uA": 0.1,
        "current_limit_mA": 520,
    },
    "operating_conditions": {"temp_min_C": -40, "temp_max_C": 125, "junction_temp_max_C": 150},
    "packages": ["8-Lead Plastic SO", "12-Lead (4mm x 3mm) Plastic DFN"],
    "features": ["Low Noise", "Low Quiescent Current"],
    "adjustable_output": True,
    "datasheet_url": "https://www.linear.com/product/LT1763",
}"""

DUMMY_JSON = {
  "component_name": "LM1117-3.3",
  "component_type": "LDO Regulator",
  "manufacturer": "Various",
  "description": "3.3V linear regulator, 800mA, low dropout",
    "electrical_specs": {
        "input_voltage_min_V": 4.5,
        "input_voltage_max_V": 20,
        "output_voltage_fixed_V": 3.3,
        "output_current_max_mA": 500,
        "quiescent_current_uA": 500,
        "dropout_voltage_typical_mV": 1200
    },
  "packages": ["SOT-223", "TO-252"],
  "features": ["Fixed output"],
  "adjustable_output": False,
  "datasheet_url": ""
}

query = build_mouser_query_fallback(DUMMY_JSON)
print(f"[TEST 1] Fallback query:  '{query}'")
assert len(query) > 0, "Query should not be empty"
assert "LDO" in query or "Regulator" in query, "Query should mention component type"
print("         ✓ PASSED\n")


# ── 2. Test: Hard filter ──────────────────────────────────────────────────────
from phase3_hard_filter import hard_filter

MOCK_PARTS = [
    # Should PASS
    {
        "mpn": "MIC5219-3.3YM5-TR", "manufacturer": "Microchip",
        "description": "LDO regulator 500mA 20V adjustable low noise",
        "mouser_pn": "998-MIC5219-3.3YM5-TR", "product_url": "https://mouser.com/p/1",
        "price_usd": 0.45, "stock": 5000, "lifecycle": "Active",
        "category": "LDO Voltage Regulators", "datasheet_url": "", "raw": {},
    },
    # Should FAIL — eval kit
    {
        "mpn": "LT1763EV#PBF", "manufacturer": "Analog Devices",
        "description": "LT1763 eval kit demo board",
        "mouser_pn": "584-LT1763EVPBF", "product_url": "https://mouser.com/p/2",
        "price_usd": 59.99, "stock": 10, "lifecycle": "Active",
        "category": "Evaluation Boards", "datasheet_url": "", "raw": {},
    },
    # Should FAIL — no stock
    {
        "mpn": "TPS7A0518PDRVR", "manufacturer": "Texas Instruments",
        "description": "LDO regulator 200mA 5.5V ultralow IQ",
        "mouser_pn": "595-TPS7A0518PDRVR", "product_url": "https://mouser.com/p/3",
        "price_usd": 0.38, "stock": 0, "lifecycle": "Active",
        "category": "LDO Regulators", "datasheet_url": "", "raw": {},
    },
    # Should FAIL — obsolete
    {
        "mpn": "LM317T", "manufacturer": "ST Microelectronics",
        "description": "Adjustable LDO regulator 1.5A 37V",
        "mouser_pn": "511-LM317T", "product_url": "https://mouser.com/p/4",
        "price_usd": 0.22, "stock": 1200, "lifecycle": "NRND",
        "category": "Linear Regulators", "datasheet_url": "", "raw": {},
    },
    # Should PASS
    {
        "mpn": "AP2112K-3.3TRG1", "manufacturer": "Diodes Inc",
        "description": "600mA 20V CMOS LDO regulator low dropout",
        "mouser_pn": "621-AP2112K-3.3TRG1", "product_url": "https://mouser.com/p/5",
        "price_usd": 0.18, "stock": 15000, "lifecycle": "Active",
        "category": "LDO Voltage Regulators", "datasheet_url": "", "raw": {},
    },
]

filtered = hard_filter(MOCK_PARTS, DUMMY_JSON, require_stock=True)
print(f"[TEST 2] Hard filter: {len(MOCK_PARTS)} parts → {len(filtered)} passed")

passed_mpns = [p["mpn"] for p in filtered]
rejected_mpns = [p["mpn"] for p in MOCK_PARTS if p.get("_rejected")]

print(f"         Passed:   {passed_mpns}")
print(f"         Rejected: {[(p['mpn'], p.get('_rejected')) for p in MOCK_PARTS if p.get('_rejected')]}")

assert "MIC5219-3.3YM5-TR" in passed_mpns, "MIC5219 should pass"
assert "AP2112K-3.3TRG1" in passed_mpns, "AP2112K should pass"
assert "LT1763EV#PBF" not in passed_mpns, "Eval kit should be filtered"
assert "TPS7A0518PDRVR" not in passed_mpns, "No-stock part should be filtered"
assert "LM317T" not in passed_mpns, "NRND part should be filtered"
print("         ✓ PASSED\n")


# ── 3. Test: Rule-based scorer (no LLM) ──────────────────────────────────────
from phase3_scorer import _apply_rule_scores

test_parts = [
    {"mpn": "A", "stock": 15000, "price_usd": 0.18},
    {"mpn": "B", "stock": 500,   "price_usd": 0.45},
    {"mpn": "C", "stock": 0,     "price_usd": 1.20},
]
_apply_rule_scores(test_parts, DUMMY_JSON)
print("[TEST 3] Rule-based scoring:")
for p in test_parts:
    print(f"         {p['mpn']}: stock={p['score_stock']}/20  price={p['score_price']}/20")

assert test_parts[0]["score_stock"] == 20, "15000 stock should score 20"
assert test_parts[2]["score_stock"] == 0,  "0 stock should score 0"
assert test_parts[0]["score_price"] == 20, "Cheapest should get max price score"
assert test_parts[2]["score_price"] == 0,  "Most expensive should get 0 price score"
print("         ✓ PASSED\n")


# ── 4. Test: SQLite cache ─────────────────────────────────────────────────────
import tempfile, os
os.environ["DB_DIR"] = tempfile.mkdtemp()  # use temp dir for test

from phase4_cache import init_db, make_cache_key, get_cached, set_cache, clear_cache

init_db()

key = make_cache_key(DUMMY_JSON)
print(f"[TEST 4] Cache key (SHA256 prefix): {key[:16]}…")

# Cache miss
assert get_cached(DUMMY_JSON) is None, "Should be cache miss initially"

# Store + hit
set_cache(DUMMY_JSON, query, filtered)
hit = get_cached(DUMMY_JSON)
assert hit is not None, "Should be cache hit after set"
assert hit["cached"] is True, "Hit should have cached=True"
assert hit["query_string"] == query, "Query string should match"
assert hit["hit_count"] == 1, "hit_count should be 1 after first retrieval"

# Second hit increments counter
hit2 = get_cached(DUMMY_JSON)
assert hit2["hit_count"] == 2, "hit_count should be 2 after second retrieval"

# Clear
deleted = clear_cache()
assert deleted == 1, "Should delete exactly 1 entry"
assert get_cached(DUMMY_JSON) is None, "Should be cache miss after clear"

print("         ✓ PASSED\n")


print("=" * 50)
print("ALL TESTS PASSED ✓")
print("=" * 50)
print("\nNext steps:")
print("  1. Set env vars:  export MOUSER_API_KEY=...  ANTHROPIC_API_KEY=...")
print("  2. Start server:  cd backend && uvicorn main:app --reload --port 8000")
print("  3. Open browser:  http://localhost:8000")
