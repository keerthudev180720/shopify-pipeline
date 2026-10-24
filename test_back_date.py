"""Test: can orderCreate backdate an order via processedAt?
Creates ONE order dated 2026-03-15 on the first product variant, then reads it back.
"""
import os, json, requests
from dotenv import load_dotenv

load_dotenv()
SHOP = os.environ["SHOP"].strip()
API = f"https://{SHOP}/admin/api/2026-07/graphql.json"
BACKDATE = "2026-03-15T14:30:00Z"


def get_token():
    r = requests.post(f"https://{SHOP}/admin/oauth/access_token", data={
        "grant_type": "client_credentials",
        "client_id": os.environ["SHOPIFY_CLIENT_ID"].strip(),
        "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"].strip(),
    })
    r.raise_for_status()
    return r.json()["access_token"]


def gql(token, query, variables=None):
    r = requests.post(API, headers={"X-Shopify-Access-Token": token},
                      json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    body = r.json()
    if "errors" in body:  # GraphQL can fail inside an HTTP 200
        raise SystemExit("GraphQL errors:\n" + json.dumps(body["errors"], indent=2))
    return body["data"]


CREATE = """
mutation orderCreate($order: OrderCreateOrderInput!, $options: OrderCreateOptionsInput) {
  orderCreate(order: $order, options: $options) {
    order { id name createdAt processedAt displayFinancialStatus }
    userErrors { field message }
  }
}"""

READ_BACK = """
query($id: ID!) {
  order(id: $id) { id name createdAt processedAt updatedAt tags
    totalPriceSet { shopMoney { amount } } }
}"""


def main():
    token = get_token()

    # Pick any existing variant to put on the order
    v = gql(token, "{ productVariants(first: 1) { nodes { id sku price } } }")
    variant = v["productVariants"]["nodes"][0]
    print("Using variant:", variant)

    variables = {
        "order": {
            "processedAt": BACKDATE,
            "financialStatus": "PAID",
            "tags": ["seed-test"],  # so test orders are easy to find/remove later
            "lineItems": [{"variantId": variant["id"], "quantity": 1}],
        },
        "options": {"sendReceipt": False, "inventoryBehaviour": "BYPASS"},
    }
    result = gql(token, CREATE, variables)["orderCreate"]

    if result["userErrors"]:
        raise SystemExit("userErrors:\n" + json.dumps(result["userErrors"], indent=2))

    order = gql(token, READ_BACK, {"id": result["order"]["id"]})["order"]
    print("\nCreated order:")
    print(json.dumps(order, indent=2))

    print("\nRequested processedAt:", BACKDATE)
    if order["processedAt"].startswith("2026-03-15"):
        print("RESULT: backdating WORKS via processedAt")
    else:
        print("RESULT: processedAt was NOT kept -> fallback plan needed")
    print("createdAt is", order["createdAt"], "(expected: today; this is when the record was inserted)")


if __name__ == "__main__":
    main()


    