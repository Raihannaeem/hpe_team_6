"""
Phase 3 – Step 3: Hard Filter
Removes parts that are definitely unsuitable BEFORE scoring:
  - Eval / dev kits, modules, boards
  - Zero stock
  - Obsolete / discontinued / NRND lifecycle
  - Parts whose key electrical specs fall outside required tolerances

This runs purely on structured data — no LLM call needed.
"""

import re
from typing import Optional


# ── Keywords that indicate a non-component product ────────────────────────────
_KIT_KEYWORDS = re.compile(
    r"\b(eval|evaluation|dev\s*kit|devkit|demo|board|module|kit|shield|"
    r"breakout|dongle|adapter|reference design|refdes)\b",
    re.IGNORECASE,
)

# ── Lifecycle strings that mean "don't use in new designs" ────────────────────
_BAD_LIFECYCLE = {
    "obsolete",
    "discontinued",
    "nrnd",           # Not Recommended for New Designs
    "eol",            # End of Life
    "last time buy",
    "end of life",
    "not recommended for new designs",
}


def hard_filter(
    parts: list[dict],
    source_json: dict,
    require_stock: bool = True,
    voltage_tolerance: float = 0.20,   # ±20% on voltage specs
    current_tolerance: float = 0.20,   # output current must be >= 80% of reference
) -> list[dict]:
    """
    Applies hard filters to the Mouser results list.

    Args:
        parts:              Normalised parts list from phase3_mouser_search.
        source_json:        The original component JSON (for electrical boundary checks).
        require_stock:      If True, drop parts with 0 stock.
        voltage_tolerance:  Fractional tolerance for input voltage matching.
        current_tolerance:  Parts must supply at least (1 - tolerance) × reference Iout.

    Returns:
        Filtered list of parts dicts (same shape as input).
    """

    ref_specs = source_json.get("electrical_specs", {})
    ref_vin_max: Optional[float] = ref_specs.get("input_voltage_max_V")
    ref_iout: Optional[float] = ref_specs.get("output_current_max_mA")

    passed = []
    for part in parts:
        reason = _reject_reason(
            part,
            require_stock=require_stock,
            ref_vin_max=ref_vin_max,
            ref_iout=ref_iout,
            voltage_tolerance=voltage_tolerance,
            current_tolerance=current_tolerance,
        )
        if reason is None:
            passed.append(part)
        else:
            # Attach rejection reason for debug logging (not shown in UI)
            part["_rejected"] = reason

    return passed


def _reject_reason(
    part: dict,
    require_stock: bool,
    ref_vin_max: Optional[float],
    ref_iout: Optional[float],
    voltage_tolerance: float,
    current_tolerance: float,
) -> Optional[str]:
    """
    Returns a rejection reason string, or None if the part passes all checks.
    """

    desc = (part.get("description") or "").lower()
    mpn  = (part.get("mpn") or "").lower()

    # 1. Eval / dev kit check
    if _KIT_KEYWORDS.search(desc) or _KIT_KEYWORDS.search(mpn):
        return "eval/dev-kit"

    # 2. Lifecycle check
    lifecycle = (part.get("lifecycle") or "").strip().lower()
    for bad in _BAD_LIFECYCLE:
        if bad in lifecycle:
            return f"lifecycle:{lifecycle}"

    # 3. Stock check
    if require_stock and part.get("stock", 0) == 0:
        return "no-stock"

    # ── Electrical boundary checks (best-effort, from description parsing) ────
    # Mouser does not return structured specs in keyword search results.
    # We do a lightweight text scan of the description as a sanity check.

    # 4. Input voltage — if we can extract a number from description, it must
    #    be at least as large as the reference (within tolerance).
    if ref_vin_max is not None:
        found_vin = _extract_voltage_from_desc(desc)
        if found_vin is not None and found_vin < ref_vin_max * (1 - voltage_tolerance):
            return f"vin-too-low:{found_vin}V<{ref_vin_max}V"

    # 5. Output current — part must be capable of at least 80% of reference Iout
    if ref_iout is not None:
        found_iout = _extract_current_mA_from_desc(desc)
        if found_iout is not None and found_iout < ref_iout * (1 - current_tolerance):
            return f"iout-too-low:{found_iout}mA<{ref_iout}mA"

    return None  # passes all checks


def _extract_voltage_from_desc(desc: str) -> Optional[float]:
    """
    Tries to find the highest voltage figure (in V) mentioned in description.
    e.g. "2.5V to 20V input" → 20.0
    """
    hits = re.findall(r"(\d+(?:\.\d+)?)\s*v\b", desc, re.IGNORECASE)
    nums = [float(h) for h in hits if 1.0 <= float(h) <= 100.0]
    return max(nums) if nums else None


def _extract_current_mA_from_desc(desc: str) -> Optional[float]:
    """
    Tries to find output current in mA from description.
    Handles both "500mA" and "1A" forms.
    """
    # mA form
    hits_ma = re.findall(r"(\d+(?:\.\d+)?)\s*ma\b", desc, re.IGNORECASE)
    if hits_ma:
        return max(float(h) for h in hits_ma)

    # A form — convert to mA
    hits_a = re.findall(r"(\d+(?:\.\d+)?)\s*a\b", desc, re.IGNORECASE)
    if hits_a:
        amps = [float(h) for h in hits_a if float(h) <= 50]  # ignore unrealistic values
        if amps:
            return max(amps) * 1000

    return None
