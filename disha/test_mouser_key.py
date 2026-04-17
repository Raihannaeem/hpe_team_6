import os
import requests

api_key = os.environ.get("MOUSER_API_KEY", "")

if not api_key:
    print("ERROR: MOUSER_API_KEY not set!")
    exit(1)

print(f"Testing API key: {api_key[:4]}...{api_key[-4:]}")

payload = {
    "SearchByKeywordRequest": {
        "keyword": "LDO regulator",
        "records": 5,
        "startingRecord": 0,
        "searchOptions": "string",
        "searchWithYourSignUpLanguage": "false",
    }
}

headers = {"Content-Type": "application/json", "Accept": "application/json"}
params = {"apiKey": api_key}

try:
    resp = requests.post(
        "https://api.mouser.com/api/v1/search/keyword",
        json=payload,
        headers=headers,
        params=params,
        timeout=10,
    )
    print(f"HTTP Status: {resp.status_code}")
    data = resp.json()
    
    if "Errors" in data and data["Errors"]:
        print(f"ERROR from Mouser: {data['Errors']}")
    elif "SearchResults" in data:
        parts = data.get("SearchResults", {}).get("Parts", [])
        print(f"SUCCESS: Got {len(parts)} results!")
        if parts:
            print(f"First result: {parts[0].get('ManufacturerPartNumber')}")
    else:
        print(f"Unexpected response: {list(data.keys())}")
        
except Exception as e:
    print(f"Request failed: {e}")
