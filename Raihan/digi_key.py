import requests
client_id = "zXOQ75gdT6eJJRcGG5VBxY0zfrRLp0pWGrKswSykoSRzBX4U"
client_secret = "mfb7qJnxxJr7m0GKAAjaXG4yEUNGeDdMccLWaRTYDNzAfBu2cV3pBbubgpG7NM6b"

def getAccessToken():
    url = "https://api.digikey.com/v1/oauth2/token"

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers)
    token = response.json()["access_token"]

    # print(token, "\n")
    return token

# LDO product number
productNumber = "MIC5365-3.3YC5-TR"
testBody = {
    "component-type": "LDO",
    "input-voltage": "5V",
    "output-voltage": "3.3V",
}

#From recommendedProducts API endpoint
def recommendedProduct(Pno):
    url = f"https://api.digikey.com/products/v4/search/{productNumber}/recommendedproducts"
    token = getAccessToken()
    response = requests.get(url, headers={"X-DIGIKEY-Client-Id": client_id, "Authorization": f"Bearer {token}"})
    res = response.json()
    print ("Response keys: ", res.keys())
    print ("Recommendations length: ", len(res['Recommendations']))
    print ("Recommendations[0] keys: ", res['Recommendations'][0].keys())
    print ("Recommendations[0].RecommendedProducts length: ", len(res['Recommendations'][0]['RecommendedProducts']))
    print ("Recommendations[0].RecommendedProducts[0] keys: ", res['Recommendations'][0]['RecommendedProducts'][0].keys())
    print()
    print("Product Numbers of the recommendations with descriptions: ")
    for i in res['Recommendations'][0]['RecommendedProducts']:
        print(i['DigiKeyProductNumber'], i['ProductDescription'], sep=" : ")

#From productDetails API endpoint
def productVariation(Pno):
    url = f"https://api.digikey.com/products/v4/search/{Pno}/productdetails"
    token = getAccessToken()
    response = requests.get(url, headers={"X-DIGIKEY-Client-Id": client_id, "Authorization": f"Bearer {token}"})
    res = response.json()
    print("Response keys: ", res.keys())
    print()
    print("Product keys: ", res['Product'].keys())
    print()
    print("Product.ProductVariations length: ", len(res['Product']['ProductVariations']))
    print()
    print("ProductVariations[0] keys: ", res['Product']['ProductVariations'][0].keys())
    print()
    print("Product.Description keys: ", res['Product']['Description'].keys())
    print()
    print("Product.Description.DetailedDescription: ", res['Product']['Description']['DetailedDescription'])

def keyWordSearch(body):
    url = "https://api.digikey.com/products/v4/search/keyword"
    token = getAccessToken()
    headers = {
        "X-DIGIKEY-Client-Id": client_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-DIGIKEY-Locale-Currency": "INR",
        "X-DIGIKEY-Locale-Site": "IN",
    }
    body = {"keywords": f"{body['component-type']} {body['input-voltage']} {body['output-voltage']}"}
    
    response = requests.post(url, headers=headers, json=body)
    res = response.json()
    
    print("Response keys -->", res.keys())
    print()
    print("Response.Products length -->", len(res['Products']))
    print()
    print("Products[0] keys -->", res['Products'][0].keys())
    print()
    print("Products[0].Description keys -->", res['Products'][0]['Description'].keys())
    print()
    print("Description.DetailedDescription -->", res['Products'][0]['Description']['DetailedDescription'])
    print()
    print("Products[0].ManufacturerProductNumber -->", res['Products'][0]['ManufacturerProductNumber'])
    print()
    print()
    
    print("Query -->", body['keywords'])
    print()
    for i in res['Products']:
        print(i['ManufacturerProductNumber']," --> ",i['Description']['DetailedDescription'])

# recommendedProduct(productNumber)
productVariation(productNumber)
# keyWordSearch(testBody)