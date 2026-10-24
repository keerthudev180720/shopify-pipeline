"""Explore Shopify data: runs orders, products, customers, inventory queries.
Prints a short summary and saves full JSON responses to ./exploration/ for inspection.
"""
import os, json, requests
from dotenv import load_dotenv

load_dotenv()
SHOP = os.environ["SHOP"].strip()
API_VERSION = "2026-07"

QUERIES = {
    "orders": """{
  orders(first: 50, sortKey: UPDATED_AT) {
    nodes {
      id name createdAt updatedAt
      displayFinancialStatus displayFulfillmentStatus
      totalPriceSet { shopMoney { amount currencyCode } }
      customer { id }
      lineItems(first: 20) {
        nodes {
          title quantity
          variant { id sku }
          originalUnitPriceSet { shopMoney { amount } }
        }
      }
      refunds(first: 5) {
        id createdAt
        totalRefundedSet { shopMoney { amount } }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}""",
    "products": """{
  products(first: 50) {
    nodes {
      id title productType vendor status createdAt updatedAt
      variants(first: 20) { nodes { id sku price inventoryQuantity } }
    }
    pageInfo { hasNextPage endCursor }
  }
}""",
    "customers": """{
  customers(first: 50) {
    nodes {
      id createdAt updatedAt numberOfOrders
      amountSpent { amount currencyCode }
    }
    pageInfo { hasNextPage endCursor }
  }
}""",
    "inventory": """{
  productVariants(first: 50) {
    nodes {
      sku
      inventoryItem {
        inventoryLevels(first: 5) {
          nodes {
            location { name }
            quantities(names: ["available", "on_hand"]) { name quantity }
          }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}""",
}


def get_token():
    resp = requests.post(f"https://{SHOP}/admin/oauth/access_token", data={
        "grant_type": "client_credentials",
        "client_id": os.environ["SHOPIFY_CLIENT_ID"].strip(),
        "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"].strip(),
    })
    resp.raise_for_status()
    body = resp.json()
    print("Granted scopes:", body.get("scope"), "\n")
    return body["access_token"]


def run_query(token, query):
    r = requests.post(f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json",
                      headers={"X-Shopify-Access-Token": token},
                      json={"query": query})
    r.raise_for_status()
    return r.json()


def summarize_orders(data):
    for o in data["orders"]["nodes"]:
        refunded = sum(float(rf["totalRefundedSet"]["shopMoney"]["amount"]) for rf in o["refunds"])
        print(f"  {o['name']}: {o['displayFinancialStatus']:<18} "
              f"total={o['totalPriceSet']['shopMoney']['amount']:>9} "
              f"lines={len(o['lineItems']['nodes'])} "
              f"customer={'GUEST' if o['customer'] is None else 'yes'} "
              f"refunded={refunded:.2f}")


def main():
    token = get_token()
    os.makedirs("exploration", exist_ok=True)

    for name, query in QUERIES.items():
        body = run_query(token, query)
        with open(f"exploration/{name}.json", "w") as f:
            json.dump(body, f, indent=2)

        cost = body.get("extensions", {}).get("cost", {})
        print(f"== {name} == (cost: {cost.get('actualQueryCost')}, "
              f"available: {cost.get('throttleStatus', {}).get('currentlyAvailable')})")

        # GraphQL can return HTTP 200 with errors in the body
        if "errors" in body:
            print("  ERRORS:", json.dumps(body["errors"], indent=2)[:800])
        if not body.get("data"):
            continue

        if name == "orders":
            summarize_orders(body["data"])
        else:
            count = len(next(iter(body["data"].values()))["nodes"])
            print(f"  {count} records -> exploration/{name}.json")
        print()


if __name__ == "__main__":
    main()

