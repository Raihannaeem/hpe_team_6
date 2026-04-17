"""
Phase 3 – Step 1: LLM Query Builder
Takes structured component JSON (from Phase 2) and uses an LLM to generate
an optimal keyword search string for the Mouser keyword search API.
"""

import json
import os
import re
from groq import Groq

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client


def build_mouser_query(component_json: dict) -> str:
    """
    Uses LLM to convert structured component JSON into a concise Mouser
    keyword search string that will return the most relevant alternatives.

    Args:
        component_json: The structured JSON output from Phase 2.

    Returns:
        A keyword string like: "LDO regulator 500mA 20V low noise"
    """

    prompt = f"""You are an electronics component search expert.

Given the following structured component specification in JSON, generate the BEST possible
keyword search string to find compatible ALTERNATIVE parts on Mouser Electronics.

Rules:
1. Output ONLY the keyword string — no explanation, no JSON, no markdown, no quotes.
2. The string must be 4-10 words.
3. Include: component type, key electrical values (output current, voltage range), package if space allows.
4. Use standard electronics abbreviations (LDO, MOSFET, op-amp, mA, V, uA, etc.)
5. Do NOT include the exact part number — we want alternatives, not the same part.
6. Priority order: component type > output current > voltage range > package.

Component JSON:
{json.dumps(component_json, indent=2)}

Keyword string:"""

    response = _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    # Strip any accidental surrounding quotes or backticks
    raw = re.sub(r"^[`\"']+|[`\"']+$", "", raw).strip()
    print(f"[QueryBuilder] LLM generated query: '{raw}'")
    return raw


def build_mouser_query_fallback(component_json: dict) -> str:
    """
    Rule-based fallback that constructs a keyword query from known JSON fields.
    Useful for testing Phase 3 without burning LLM tokens.
    """
    parts = []

    comp_type = component_json.get("component_type", "")
    if comp_type:
        parts.append(comp_type)

    specs = component_json.get("electrical_specs", {})

    iout = specs.get("output_current_max_mA")
    if iout is not None:
        parts.append(f"{int(iout)}mA")

    vin_max = specs.get("input_voltage_max_V")
    if vin_max is not None:
        parts.append(f"{vin_max}V")

    iq = specs.get("quiescent_current_uA")
    if iq is not None and iq < 100:
        parts.append("low quiescent")

    noise = specs.get("output_noise_uVrms")
    if noise is not None and noise < 50:
        parts.append("low noise")

    pkgs = component_json.get("packages", [])
    if pkgs:
        pkg_clean = re.sub(r"[^A-Za-z0-9]", " ", pkgs[0]).split()[0]
        parts.append(pkg_clean)

    query = " ".join(parts) if parts else "LDO regulator"
    print(f"[QueryBuilder] Fallback query: '{query}'")
    return query
