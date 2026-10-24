"""Small reusable Shopify GraphQL client.

Handles: token refresh (24h tokens), cost-based throttling, 429/5xx retries with
exponential backoff + jitter, and GraphQL errors hidden inside HTTP 200 responses.
"""
import os, time, json, random, requests
from dotenv import load_dotenv
from seeder.config import API_VERSION

MIN_BUDGET = 200  # pause if fewer query-cost points than this remain


class GraphQLError(Exception):
    pass


class ShopifyClient:
    def __init__(self):
        load_dotenv()
        self.shop = os.environ["SHOP"].strip()
        self.url = f"https://{self.shop}/admin/api/{API_VERSION}/graphql.json"
        self._token = None
        self._token_expires = 0

    # ---- auth ----
    def _refresh_token(self):
        r = requests.post(f"https://{self.shop}/admin/oauth/access_token", data={
            "grant_type": "client_credentials",
            "client_id": os.environ["SHOPIFY_CLIENT_ID"].strip(),
            "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"].strip(),
        }, timeout=30)
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        # refresh 5 minutes before expiry
        self._token_expires = time.time() + int(body.get("expires_in", 86400)) - 300

    @property
    def token(self):
        if not self._token or time.time() >= self._token_expires:
            self._refresh_token()
        return self._token

    # ---- requests ----
    @staticmethod
    def _backoff(attempt):
        return min(60, 2 ** attempt) + random.uniform(0, 1)  # exponential + jitter

    def gql(self, query, variables=None, max_retries=6):
        for attempt in range(max_retries):
            try:
                r = requests.post(self.url, timeout=60,
                                  headers={"X-Shopify-Access-Token": self.token},
                                  json={"query": query, "variables": variables or {}})
            except requests.RequestException as e:
                wait = self._backoff(attempt)
                print(f"  network error ({e}); retrying in {wait:.1f}s")
                time.sleep(wait)
                continue

            if r.status_code == 401:          # token expired early -> refresh and retry
                self._token = None
                continue
            if r.status_code == 429 or r.status_code >= 500:
                wait = self._backoff(attempt)
                print(f"  HTTP {r.status_code}; retrying in {wait:.1f}s")
                time.sleep(wait)
                continue
            r.raise_for_status()

            body = r.json()
            errors = body.get("errors") or []
            if any(e.get("extensions", {}).get("code") == "THROTTLED" for e in errors):
                wait = self._backoff(attempt)
                print(f"  throttled; retrying in {wait:.1f}s")
                time.sleep(wait)
                continue
            if errors:  # GraphQL can fail inside an HTTP 200
                raise GraphQLError(json.dumps(errors, indent=2))

            self._respect_budget(body)
            return body["data"]

        raise GraphQLError(f"Gave up after {max_retries} retries")

    @staticmethod
    def _respect_budget(body):
        ts = body.get("extensions", {}).get("cost", {}).get("throttleStatus")
        if ts and ts["currentlyAvailable"] < MIN_BUDGET:
            wait = (MIN_BUDGET - ts["currentlyAvailable"]) / ts["restoreRate"]
            time.sleep(wait)

