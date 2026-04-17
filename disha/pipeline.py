"""
Pipeline Orchestrator
Ties Phase 3 and Phase 4 together into a single callable function.

Flow:
  1. Check SQLite cache (Phase 4) → return instantly on hit
  2. Build Mouser keyword query via LLM (Phase 3, Step 1)
  3. Call Mouser keyword search API (Phase 3, Step 2)
  4. Hard filter results (Phase 3, Step 3)
  5. Score and rank results via LLM + rules (Phase 3, Step 4)
  6. Store in SQLite cache (Phase 4)
  7. Return top 5 results

Usage:
    from pipeline import run_pipeline
    result = run_pipeline(component_json)
"""

from phase3_query_builder import build_mouser_query, build_mouser_query_fallback
from phase3_mouser_search import search_mouser
from phase3_hard_filter import hard_filter
from phase3_scorer import score_parts
from phase4_cache import init_db, get_cached, set_cache


# Initialise DB on import (idempotent)
init_db()


def run_pipeline(
    component_json: dict,
    use_llm_query: bool = True,
    top_n: int = 5,
    require_stock: bool = True,
) -> dict:
    """
    Runs the full Phase 3 + Phase 4 pipeline.

    Args:
        component_json:  Structured component JSON from Phase 2 (or dummy JSON for testing).
        use_llm_query:   If True, use LLM to build query; else use rule-based fallback.
        top_n:           Number of top results to return and display (default 5).
        require_stock:   If True, filter out parts with zero stock.

    Returns:
        {
          "results":      [...],   — list of top_n scored part dicts
          "query_string": "...",   — Mouser keyword string used
          "cached":       bool,    — True if result came from cache
          "total_found":  int,     — total parts found before filtering
          "after_filter": int,     — parts remaining after hard filter
          "created_at":   str,     — ISO timestamp
          "hit_count":    int,     — cache hit count (0 if fresh)
          "error":        str|None — error message if something went wrong
        }
    """

    # ── Phase 4: Cache check ──────────────────────────────────────────────────
    cached = get_cached(component_json)
    if cached is not None:
        print(f"[Pipeline] Cache HIT (hit_count={cached['hit_count']})")
        cached["total_found"] = len(cached["results"])
        cached["after_filter"] = len(cached["results"])
        cached["error"] = None
        return cached

    print("[Pipeline] Cache MISS — running full pipeline")

    # ── Phase 3, Step 1: Build Mouser query ───────────────────────────────────
    try:
        if use_llm_query:
            query_string = build_mouser_query(component_json)
            print(f"[Pipeline] LLM query: '{query_string}'")
        else:
            query_string = build_mouser_query_fallback(component_json)
            print(f"[Pipeline] Fallback query: '{query_string}'")
    except Exception as e:
        print(f"[Pipeline] Query builder failed: {e} — using fallback")
        query_string = build_mouser_query_fallback(component_json)

    # ── Phase 3, Step 2: Mouser search ───────────────────────────────────────
    try:
        raw_parts = search_mouser(query_string, records=50)
        print(f"[Pipeline] Mouser returned {len(raw_parts)} parts for '{query_string}'")
    except EnvironmentError as e:
        # API key not set
        return _error_response(query_string, str(e))
    except Exception as e:
        return _error_response(query_string, f"Mouser search failed: {e}")

    # If the first query returns no results, try progressively relaxed queries
    if not raw_parts:
        print("[Pipeline] No results — attempting relaxed queries")
        tried = {query_string}
        # 1) rule-based fallback
        try:
            fallback_q = build_mouser_query_fallback(component_json)
        except Exception:
            fallback_q = None

        candidates = [q for q in (fallback_q, ) if q and q not in tried]

        # 2) simple component-type-only query
        comp_type = component_json.get("component_type")
        if comp_type and comp_type not in tried:
            candidates.append(comp_type)

        # 3) component type + current (rounded) if available
        specs = component_json.get("electrical_specs", {})
        iout = specs.get("output_current_max_mA")
        if iout:
            rounded = int(max(1, round(iout / 100.0) * 100))
            q3 = f"{component_json.get('component_type','')} {rounded}mA".strip()
            if q3 and q3 not in tried:
                candidates.append(q3)

        # Try each candidate until we get results
        for q in candidates:
            try:
                print(f"[Pipeline] Retry search with: '{q}'")
                raw_parts = search_mouser(q, records=50)
                print(f"[Pipeline] Mouser returned {len(raw_parts)} parts for relaxed query '{q}'")
                if raw_parts:
                    query_string = q
                    break
                tried.add(q)
            except EnvironmentError as e:
                return _error_response(query_string, str(e))
            except Exception as e:
                print(f"[Pipeline] Relaxed search failed: {e}")

    if not raw_parts:
        return _error_response(query_string, "Mouser returned no results for this query.")

    total_found = len(raw_parts)

    # ── Phase 3, Step 3: Hard filter ─────────────────────────────────────────
    filtered = hard_filter(raw_parts, component_json, require_stock=require_stock)
    print(f"[Pipeline] After hard filter: {len(filtered)} parts")

    if not filtered:
        # Relax stock requirement and retry filter
        print("[Pipeline] No parts after strict filter — relaxing stock requirement")
        filtered = hard_filter(raw_parts, component_json, require_stock=False)

    if not filtered:
        return _error_response(
            query_string,
            "All Mouser results were filtered out (eval kits, obsolete, or wrong specs).",
        )

    after_filter = len(filtered)

    # ── Phase 3, Step 4: Score and rank ──────────────────────────────────────
    try:
        scored = score_parts(filtered, component_json, top_n=top_n)
        print(f"[Pipeline] Top {len(scored)} scored parts ready")
    except Exception as e:
        print(f"[Pipeline] Scoring failed: {e} — returning unscored results")
        # Fallback: just return first top_n parts with zero scores
        for p in filtered[:top_n]:
            p.setdefault("score_total", 0)
            p.setdefault("score_stock", 0)
            p.setdefault("score_price", 0)
            p.setdefault("score_electrical", 0)
            p.setdefault("score_rationale", "Scoring unavailable.")
        scored = filtered[:top_n]

    # ── Phase 4: Store in cache ───────────────────────────────────────────────
    try:
        set_cache(component_json, query_string, scored)
        print("[Pipeline] Results cached")
    except Exception as e:
        print(f"[Pipeline] Cache write failed (non-fatal): {e}")

    from datetime import datetime, timezone
    return {
        "results": scored,
        "query_string": query_string,
        "cached": False,
        "total_found": total_found,
        "after_filter": after_filter,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hit_count": 0,
        "error": None,
    }


def _error_response(query_string: str, message: str) -> dict:
    from datetime import datetime, timezone
    return {
        "results": [],
        "query_string": query_string,
        "cached": False,
        "total_found": 0,
        "after_filter": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hit_count": 0,
        "error": message,
    }
