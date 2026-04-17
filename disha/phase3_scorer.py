"""
Phase 3 – Step 4: LLM + Rule-Based Scorer
Scores each filtered candidate part against the reference component JSON.

Scoring is a two-layer approach:
  Layer 1 (Rule-based, fast): stock score + price score → 0-40 pts
  Layer 2 (LLM, 1 API call):  electrical fit score for all candidates
                               returned as JSON → 0-60 pts

Total = Layer1 + Layer2  (max 100 pts)
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


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def score_parts(
    candidates: list[dict],
    source_json: dict,
    top_n: int = 10,
) -> list[dict]:
    """
    Scores and ranks candidate parts against the reference component JSON.

    Args:
        candidates:  Filtered parts list from phase3_hard_filter.
        source_json: Original component JSON from Phase 2.
        top_n:       Return only the top N results (default 10; Phase 4 shows top 5).

    Returns:
        Sorted list of candidate dicts (highest score first), each with extra keys:
            score_total     – int 0–100
            score_stock     – int 0–20  (rule-based)
            score_price     – int 0–20  (rule-based)
            score_electrical – int 0–60 (LLM)
            score_rationale – str       (LLM explanation, 1–2 sentences)
    """

    if not candidates:
        return []

    # Layer 1: fast rule-based scores
    _apply_rule_scores(candidates, source_json)

    # Layer 2: LLM electrical fit (batch call — all candidates in one prompt)
    _apply_llm_scores(candidates, source_json)

    # Combine and rank
    for p in candidates:
        p["score_total"] = (
            p.get("score_stock", 0)
            + p.get("score_price", 0)
            + p.get("score_electrical", 0)
        )

    candidates.sort(key=lambda x: x["score_total"], reverse=True)
    return candidates[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 – Rule-based scoring
# ─────────────────────────────────────────────────────────────────────────────

def _apply_rule_scores(candidates: list[dict], source_json: dict) -> None:
    """Mutates each candidate dict in-place, adding score_stock and score_price."""

    # ── Stock score (0–20) ────────────────────────────────────────────────────
    # 0 stock → 0 pts  |  1–99 → 5  |  100–999 → 10  |  1000–9999 → 15  |  10000+ → 20
    for p in candidates:
        stock = p.get("stock", 0)
        if stock >= 10_000:
            p["score_stock"] = 20
        elif stock >= 1_000:
            p["score_stock"] = 15
        elif stock >= 100:
            p["score_stock"] = 10
        elif stock >= 1:
            p["score_stock"] = 5
        else:
            p["score_stock"] = 0

    # ── Price score (0–20) ────────────────────────────────────────────────────
    # Relative to cheapest part in the candidate set.
    prices = [p["price_usd"] for p in candidates if p.get("price_usd") is not None]

    if prices:
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price if max_price > min_price else 1.0

        for p in candidates:
            if p.get("price_usd") is None:
                p["score_price"] = 0
            else:
                # Linear: cheapest → 20, most expensive → 0
                normalised = 1.0 - (p["price_usd"] - min_price) / price_range
                p["score_price"] = round(normalised * 20)
    else:
        for p in candidates:
            p["score_price"] = 0


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 – LLM electrical fit scoring
# ─────────────────────────────────────────────────────────────────────────────

def _apply_llm_scores(candidates: list[dict], source_json: dict) -> None:
    """
    Sends all candidates in a single LLM call and asks it to score electrical
    compatibility 0–60 for each, returning JSON.

    Mutates each candidate in-place, adding:
        score_electrical  (int 0–60)
        score_rationale   (str)
    """

    # Build a compact summary of each candidate for the prompt
    candidate_summaries = []
    for i, p in enumerate(candidates):
        candidate_summaries.append({
            "index": i,
            "mpn": p.get("mpn", ""),
            "manufacturer": p.get("manufacturer", ""),
            "description": p.get("description", ""),
        })

    prompt = f"""You are an expert electronics engineer evaluating component alternatives.

REFERENCE COMPONENT:
{json.dumps(source_json, indent=2)}

CANDIDATE ALTERNATIVES (from Mouser search):
{json.dumps(candidate_summaries, indent=2)}

TASK:
For each candidate, score its electrical compatibility with the reference component 
on a scale of 0 to 60, where:
  50–60 = Near drop-in replacement (same type, same or better specs)
  35–49 = Compatible with minor caveats (slight spec differences, same application)
  20–34 = Partially compatible (same component family, different performance tier)
  1–19  = Same category but significantly different specs
  0     = Wrong component type or incompatible

Also write a 1-sentence rationale explaining the score.

CRITICAL: Respond with ONLY a valid JSON array, no markdown, no explanation.
Format:
[
  {{"index": 0, "score_electrical": 55, "score_rationale": "Same LDO family with matching Iout and lower noise."}},
  {{"index": 1, "score_electrical": 30, "score_rationale": "LDO regulator but lower max input voltage limits applicability."}}
]"""

    try:
        response = _get_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.choices[0].message.content.strip()

        # Strip any accidental markdown fences
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw, flags=re.MULTILINE).strip()

        scores = json.loads(raw)

        # Apply scores back to candidates
        score_map = {item["index"]: item for item in scores}
        for i, p in enumerate(candidates):
            entry = score_map.get(i, {})
            p["score_electrical"] = int(entry.get("score_electrical", 0))
            p["score_rationale"] = entry.get("score_rationale", "No rationale provided.")

    except (json.JSONDecodeError, KeyError, Exception) as e:
        print(f"[Scorer] LLM scoring failed: {e}. Applying fallback scores.")
        for p in candidates:
            p["score_electrical"] = 20   # neutral fallback
            p["score_rationale"] = "Electrical score unavailable (LLM error)."
