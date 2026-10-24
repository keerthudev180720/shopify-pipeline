from seeder.shopify_client import ShopifyClient
q = """{ node(id: "gid://shopify/Refund/986861863009") {
     ... on Refund { processedAt createdAt } } }"""
print(ShopifyClient().gql(q))