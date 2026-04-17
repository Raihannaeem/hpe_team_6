"""
Phase 3 – Step 2: Mouser API Search
Calls the Mouser keyword search API and normalises the response into a
consistent list-of-dicts format regardless of which Mouser API version
your key is provisioned for (v1 SearchByKeyword or v2 /search).

Set environment variable:  MOUSER_API_KEY=<your key>
"""

import os
import requests
from typing import Optional

MOUSER_API_KEY = os.environ.get("MOUSER_API_KEY", "")

if MOUSER_API_KEY:
    # Log masked version for debugging
    masked = MOUSER_API_KEY[:4] + "***" + MOUSER_API_KEY[-4:] if len(MOUSER_API_KEY) > 8 else "***"
    print(f"[Mouser] API key loaded: {masked}")
else:
    print("[Mouser] WARNING: MOUSER_API_KEY environment variable is NOT set!")

# Mouser v1 keyword search endpoint
MOUSER_SEARCH_URL = "https://api.mouser.com/api/v1/search/keyword"


def search_mouser(keyword: str, records: int = 50) -> list[dict]:
    """
    Calls Mouser keyword search API and returns a normalised list of parts.

    Each returned dict always contains these keys (missing values are None):
        mpn           – Manufacturer Part Number
        manufacturer  – Manufacturer name
        description   – Part description
        mouser_pn     – Mouser internal part number
        datasheet_url – URL to datasheet (if available)
        product_url   – Mouser product page URL
        price_usd     – Unit price in USD (cheapest price break, or None)
        stock         – Available stock quantity (integer)
        lifecycle     – Lifecycle status string (e.g. "Active", "Obsolete")
        category      – Category string from Mouser
        raw           – The original dict from Mouser (for debugging)

    Args:
        keyword: Search string built by phase3_query_builder.
        records: Max results to request (Mouser max is 50 per call).

    Returns:
        List of normalised part dicts (may be empty on error or no results).
    """

    if not MOUSER_API_KEY:
        raise EnvironmentError(
            "MOUSER_API_KEY environment variable is not set. "
            "Set it before running: set MOUSER_API_KEY=your_key_here"
        )

    payload = {
        "SearchByKeywordRequest": {
            "keyword": keyword,
            "records": records,
            "startingRecord": 0,
            "searchOptions": "string",   # search in part number + description
            "searchWithYourSignUpLanguage": "false",
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    params = {"apiKey": MOUSER_API_KEY}

    print(f"[Mouser] Searching for: '{keyword}' (records={records})")
    if MOUSER_API_KEY:
        key_masked = MOUSER_API_KEY[:4] + "***" + MOUSER_API_KEY[-4:] if len(MOUSER_API_KEY) > 8 else "***"
        print(f"[Mouser] Using API key: {key_masked}")
    else:
        print(f"[Mouser] ERROR: No API key available!")

    try:
        resp = requests.post(
            MOUSER_SEARCH_URL,
            json=payload,
            headers=headers,
            params=params,
            timeout=15,
        )
        print(f"[Mouser] HTTP {resp.status_code}")
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        print("[Mouser] Request timed out.")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"[Mouser] HTTP error: {e}")
        print(f"[Mouser] Response: {resp.text[:500]}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"[Mouser] Request failed: {e}")
        return []

    try:
        data = resp.json()
    except Exception as e:
        print(f"[Mouser] Failed to parse JSON: {e}")
        print(f"[Mouser] Response text: {resp.text[:300]}")
        return []

    print(f"[Mouser] Response keys: {list(data.keys())}")
    result = _normalise_response(data)
    print(f"[Mouser] Parsed {len(result)} parts from response")
    return result


def _normalise_response(data: dict) -> list[dict]:
    """
    Handles both Mouser v1 response shapes and returns a clean list.
    """

    # ── v1 shape ──────────────────────────────────────────────────────────────
    # { "SearchResults": { "Parts": [...] } }
    # ── v2 shape ──────────────────────────────────────────────────────────────
    # { "Parts": [...] }  (direct)

    raw_parts = []

    if "SearchResults" in data:
        search_results = data["SearchResults"]
        if isinstance(search_results, dict):
            raw_parts = search_results.get("Parts") or []
        # Some error responses have Errors list
        errors = data.get("Errors") or (search_results or {}).get("Errors") or []
        if errors:
            print(f"[Mouser] API returned errors: {errors}")
    elif "Parts" in data:
        raw_parts = data["Parts"] or []
    else:
        print(f"[Mouser] Unexpected response shape. Keys: {list(data.keys())}")
        # Check for error messages
        if "ErrorMessage" in data:
            print(f"[Mouser] ErrorMessage: {data['ErrorMessage']}")

    if not isinstance(raw_parts, list):
        print(f"[Mouser] Parts field is not a list: {type(raw_parts)}")
        return []

    print(f"[Mouser] Found {len(raw_parts)} raw parts to normalise")
    return [_normalise_part(p) for p in raw_parts]


def _normalise_part(p: dict) -> dict:
    """Flatten a single Mouser part dict into a canonical shape."""

    # ── Price: pick the lowest price break ────────────────────────────────────
    price_usd: Optional[float] = None
    price_breaks = p.get("PriceBreaks") or []
    if price_breaks:
        prices = []
        for pb in price_breaks:
            raw_price = pb.get("Price", "") or ""
            # Mouser returns price as string like "$0.95" or "0.95"
            cleaned = raw_price.replace("$", "").replace(",", "").strip()
            try:
                prices.append(float(cleaned))
            except ValueError:
                pass
        if prices:
            price_usd = min(prices)

    # ── Stock ─────────────────────────────────────────────────────────────────
    stock_raw = p.get("Availability") or p.get("AvailabilityInStock") or "0"
    stock = _parse_stock(str(stock_raw))

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    lifecycle = (
        p.get("LifecycleStatus")
        or p.get("Lifecycle")
        or p.get("ProductStatus")
        or "Unknown"
    )

    return {
        "mpn": p.get("ManufacturerPartNumber") or p.get("MfrPartNumber") or "",
        "manufacturer": p.get("Manufacturer") or p.get("ManufacturerName") or "",
        "description": p.get("Description") or p.get("ProductDescription") or "",
        "mouser_pn": p.get("MouserPartNumber") or "",
        "datasheet_url": p.get("DataSheetUrl") or p.get("DatasheetUrl") or "",
        "product_url": p.get("ProductDetailUrl") or p.get("ProductUrl") or "",
        "price_usd": price_usd,
        "stock": stock,
        "lifecycle": lifecycle,
        "category": p.get("Category") or p.get("ProductCategory") or "",
        "raw": p,
    }


def _parse_stock(raw: str) -> int:
    """
    Mouser returns stock as strings like:
      "1,234 In Stock", "In Stock", "0", "None", "2500"
    Extract the first integer found, or 0.
    """
    import re
    nums = re.findall(r"[\d,]+", raw.replace(",", ""))
    if nums:
        try:
            return int(nums[0].replace(",", ""))
        except ValueError:
            pass
    return 0
