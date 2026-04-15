import argparse
import os
import json
import re
from pathlib import Path
import requests
from dotenv import load_dotenv
from groq import Groq

# ---------------- LOAD ENV ----------------
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CLIENT_ID = os.getenv("DIGIKEY_CLIENT_ID")
CLIENT_SECRET = os.getenv("DIGIKEY_CLIENT_SECRET")

if not GROQ_API_KEY or not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("Missing API keys in .env")

# ---------------- CONFIG ----------------
GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_INPUT_JSON = "TC1263_specs.json"

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"

TOP_K = 10


def parse_args():
    parser = argparse.ArgumentParser(description="Search Digi-Key using a spec JSON file.")
    parser.add_argument(
        "--spec",
        default=DEFAULT_INPUT_JSON,
        help="Path to input spec JSON (absolute or relative to this script directory).",
    )
    return parser.parse_args()


def resolve_spec_path(spec_arg, base_dir):
    spec_path = Path(spec_arg)
    if not spec_path.is_absolute():
        spec_path = base_dir / spec_path
    return spec_path.resolve()


# ---------------- LOAD SPEC ----------------
def load_spec(path):
    with open(path, "r") as f:
        return json.load(f)


# ---------------- SAFE JSON PARSER ----------------
def safe_parse_llm_output(raw):
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except:
        pass
    return None


# ---------------- LLM QUERY BUILDER ----------------
def build_query_with_llm(spec):
    client = Groq(api_key=GROQ_API_KEY)

    PROMPT = """
You are an expert electronics engineer.

Generate an optimal Digi-Key search keyword.

Rules:
- 3 to 6 words only
- Include component type
- Include 1–2 key specs (current/voltage/features)
- No ranges
- No sentences

Return JSON:
{"search_keyword": "...", "reasoning": "..."}
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(spec)}
        ],
        temperature=0.3,
        max_tokens=120,
    )

    raw = response.choices[0].message.content.strip()

    parsed = safe_parse_llm_output(raw)

    if parsed:
        return parsed

    print("⚠️ Parsing failed, retrying with simpler prompt...")
    return fallback_query_with_llm(spec)


# ---------------- LLM FALLBACK QUERY ----------------
def fallback_query_with_llm(spec):
    client = Groq(api_key=GROQ_API_KEY)

    PROMPT = """
Generate a VERY SIMPLE Digi-Key search keyword.

Rules:
- Only 2–4 words
- Include component type
- Include ONE key spec

Return JSON:
{"search_keyword": "..."}
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": json.dumps(spec)}],
        temperature=0.2,
        max_tokens=60,
    )

    raw = response.choices[0].message.content.strip()

    parsed = safe_parse_llm_output(raw)

    if parsed:
        return parsed

    return {"search_keyword": ""}  # still no hardcoding


# ---------------- GENERATE FALLBACK QUERIES ----------------
def generate_fallback_queries_with_llm(spec, original_query):
    client = Groq(api_key=GROQ_API_KEY)

    PROMPT = f"""
Given this search query:
"{original_query}"

Generate 3 simpler alternative queries for Digi-Key search.

Rules:
- Short (2–5 words)
- Reduce complexity gradually

Return JSON:
{{"queries": ["...", "...", "..."]}}
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.3,
        max_tokens=100,
    )

    raw = response.choices[0].message.content.strip()

    parsed = safe_parse_llm_output(raw)

    if parsed and "queries" in parsed:
        return parsed["queries"]

    return []


# ---------------- DIGIKEY AUTH ----------------
def get_access_token():
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(TOKEN_URL, data=payload, headers=headers)
    response.raise_for_status()

    return response.json()["access_token"]


# ---------------- DIGIKEY SEARCH ----------------
def search_digikey(keyword, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": CLIENT_ID,
        "Content-Type": "application/json"
    }

    payload = {
        "Keywords": keyword,
        "RecordCount": TOP_K
    }

    response = requests.post(SEARCH_URL, json=payload, headers=headers)
    response.raise_for_status()

    return response.json()


# ---------------- EXTRACT PRODUCTS ----------------
def extract_products(data):
    products = data.get("Products", [])
    results = []

    for p in products:
        specs = {}

        for param in p.get("Parameters", []):
            name = param.get("ParameterText", "")
            value = param.get("ValueText", "")

            if name:
                specs[name] = value

        results.append({
            "manufacturer": p.get("Manufacturer", {}).get("Name"),
            "manufacturer_part_number": p.get("ManufacturerPartNumber"),
            "digi_key_part_number": p.get("DigiKeyPartNumber"),
            "description": p.get("Description", {}).get("ProductDescription"),
            "category": p.get("Category", {}).get("Name"),
            "stock": p.get("QuantityAvailable"),
            "unit_price": p.get("UnitPrice"),
            "datasheet_url": p.get("DatasheetUrl"),
            "product_url": p.get("ProductUrl"),
            "parameters": specs
        })

    return results


# ---------------- FILTER ----------------
def is_relevant(product):
    desc = (product.get("description") or "").lower()
    params = product.get("parameters", {})
    return any(k in desc for k in ["reg", "amp", "mosfet", "driver"]) or params


# ---------------- MAIN ----------------
def main(spec_arg):
    base_dir = Path(__file__).resolve().parent
    spec_path = resolve_spec_path(spec_arg, base_dir)
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")

    print("[1] Loading spec...")
    spec = load_spec(spec_path)

    print("[2] Building query using LLM...")
    q = build_query_with_llm(spec)

    keyword = q.get("search_keyword", "")
    print("Generated Keyword:", keyword)

    print("[3] Getting Digi-Key token...")
    token = get_access_token()

    print("[4] Searching Digi-Key...")

    queries = [keyword] + generate_fallback_queries_with_llm(spec, keyword)

    data = None
    used_query = None

    for q_try in queries:
        if not q_try:
            continue

        print(f"Trying query: {q_try}")

        try:
            response = search_digikey(q_try, token)
            products = response.get("Products", [])

            if products:
                print(f"Success with: {q_try}")
                data = response
                used_query = q_try
                break
        except Exception as e:
            print("Error:", e)

    if not data:
        print("❌ No results found")
        products = []
    else:
        products = extract_products(data)

    print(f"Total fetched: {len(products)}")

    filtered = [p for p in products if is_relevant(p)]

    output = {
        "original_query": keyword,
        "final_query_used": used_query,
        "total_fetched": len(products),
        "filtered_results": len(filtered),
        "products": filtered
    }

    with open(base_dir / "digikey_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\nSaved to digikey_results.json")


if __name__ == "__main__":
    args = parse_args()
    main(args.spec)