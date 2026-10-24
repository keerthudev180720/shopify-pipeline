import os, requests
from dotenv import load_dotenv
load_dotenv()

SHOP = os.environ["SHOP"].strip()  # e.g. ecommerce-keer.myshopify.com

# Step 1: get access token
resp = requests.post(f"https://{SHOP}/admin/oauth/access_token", data={
    "grant_type": "client_credentials",
    "client_id": os.environ["SHOPIFY_CLIENT_ID"].strip(),
    "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"].strip(),
})
print("SHOP:", repr(SHOP))
print("Status:", resp.status_code, "| Final URL:", resp.url)

if resp.status_code != 200:
    print("Response:", resp.text[:500])
    raise SystemExit("Token request failed — check the output above.")

tok = resp.json()["access_token"]
print("Token received.")

# Step 2: query orders
r = requests.post(f"https://{SHOP}/admin/api/2026-07/graphql.json",
    headers={"X-Shopify-Access-Token": tok},
    json={"query": "{ orders(first: 5) { nodes { id name createdAt } } }"})
print(r.status_code, r.json())
print("Granted scopes:", resp.json().get("scope"))
