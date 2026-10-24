"""Test: can we refund a seeded order, and can the refund be backdated?

1. Picks an early PAID seeded order from seeder_state.db.
2. Shows its payment transactions (seeded orders may have none).
3. Asks Shopify for a suggested refund for 1 unit of the first line item.
4. Creates the refund (with the required @idempotent key), trying a backdated
   processedAt first and falling back without it if the field isn't accepted.
5. Reads the order back and reports what happened.

Run from the project root:  python test_refund.py
"""
import json
from datetime import datetime, timedelta
from seeder import state
from seeder.shopify_client import ShopifyClient, GraphQLError

ORDER_Q = """
query($id: ID!) {
  order(id: $id) {
    id name processedAt displayFinancialStatus
    transactions { id kind status gateway amountSet { shopMoney { amount } } }
    lineItems(first: 10) { nodes { id title quantity sku } }
  }
}"""

SUGGEST_Q = """
query($id: ID!, $items: [RefundLineItemInput!]) {
  order(id: $id) {
    suggestedRefund(refundLineItems: $items) {
      amountSet { shopMoney { amount } }
      suggestedTransactions {
        gateway kind amountSet { shopMoney { amount } }
        parentTransaction { id }
      }
    }
  }
}"""

REFUND = """
mutation refund($input: RefundInput!, $key: String!) {
  refundCreate(input: $input) @idempotent(key: $key) {
    refund { id createdAt totalRefundedSet { shopMoney { amount } } }
    userErrors { field message }
  }
}"""

AFTER_Q = """
query($id: ID!) {
  order(id: $id) {
    name displayFinancialStatus
    totalRefundedSet { shopMoney { amount } }
    refunds(first: 5) {
      id createdAt
      totalRefundedSet { shopMoney { amount } }
      refundLineItems(first: 5) { nodes { quantity subtotalSet { shopMoney { amount } } } }
    }
  }
}"""


def main():
    client = ShopifyClient()

    # 1. pick an early, paid, successfully created seeded order
    candidates = sorted(
        (o for o in state.all_of("order")
         if o["id"] != "SKIPPED" and not o.get("pending") and o.get("processed_at")),
        key=lambda o: o["key"])
    o = candidates[0]
    order = client.gql(ORDER_Q, {"id": o["id"]})["order"]
    print(f"Order {order['name']} processed {order['processedAt']} status {order['displayFinancialStatus']}")
    print("Transactions:", json.dumps(order["transactions"], indent=2) or "none")

    line = order["lineItems"]["nodes"][0]
    print(f"Refunding 1 x {line['title']} ({line['sku']})")
    items = [{"lineItemId": line["id"], "quantity": 1, "restockType": "NO_RESTOCK"}]

    # 2. suggested refund (gives amount + which transaction to refund against, if any)
    sug = client.gql(SUGGEST_Q, {"id": order["id"], "items": items})["order"]["suggestedRefund"]
    print("Suggested refund amount:", sug["amountSet"]["shopMoney"]["amount"])
    transactions = [{
        "orderId": order["id"], "kind": "REFUND", "gateway": t["gateway"],
        "amount": t["amountSet"]["shopMoney"]["amount"],
        "parentId": t["parentTransaction"]["id"],
    } for t in sug["suggestedTransactions"] if t.get("parentTransaction")]
    print("Refund transactions to create:", transactions or "none (order has no payment transaction)")

    # 3. create refund, 10 days after the order date
    backdate = (datetime.fromisoformat(order["processedAt"].replace("Z", "+00:00"))
                + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    base_input = {"orderId": order["id"], "notify": False, "note": "seed-test refund",
                  "refundLineItems": items, "transactions": transactions}
    key = f"test-refund-{o['key']}"

    try:
        res = client.gql(REFUND, {"input": {**base_input, "processedAt": backdate}, "key": key})
        tried_backdate = True
    except GraphQLError as e:
        print("\nBackdated refund rejected by schema -> retrying without processedAt")
        print(str(e)[:400])
        res = client.gql(REFUND, {"input": base_input, "key": key + "-nobackdate"})
        tried_backdate = False

    rc = res["refundCreate"]
    if rc["userErrors"]:
        raise SystemExit("userErrors:\n" + json.dumps(rc["userErrors"], indent=2))
    print("\nRefund created:", json.dumps(rc["refund"], indent=2))

    # 4. read back
    after = client.gql(AFTER_Q, {"id": order["id"]})["order"]
    print("\nOrder after refund:", json.dumps(after, indent=2))
    print("\n--- RESULTS ---")
    print("Backdate field accepted:", tried_backdate, "| requested:", backdate,
          "| refund createdAt:", rc["refund"]["createdAt"])
    print("Money refunded:", rc["refund"]["totalRefundedSet"]["shopMoney"]["amount"])


if __name__ == "__main__":
    main()