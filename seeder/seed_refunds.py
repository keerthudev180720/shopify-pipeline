"""Seeder step 4: refunds.

Picks ~6% of paid orders to refund (deterministically), with the return-prone
products refunded ~5x more often than everything else. Each refund is backdated
3-30 days after its order via processedAt (capped at "now").

Notes:
  - Seeded orders have no payment transactions, so refunds move $0 of money;
    the refunded VALUE lives in refundLineItems.subtotalSet. dbt models refund
    value from line items.
  - NO_RESTOCK: refunded items are not put back in stock (keeps the inventory
    simulation simple; many returns -- e.g. defective items -- aren't resellable).
  - Idempotent three ways: local state log, a check that the order has no refunds
    yet (check-before-write), and Shopify's required @idempotent key derived from
    the order key.

Run from the project root:
  python -m seeder.seed_refunds --dry-run
  python -m seeder.seed_refunds --limit 3
  python -m seeder.seed_refunds
"""
import argparse, random
from datetime import datetime, timedelta, timezone
from seeder import config as cfg, state
from seeder.shopify_client import ShopifyClient

BASE_LINE_RATE = 0.035        # chance a normal line gets refunded
RETURN_PRONE_LINE_RATE = 0.18 # chance a return-prone line gets refunded
REFUND_DELAY_DAYS = (3, 30)
REASONS = ["Wrong size", "Damaged in transit", "Not as described", "Changed mind", "Defective"]

ORDER_Q = """
query($id: ID!) {
  order(id: $id) {
    id name
    refunds(first: 1) { id }
    lineItems(first: 20) { nodes { id sku quantity } }
  }
}"""

REFUND = """
mutation refund($input: RefundInput!, $key: String!) {
  refundCreate(input: $input) @idempotent(key: $key) {
    refund { id processedAt
      refundLineItems(first: 10) { nodes { quantity subtotalSet { shopMoney { amount } } } } }
    userErrors { field message }
  }
}"""


def build_plan():
    rng = random.Random(cfg.RANDOM_SEED + 3)
    return_prone = {v["key"] for v in state.all_of("variant") if v.get("return_prone")}
    now = datetime.now(timezone.utc) - timedelta(hours=1)

    orders = sorted((o for o in state.all_of("order")
                     if o["id"] != "SKIPPED" and not o.get("pending") and o.get("lines")),
                    key=lambda o: o["key"])
    plan = []
    for o in orders:
        lines = []
        for ln in o["lines"]:
            rate = RETURN_PRONE_LINE_RATE if ln["sku"] in return_prone else BASE_LINE_RATE
            if rng.random() < rate:
                qty = ln["qty"] if ln["qty"] == 1 or rng.random() < 0.7 else rng.randint(1, ln["qty"] - 1)
                lines.append({"sku": ln["sku"], "qty": qty, "return_prone": ln["sku"] in return_prone})
        if not lines:
            continue
        ordered = datetime.fromisoformat(o["processed_at"])
        refund_at = min(ordered + timedelta(days=rng.randint(*REFUND_DELAY_DAYS),
                                            hours=rng.randint(0, 23)), now)
        plan.append({"order_key": o["key"], "order_id": o["id"], "lines": lines,
                     "processed_at": refund_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "reason": rng.choice(REASONS)})
    return plan, len(orders)


def print_stats(plan, n_eligible):
    rp = sum(any(l["return_prone"] for l in r["lines"]) for r in plan)
    print(f"Eligible paid orders: {n_eligible}")
    print(f"Planned refunds: {len(plan)} ({len(plan) / n_eligible:.1%} of orders); "
          f"{rp} involve return-prone products")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    plan, n_eligible = build_plan()
    print_stats(plan, n_eligible)
    if args.dry_run:
        return

    client = ShopifyClient()
    created = skipped = 0
    for r in plan:
        if args.limit is not None and created >= args.limit:
            break
        if state.get("refund", r["order_key"]):
            continue

        order = client.gql(ORDER_Q, {"id": r["order_id"]})["order"]
        if order["refunds"]:   # check-before-write: already refunded (crash window or manual test)
            state.record("refund", r["order_key"], order["refunds"][0]["id"], {"pre_existing": True})
            skipped += 1
            print(f"  {r['order_key']} {order['name']} already has a refund -> logged, skipped")
            continue

        by_sku = {li["sku"]: li for li in order["lineItems"]["nodes"]}
        items = [{"lineItemId": by_sku[l["sku"]]["id"], "quantity": l["qty"], "restockType": "NO_RESTOCK"}
                 for l in r["lines"] if l["sku"] in by_sku]
        if not items:
            state.record("refund", r["order_key"], "SKIPPED", {"reason": "line items not found"})
            skipped += 1
            continue

        res = client.gql(REFUND, {
            "key": f"refund-{r['order_key']}",
            "input": {"orderId": r["order_id"], "processedAt": r["processed_at"],
                      "notify": False, "note": f"Reason: {r['reason']}",
                      "refundLineItems": items, "transactions": []},
        })["refundCreate"]
        if res["userErrors"]:
            raise RuntimeError(f"{r['order_key']}: {res['userErrors']}")

        refund = res["refund"]
        value = sum(float(n["subtotalSet"]["shopMoney"]["amount"])
                    for n in refund["refundLineItems"]["nodes"])
        state.record("refund", r["order_key"], refund["id"], {
            "processed_at": refund["processedAt"], "reason": r["reason"],
            "lines": r["lines"], "value": value})
        created += 1
        print(f"  {r['order_key']} {order['name']} refunded ${value:.2f} on "
              f"{refund['processedAt'][:10]} ({r['reason']})")

    print(f"\nThis run: {created} refunds created, {skipped} skipped. "
          f"Progress: {len(state.all_of('refund'))}/{len(plan)} logged.")


if __name__ == "__main__":
    main()