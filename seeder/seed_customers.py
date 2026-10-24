"""Seeder step 2: customers.

Creates N_CUSTOMERS fake customers (example.com emails) and assigns each a hidden
segment stored ONLY in the local state DB -- the order generator uses it to decide
how often each customer buys. The segment is never written to Shopify, so the
pipeline has to discover behavior from the orders, like it would in a real company.

Segments:  vip (many orders) | repeat (2-5 orders) | one_time (1 order)
           | no_purchase (signed up, never bought)

Resumable: already-created customers are skipped. If a run crashed after Shopify
created a customer but before we logged it, the duplicate-email error is caught and
the existing customer is looked up and logged instead.

Run from the project root:  python -m seeder.seed_customers
"""
import random
from seeder import config as cfg, state
from seeder.shopify_client import ShopifyClient

NO_PURCHASE_SHARE = getattr(cfg, "NO_PURCHASE_SHARE", 0.10)

FIRST = ["Aarav", "Maya", "Liam", "Sofia", "Noah", "Priya", "Ethan", "Zara", "Lucas", "Ana",
         "Mateo", "Chloe", "Arjun", "Emma", "Kenji", "Leila", "Omar", "Grace", "Diego", "Nina",
         "Ravi", "Hannah", "Yusuf", "Isla", "Marcus", "Mei", "Samuel", "Aisha", "Leo", "Clara"]
LAST = ["Patel", "Garcia", "Kim", "Nguyen", "Smith", "Rao", "Johnson", "Lopez", "Chen", "Brown",
        "Singh", "Martinez", "Williams", "Khan", "Davis", "Tanaka", "Silva", "Murphy", "Ali", "Moore"]

CUSTOMER_CREATE = """
mutation customerCreate($input: CustomerInput!) {
  customerCreate(input: $input) {
    customer { id }
    userErrors { field message }
  }
}"""

FIND_BY_EMAIL = """
query($q: String!) { customers(first: 1, query: $q) { nodes { id } } }"""


def pick_segment(rng):
    r = rng.random()
    vip = cfg.VIP_SHARE
    repeat = cfg.REPEAT_CUSTOMER_SHARE - cfg.VIP_SHARE   # VIPs are a subset of repeat buyers
    if r < vip:
        return "vip"
    if r < vip + repeat:
        return "repeat"
    if r < vip + repeat + NO_PURCHASE_SHARE:
        return "no_purchase"
    return "one_time"


def build_specs(rng):
    specs = []
    for n in range(1, cfg.N_CUSTOMERS + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        specs.append({
            "key": f"CUST-{n:04d}",
            "first": first,
            "last": last,
            "email": f"{first.lower()}.{last.lower()}.{n}@example.com",
            "segment": pick_segment(rng),
        })
    return specs


def create_customer(client, spec):
    data = client.gql(CUSTOMER_CREATE, {"input": {
        "firstName": spec["first"],
        "lastName": spec["last"],
        "email": spec["email"],
        "tags": [cfg.SEED_TAG],
    }})["customerCreate"]

    if not data["userErrors"]:
        return data["customer"]["id"]

    # Idempotency: customer exists in Shopify but wasn't logged locally (earlier crash)
    if any("taken" in e["message"].lower() for e in data["userErrors"]):
        found = client.gql(FIND_BY_EMAIL, {"q": f"email:{spec['email']}"})["customers"]["nodes"]
        if found:
            return found[0]["id"]
    raise RuntimeError(f"{spec['key']}: {data['userErrors']}")


def main():
    rng = random.Random(cfg.RANDOM_SEED + 1)   # separate stream from products
    client = ShopifyClient()
    specs = build_specs(rng)
    created = skipped = 0

    print(f"== Step 2: customers ({len(specs)}) ==")
    for spec in specs:
        if state.get("customer", spec["key"]):
            skipped += 1
            continue
        cid = create_customer(client, spec)
        state.record("customer", spec["key"], cid, {"segment": spec["segment"]})
        created += 1
        if created % 50 == 0:
            print(f"  {created} created...")

    counts = {}
    for c in state.all_of("customer"):
        counts[c["segment"]] = counts.get(c["segment"], 0) + 1
    print(f"Customers: {created} created, {skipped} already existed")
    print("Segment mix (hidden, local only):", counts)


if __name__ == "__main__":
    main()