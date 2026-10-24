"""GraphQL queries used by the extractor.

Design notes:
  - Incremental entities take a search string ($q) like
    "updated_at:>='2026-10-01T00:00:00Z' AND updated_at:<='2026-10-02T00:00:00Z'"
    and are sorted by UPDATED_AT.
  - No PII is requested: customers are extracted by ID and behavior only
    (no names, emails, phones, or addresses).
  - Nested lists have limits (e.g. lineItems first: 10). Each query asks for the
    nested pageInfo so the extractor can WARN if a list was truncated, instead of
    silently dropping data.
"""

ORDERS = """
query($first: Int!, $after: String, $q: String) {
  orders(first: $first, after: $after, query: $q, sortKey: UPDATED_AT) {
    nodes {
      id name createdAt updatedAt processedAt cancelledAt closedAt
      displayFinancialStatus displayFulfillmentStatus currencyCode tags test
      subtotalPriceSet  { shopMoney { amount currencyCode } }
      totalDiscountsSet { shopMoney { amount } }
      totalTaxSet       { shopMoney { amount } }
      totalPriceSet     { shopMoney { amount } }
      totalRefundedSet  { shopMoney { amount } }
      customer { id }
      lineItems(first: 10) {
        nodes {
          id sku name quantity
          variant { id }
          product { id }
          originalUnitPriceSet { shopMoney { amount } }
          discountedTotalSet   { shopMoney { amount } }
        }
        pageInfo { hasNextPage }
      }
      refunds(first: 3) {
        id createdAt processedAt note
        totalRefundedSet { shopMoney { amount } }
        refundLineItems(first: 10) {
          nodes {
            quantity restockType
            lineItem { id sku }
            subtotalSet { shopMoney { amount } }
          }
          pageInfo { hasNextPage }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""

PRODUCTS = """
query($first: Int!, $after: String, $q: String) {
  products(first: $first, after: $after, query: $q, sortKey: UPDATED_AT) {
    nodes {
      id title handle productType vendor status tags isGiftCard createdAt updatedAt
      variants(first: 20) {
        nodes {
          id sku title price compareAtPrice createdAt updatedAt
          inventoryItem { id tracked unitCost { amount } }
        }
        pageInfo { hasNextPage }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""

CUSTOMERS = """
query($first: Int!, $after: String, $q: String) {
  customers(first: $first, after: $after, query: $q, sortKey: UPDATED_AT) {
    nodes {
      id createdAt updatedAt state tags numberOfOrders
      amountSpent { amount currencyCode }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""

# Full snapshot every run (inventory levels have no reliable updated_at)
INVENTORY = """
query($first: Int!, $after: String, $q: String) {
  productVariants(first: $first, after: $after, query: $q) {
    nodes {
      id sku
      product { id }
      inventoryItem {
        id tracked
        inventoryLevels(first: 5) {
          nodes {
            location { id name }
            quantities(names: ["available", "on_hand", "committed"]) { name quantity }
          }
          pageInfo { hasNextPage }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""