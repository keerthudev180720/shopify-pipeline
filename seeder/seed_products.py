"""Seeder step 1: products.

1. Creates PRODUCTS_PER_CATEGORY products per category (with variants, SKUs, cost, stock).
2. Flags a few products as return-prone and a few as low-stock (used by later steps).
3. Adds SKUs + cost to the store's original test products that have none.

Resumable: already-created products are skipped on rerun.
Run from the project root:  python -m seeder.seed_products
"""
import random
from seeder import config as cfg, state
from seeder.shopify_client import ShopifyClient

PRODUCT_SET = """
mutation productSet($input: ProductSetInput!) {
  productSet(synchronous: true, input: $input) {
    product {
      id
      variants(first: 10) { nodes { id sku price } }
    }
    userErrors { field message code }
  }
}"""

VARIANTS_BULK_UPDATE = """
mutation update($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id sku }
    userErrors { field message }
  }
}"""


def build_specs(rng):
    """Deterministically generate product definitions from config."""
    specs = []
    for category, c in cfg.CATEGORIES.items():
        for i, noun in enumerate(c["nouns"][:cfg.PRODUCTS_PER_CATEGORY], start=1):
            price = round(rng.uniform(*c["price"])) - 0.01          # e.g. 59.99
            cost = round(price * (1 - rng.uniform(*c["margin"])), 2)
            specs.append({
                "key": f"{c['prefix']}-{i:03d}",
                "title": f"{rng.choice(cfg.ADJECTIVES)} {noun}",
                "category": category,
                "price": price,
                "cost": cost,
                "option": c["option"],
            })
    keys = [s["key"] for s in specs]
    return_prone = set(rng.sample(keys, cfg.N_RETURN_PRONE_PRODUCTS))
    low_stock = set(rng.sample(sorted(set(keys) - return_prone), cfg.N_LOW_STOCK_PRODUCTS))
    for s in specs:
        s["return_prone"] = s["key"] in return_prone
        s["low_stock"] = s["key"] in low_stock
    return specs


def get_location_id(client):
    data = client.gql("{ locations(first: 1) { nodes { id name } } }")
    loc = data["locations"]["nodes"][0]
    print(f"Stocking inventory at location: {loc['name']}")
    return loc["id"]


def create_product(client, spec, location_id, rng):
    opt_name, opt_values = spec["option"]
    stock_range = cfg.LOW_STOCK if spec["low_stock"] else cfg.INITIAL_STOCK
    variants = []
    for v in opt_values:
        variants.append({
            "optionValues": [{"optionName": opt_name, "name": v}],
            "price": f"{spec['price']:.2f}",
            "inventoryItem": {
                "sku": f"{spec['key']}-{v.upper().replace(' ', '')}",
                "cost": f"{spec['cost']:.2f}",
                "tracked": True,
            },
            "inventoryQuantities": [{
                "locationId": location_id, "name": "available",
                "quantity": rng.randint(*stock_range),
            }],
        })

    product_input = {
        "title": spec["title"],
        "productType": spec["category"],
        "vendor": cfg.VENDOR,
        "status": "ACTIVE",
        "tags": [cfg.SEED_TAG, spec["category"].lower()],
        "productOptions": [{"name": opt_name, "values": [{"name": v} for v in opt_values]}],
        "variants": variants,
    }
    result = client.gql(PRODUCT_SET, {"input": product_input})["productSet"]
    if result["userErrors"]:
        raise RuntimeError(f"{spec['key']}: {result['userErrors']}")
    return result["product"]


def seed_new_products(client, rng):
    specs = build_specs(rng)
    location_id = get_location_id(client)
    created = skipped = 0

    for spec in specs:
        if state.get("product", spec["key"]):
            skipped += 1
            continue
        product = create_product(client, spec, location_id, rng)
        meta = {k: spec[k] for k in ("title", "category", "price", "cost", "return_prone", "low_stock")}
        state.record("product", spec["key"], product["id"], meta)
        for v in product["variants"]["nodes"]:
            state.record("variant", v["sku"], v["id"], {"product_key": spec["key"], **meta})
        created += 1
        flags = " [return-prone]" if spec["return_prone"] else ""
        flags += " [low-stock]" if spec["low_stock"] else ""
        print(f"  created {spec['key']}: {spec['title']} (${spec['price']:.2f}){flags}")

    print(f"New products: {created} created, {skipped} already existed")


def backfill_legacy_skus(client):
    """Give the store's original test products SKUs + cost so every variant is analyzable."""
    data = client.gql(f"""{{
      products(first: 100, query: "-tag:{cfg.SEED_TAG}") {{
        nodes {{ id title productType isGiftCard
          variants(first: 50) {{ nodes {{ id sku price }} }} }}
      }}
    }}""")
    n = len(state.all_of("legacy_variant"))
    updated = 0

    for p in data["products"]["nodes"]:
        if p["isGiftCard"]:
            continue  # gift cards aren't real merchandise; exclude from analysis
        updates = []
        for v in p["variants"]["nodes"]:
            if state.get("legacy_variant", v["id"]):
                continue
            n += 1
            sku = v["sku"] or f"{cfg.LEGACY_SKU_PREFIX}-{n:03d}"
            cost = round(float(v["price"]) * cfg.LEGACY_COST_RATIO, 2)
            updates.append({"id": v["id"], "inventoryItem": {"sku": sku, "cost": f"{cost:.2f}"}})
            meta = {"title": p["title"], "category": p["productType"] or "Legacy",
                    "price": float(v["price"]), "cost": cost,
                    "return_prone": False, "low_stock": False, "sku": sku}
            state.record("legacy_variant", v["id"], v["id"], meta)
            state.record("variant", sku, v["id"], {"product_key": p["id"], **meta})
        if updates:
            res = client.gql(VARIANTS_BULK_UPDATE,
                             {"productId": p["id"], "variants": updates})["productVariantsBulkUpdate"]
            if res["userErrors"]:
                raise RuntimeError(f"{p['title']}: {res['userErrors']}")
            updated += len(updates)
            print(f"  SKUs set on '{p['title']}' ({len(updates)} variants)")

    print(f"Legacy variants updated: {updated}")


def main():
    rng = random.Random(cfg.RANDOM_SEED)
    client = ShopifyClient()
    print("== Step 1a: new products ==")
    seed_new_products(client, rng)
    print("\n== Step 1b: SKUs for original products ==")
    backfill_legacy_skus(client)
    print(f"\nTotal sellable variants tracked: {len(state.all_of('variant'))}")


if __name__ == "__main__":
    main()