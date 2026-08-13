#!/usr/bin/env python3
"""
Thin Admin GraphQL client that reuses the Shopify CLI's own stored sessions.

`shopify store auth` writes an access token per store into the CLI's config.
Reading it from there means no second credential to manage and no scope the
user did not already approve in the browser: whatever the CLI was granted is
exactly what these scripts can do.

Going direct rather than shelling out to `shopify store execute` matters at
this scale — a CLI round trip is seconds, and the catalog migration is
hundreds of mutations. It also gives access to the response `extensions`,
which is the only way to throttle correctly against the leaky bucket instead
of guessing at a sleep.
"""

import json
import pathlib
import time
import urllib.error
import urllib.request

API_VERSION = '2026-07'
CLI_CONFIG = pathlib.Path.home() / '.config/shopify-cli-store-nodejs/config.json'


def load_tokens():
    """Map of `store.myshopify.com` -> access token, from the CLI's session store."""
    if not CLI_CONFIG.exists():
        raise SystemExit(
            f'No Shopify CLI sessions at {CLI_CONFIG}.\n'
            'Run: shopify store auth --store <store>.myshopify.com --scopes ...'
        )
    tokens = {}
    for key, entry in json.loads(CLI_CONFIG.read_text()).items():
        domain = key.split('::')[-1]
        for session in (entry.get('sessionsByUserId') or {}).values():
            if session.get('accessToken'):
                tokens[domain] = session['accessToken']
    return tokens


class Store:
    def __init__(self, domain, tokens=None):
        tokens = tokens or load_tokens()
        if domain not in tokens:
            raise SystemExit(
                f'Not authenticated against {domain}.\n'
                f'Run: shopify store auth --store {domain} --scopes ...'
            )
        self.domain = domain
        self.token = tokens[domain]
        self.url = f'https://{domain}/admin/api/{API_VERSION}/graphql.json'

    def __call__(self, query, variables=None, tries=4):
        """
        Run one operation, retrying on throttling and transient 5xx.

        Returns the `data` object. GraphQL `errors` and any `userErrors` are
        left for the caller to inspect — a mutation that half-succeeds is a
        real outcome in a migration and should not be swallowed.
        """
        body = json.dumps({'query': query, 'variables': variables or {}}).encode()
        for attempt in range(tries):
            req = urllib.request.Request(
                self.url,
                data=body,
                headers={
                    'X-Shopify-Access-Token': self.token,
                    'Content-Type': 'application/json',
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as response:
                    payload = json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < tries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

            errors = payload.get('errors') or []
            throttled = any(
                (e.get('extensions') or {}).get('code') == 'THROTTLED' for e in errors
            )
            if throttled and attempt < tries - 1:
                time.sleep(2 + 2 * attempt)
                continue

            self._respect_budget(payload)
            if errors and payload.get('data') is None:
                raise RuntimeError(json.dumps(errors)[:800])
            return payload.get('data') or {}
        raise RuntimeError('exhausted retries')

    @staticmethod
    def _respect_budget(payload):
        """
        Pause before the bucket runs dry rather than after.

        Waiting for a 429 costs a wasted request and a full retry; reading the
        remaining points costs nothing and keeps a long import at a steady rate.
        """
        cost = (payload.get('extensions') or {}).get('cost') or {}
        status = cost.get('throttleStatus') or {}
        available = status.get('currentlyAvailable')
        restore = status.get('restoreRate') or 50
        requested = cost.get('requestedQueryCost') or 0
        if available is not None and available < max(requested * 2, 200):
            time.sleep(min(4.0, (max(requested * 2, 200) - available) / restore))
