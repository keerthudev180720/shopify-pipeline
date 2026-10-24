"""Seeder step 3: orders (the long overnight run).

Builds a deterministic 12-month order plan, then creates orders in Shopify in
chronological order, backdated with processedAt.

Realism:
  - order count per customer comes from their hidden segment (vip / repeat / one_time)
  - ~10% guest orders (no customer)
  - seasonality: holiday peak, summer dip, weekend + evening spikes
  - a few best-sellers (popularity skew); original snowboards sell rarely
  - ~3% of orders left PENDING
  - stock is tracked: normal products are restocked when low; the "low-stock"
    products run out and stay out for 45-90 days (visible as a sales gap)

Engineering:
  - resumable: every created order is logged in seeder_state.db; rerun continues
  - crash-safe: each order carries a tag seedkey-ORD-xxxxx; on restart the first
    unlogged order is looked up in Shopify before creating, so no duplicates
  - restocks use Shopify's @idempotent key (required from API 2026-04), derived
    from the order key, so a retried restock is never applied twice
  - paced under the dev-store limit of 5 orders/minute

Run from the project root:
  python -m seeder.seed_orders --dry-run     # show plan stats, create nothing
  python -m seeder.seed_orders --limit 5     # create first 5 orders (test)
  python -m seeder.seed_orders               # full run (hours) - resumable
"""
import argparse, random, time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from seeder import config as cfg, state
from seeder.shopify_client import ShopifyClient

SEGMENT_ORDERS = {"vip": (10, 20), "repeat": (2, 6), "one_time": (1, 1), "no_purchase": (0, 0)}
MONTH_WEIGHT = {1: 0.8, 2: 0.85, 3: 0.95, 4: 1.0, 5: 1.0, 6: 0.85,
                7: 0.85, 8: 0.9, 9: 1.0, 10: 1.05, 11: 1.6, 12: 1.9}
WEEKDAY_WEIGHT = [0.9, 0.9, 0.95, 1.0, 1.1, 1.3, 1.3]          # Mon..Sun
HOUR_WEIGHT = [2, 1, 1, 1, 1, 1, 2, 3, 4, 5, 5, 6, 6, 6, 6, 6, 7, 8, 9, 10, 10, 9, 6, 4]
BASKET_SIZES, BASKET_W = [1, 2, 3, 4], [0.55, 0.28, 0.12, 0.05]
QTY, QTY_W = [1, 2, 3], [0.85, 0.12, 0.03]
LEGACY_WEIGHT = 0.15          # relative popularity of the original snowboard products
RESTOCK_UNITS = (80, 200)
STOCKOUT_DAYS = (45, 90)

CATALOG_Q = """
query($cursor: String) {
  products(first: 50, after: $cursor, query: "status:active") {
    nodes { id isGiftCard
      variants(first: 50) { nodes {
        id sku price inventoryQuantity inventoryItem { id tracked } } } }
    pageInfo { hasNextPage endCursor }
  }
}"""

ORDER_CREATE = """
mutation orderCreate($order: OrderCreateOrderInput!, $options: OrderCreateOptionsInput) {
  orderCreate(order: $order, options: $options) {
    order { id name }
    userErrors { field message }
  }
}"""

FIND_BY_TAG = """query($q: String!) { orders(first: 1, query: $q) { nodes { id name } } }"""

RESTOCK = """
mutation restock($input: InventoryAdjustQuantitiesInput!, $key: String!) {
  inventoryAdjustQuantities(input: $input) @idempotent(key: $key) {
    inventoryAdjustmentGroup { id }
    userErrors { field message }
  }
}"""


# ---------------- catalog ----------------
def load_catalog(client):
    """Live, sellable variants only: active, not gift cards, has SKU, in stock (if tracked)."""
    meta = {v["key"]: v for v in state.all_of("variant")}
    catalog, cursor = {}, None
    while True:
        data = client.gql(CATALOG_Q, {"cursor": cursor})["products"]
        for p in data["nodes"]:
            if p["isGiftCard"]:
                continue
            for v in p["variants"]["nodes"]:
                sku, tracked = v["sku"], v["inventoryItem"]["tracked"]
                if not sku or sku not in meta:
                    continue
                if tracked and (v["inventoryQuantity"] or 0) <= 0:
                    continue  # e.g. the deliberately out-of-stock test product
                m = meta[sku]
                catalog[sku] = {
                    "variant_id": v["id"], "price": float(v["price"]),
                    "stock": v["inventoryQuantity"] or 0, "tracked": tracked,
                    "inv_item": v["inventoryItem"]["id"],
                    "product_key": m.get("product_key"),
                    "legacy": str(m.get("product_key", "")).startswith("gid://"),
                    "low_stock": m.get("low_stock", False),
                }
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    return catalog


