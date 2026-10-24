"""All seeder settings in one place. Change numbers here, not in the scripts."""

RANDOM_SEED = 42            # same seed -> same generated data every run
API_VERSION = "2026-07"
SEED_TAG = "seeded"         # every record the seeder creates gets this tag
VENDOR = "Keer Goods"

# ---------- Products ----------
PRODUCTS_PER_CATEGORY = 6
ADJECTIVES = ["Classic", "Urban", "Everyday", "Premium", "Trail", "Studio"]

CATEGORIES = {
    "Apparel": {
        "prefix": "APP", "price": (25, 90), "margin": (0.45, 0.60),
        "option": ("Size", ["S", "M", "L"]),
        "nouns": ["Hoodie", "T-Shirt", "Joggers", "Jacket", "Crewneck", "Shorts"],
    },
    "Footwear": {
        "prefix": "FTW", "price": (60, 180), "margin": (0.40, 0.55),
        "option": ("Size", ["7", "8", "9", "10"]),
        "nouns": ["Sneakers", "Runners", "Slides", "Boots", "Trainers", "Loafers"],
    },
    "Accessories": {
        "prefix": "ACC", "price": (15, 60), "margin": (0.55, 0.70),
        "option": ("Color", ["Black", "Tan"]),
        "nouns": ["Backpack", "Cap", "Belt", "Wallet", "Tote", "Beanie"],
    },
    "Home": {
        "prefix": "HOM", "price": (20, 120), "margin": (0.50, 0.65),
        "option": ("Style", ["Standard"]),
        "nouns": ["Candle", "Throw Blanket", "Mug Set", "Planter", "Lamp", "Cushion"],
    },
    "Electronics": {
        "prefix": "ELE", "price": (40, 250), "margin": (0.25, 0.40),
        "option": ("Color", ["Black", "White"]),
        "nouns": ["Earbuds", "Speaker", "Charger", "Smartwatch", "Power Bank", "Keyboard"],
    },
}

INITIAL_STOCK = (40, 200)       # units per variant at start
LOW_STOCK = (3, 10)             # units for the few products meant to stock out
N_RETURN_PRONE_PRODUCTS = 4     # products with unusually high refund rates
N_LOW_STOCK_PRODUCTS = 3        # products that will run out mid-year
LEGACY_SKU_PREFIX = "LEG"       # SKUs assigned to the store's original test products
LEGACY_COST_RATIO = 0.5         # assumed cost = 50% of price for original products

# ---------- Customers / orders (used by later steps) ----------
N_CUSTOMERS = 800
N_ORDERS = 3000
ORDER_START = "2025-10-01"
ORDER_END = "2026-09-28"
REPEAT_CUSTOMER_SHARE = 0.30
VIP_SHARE = 0.05
GUEST_ORDER_SHARE = 0.10
PENDING_ORDER_SHARE = 0.03
REFUND_RATE = 0.06              # baseline; return-prone products get ~4x
ORDERS_PER_MINUTE = 4           # dev stores allow max 5/min; stay under it