def popularity_weights(catalog, rng):
    """Skewed popularity: a few best-sellers, long tail; legacy products rarely sell."""
    products = sorted({v["product_key"] for v in catalog.values() if not v["legacy"]})
    rng.shuffle(products)
    prod_w = {p: 1 / (rank + 1) ** 0.8 for rank, p in enumerate(products)}
    floor = min(prod_w.values())
    skus = sorted(catalog)
    weights = [floor * LEGACY_WEIGHT if catalog[s]["legacy"] else prod_w[catalog[s]["product_key"]]
               for s in skus]
    return skus, weights


# ---------------- plan ----------------
def day_pool():
    start, end = date.fromisoformat(cfg.ORDER_START), date.fromisoformat(cfg.ORDER_END)
    days, weights, d = [], [], start
    while d <= end:
        days.append(d)
        weights.append(MONTH_WEIGHT[d.month] * WEEKDAY_WEIGHT[d.weekday()])
        d += timedelta(days=1)
    return days, weights


def random_ts(rng, days, weights):
    d = rng.choices(days, weights)[0]
    h = rng.choices(range(24), HOUR_WEIGHT)[0]
    return datetime(d.year, d.month, d.day, h, rng.randint(0, 59), rng.randint(0, 59),
                    tzinfo=timezone.utc)


def build_plan(catalog):
    rng = random.Random(cfg.RANDOM_SEED + 2)
    days, dweights = day_pool()
    skus, sweights = popularity_weights(catalog, rng)
    customers = sorted(state.all_of("customer"), key=lambda c: c["key"])

    orders = []
    for c in customers:
        lo, hi = SEGMENT_ORDERS[c["segment"]]
        for _ in range(rng.randint(lo, hi)):
            orders.append({"customer_key": c["key"], "ts": random_ts(rng, days, dweights)})
    n_guest = round(len(orders) * cfg.GUEST_ORDER_SHARE / (1 - cfg.GUEST_ORDER_SHARE))
    for _ in range(n_guest):
        orders.append({"customer_key": None, "ts": random_ts(rng, days, dweights)})

    orders.sort(key=lambda o: (o["ts"], o["customer_key"] or ""))
    for i, o in enumerate(orders, start=1):
        o["key"] = f"ORD-{i:05d}"
        o["pending"] = rng.random() < cfg.PENDING_ORDER_SHARE
        n_lines = rng.choices(BASKET_SIZES, BASKET_W)[0]
        chosen = []
        while len(chosen) < n_lines:
            s = rng.choices(skus, sweights)[0]
            if s not in chosen:
                chosen.append(s)
        o["lines"] = [(s, rng.choices(QTY, QTY_W)[0]) for s in chosen]
    return orders


def print_plan_stats(plan, catalog):
    guests = sum(o["customer_key"] is None for o in plan)
    months = Counter(o["ts"].strftime("%Y-%m") for o in plan)
    top = Counter(s for o in plan for s, _ in o["lines"]).most_common(5)
    print(f"Planned orders: {len(plan)}  (guests: {guests}, pending: {sum(o['pending'] for o in plan)})")
    print(f"Sellable variants: {len(catalog)}")
    print("Orders by month:", dict(sorted(months.items())))
    print("Top 5 SKUs by order lines:", top)
    print(f"Estimated run time at {cfg.ORDERS_PER_MINUTE}/min: "
          f"{len(plan) / cfg.ORDERS_PER_MINUTE / 60:.1f} hours")


# ---------------- execution ----------------
def restock(client, sku, v, location_id, order_key):
    units = random.Random(f"{cfg.RANDOM_SEED}-{sku}-{order_key}").randint(*RESTOCK_UNITS)
    res = client.gql(RESTOCK, {
        "key": f"restock-{sku}-{order_key}",   # same key on retry -> applied once
        "input": {"reason": "received", "name": "available", "changes": [{
            "inventoryItemId": v["inv_item"], "locationId": location_id,
            "delta": units, "changeFromQuantity": None,   # single writer: opt out of compare-and-swap
        }]},
    })["inventoryAdjustQuantities"]
    if res["userErrors"]:
        raise RuntimeError(f"restock {sku}: {res['userErrors']}")
    v["stock"] += units
    print(f"    restocked {sku} +{units}")


def resolve_lines(client, o, catalog, stockouts, location_id):
    """Apply stock rules; returns the lines that can actually be sold."""
    lines = []
    for sku, qty in o["lines"]:
        v = catalog.get(sku)
        if not v:
            continue
        if v["tracked"] and v["stock"] < qty:
            rec = stockouts.get(sku)
            if v["low_stock"] and not (rec and rec.get("restocked")):
                if rec is None:
                    days = random.Random(f"{cfg.RANDOM_SEED}-{sku}").randint(*STOCKOUT_DAYS)
                    rec = {"out_since": o["ts"].isoformat(),
                           "restock_on": (o["ts"] + timedelta(days=days)).isoformat()}
                    state.record("stockout", sku, sku, rec)
                    stockouts[sku] = rec
                    print(f"    STOCKOUT {sku} on {o['ts']:%Y-%m-%d}, back {rec['restock_on'][:10]}")
                if o["ts"] < datetime.fromisoformat(rec["restock_on"]):
                    continue  # still out of stock -> lost sale
                restock(client, sku, v, location_id, o["key"])
                rec = {**rec, "restocked": True}
                state.record("stockout", sku, sku, rec)
                stockouts[sku] = rec
            else:
                restock(client, sku, v, location_id, o["key"])
        lines.append((sku, qty))
    return lines


def create_order(client, o, lines, catalog, customer_ids):
    ts = o["ts"].strftime("%Y-%m-%dT%H:%M:%SZ")
    order = {
        "processedAt": ts,
        "financialStatus": "PENDING" if o["pending"] else "PAID",
        "tags": [cfg.SEED_TAG, f"seedkey-{o['key']}"],
        "lineItems": [{"variantId": catalog[s]["variant_id"], "quantity": q} for s, q in lines],
    }
    if o["customer_key"]:
        order["customer"] = {"toAssociate": {"id": customer_ids[o["customer_key"]]}}
    options = {"sendReceipt": False, "sendFulfillmentReceipt": False,
               "inventoryBehaviour": "DECREMENT_IGNORING_POLICY"}
    res = client.gql(ORDER_CREATE, {"order": order, "options": options})["orderCreate"]
    if res["userErrors"]:
        raise RuntimeError(f"{o['key']}: {res['userErrors']}")
    return res["order"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print plan stats only")
    ap.add_argument("--limit", type=int, default=None, help="create at most N new orders")
    args = ap.parse_args()

    client = ShopifyClient()
    catalog = load_catalog(client)
    plan = build_plan(catalog)
    print_plan_stats(plan, catalog)
    if args.dry_run:
        return

    location_id = client.gql("{ locations(first: 1) { nodes { id } } }")["locations"]["nodes"][0]["id"]
    customer_ids = {c["key"]: c["id"] for c in state.all_of("customer")}
    stockouts = {s["key"]: s for s in state.all_of("stockout")}
    interval = 60 / cfg.ORDERS_PER_MINUTE
    checked_crash_window = False
    created = skipped = 0
    last_create = 0.0

    for o in plan:
        if args.limit is not None and created >= args.limit:
            break
        if state.get("order", o["key"]):
            continue

        # Crash safety: the first unlogged order may already exist in Shopify
        if not checked_crash_window:
            checked_crash_window = True
            found = client.gql(FIND_BY_TAG, {"q": f"tag:'seedkey-{o['key']}'"})["orders"]["nodes"]
            if found:
                print(f"  {o['key']} already in Shopify as {found[0]['name']} -> logging, not recreating")
                state.record("order", o["key"], found[0]["id"], {"recovered": True})
                continue

        lines = resolve_lines(client, o, catalog, stockouts, location_id)
        if not lines:
            state.record("order", o["key"], "SKIPPED", {"reason": "all items out of stock"})
            skipped += 1
            continue

        wait = interval - (time.time() - last_create)
        if wait > 0:
            time.sleep(wait)
        result = create_order(client, o, lines, catalog, customer_ids)
        last_create = time.time()

        for s, q in lines:
            if catalog[s]["tracked"]:
                catalog[s]["stock"] -= q
        state.record("order", o["key"], result["id"], {
            "name": result["name"], "processed_at": o["ts"].isoformat(),
            "customer_key": o["customer_key"], "pending": o["pending"],
            "lines": [{"sku": s, "qty": q, "price": catalog[s]["price"]} for s, q in lines],
        })
        created += 1
        who = o["customer_key"] or "GUEST"
        print(f"  {o['key']} {result['name']} {o['ts']:%Y-%m-%d} {who} lines={len(lines)}"
              f"{' PENDING' if o['pending'] else ''}")

    done = len(state.all_of("order"))
    print(f"\nThis run: {created} created, {skipped} skipped (stockout). "
          f"Progress: {done}/{len(plan)} orders logged.")


if __name__ == "__main__":
    main()