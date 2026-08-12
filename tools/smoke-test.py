#!/usr/bin/env python3
"""
Render every template and fail on Liquid errors.

`shopify theme check` is a linter. It validates each file in isolation and is
blind to whole classes of failure that only appear when Liquid actually runs:
a filter chain inside a tag argument, a template whose section renders from
blocks it never defines, a missing snippet, a bad object path. Both of those
shipped to a live store in this project because a clean lint was mistaken for
a working page.

This fetches real rendered HTML for every template and greps for the error
banner Shopify injects, plus a few structural assertions per page type.

Point it at a local dev server (no store password needed by this script — the
server handles it):

    shopify theme dev --store <store>.myshopify.com --store-password '<pw>'
    python3 tools/smoke-test.py

Or at any reachable origin:

    python3 tools/smoke-test.py --base https://127.0.0.1:9292
"""

import argparse
import re
import sys
import urllib.error
import urllib.request

# Shopify renders this inline where a section blew up, with a 200 status —
# which is exactly why a status-code check is not enough.
LIQUID_ERROR = re.compile(r'Liquid error[^<]*|Liquid syntax error[^<]*', re.I)

# (path, description, [(regex, what it proves)])
CHECKS = [
    ('/', 'home', [
        (r'class="[^"]*header', 'header renders'),
        (r'class="[^"]*hero', 'hero section renders'),
        (r'class="[^"]*footer', 'footer renders'),
    ]),
    ('/collections/all', 'collection', [
        (r'class="[^"]*product-grid', 'product grid renders'),
        (r'class="[^"]*card__title', 'product cards render'),
    ]),
    ('/collections/girls', 'collection (girls)', [
        (r'class="[^"]*card__title', 'product cards render'),
    ]),
    ('/cart', 'cart', [
        (r'class="[^"]*cart-page', 'cart page renders'),
    ]),
    ('/search?q=dress', 'search', [
        (r'class="[^"]*search-page', 'search page renders'),
    ]),
    ('/pages/nonexistent-page-for-404', '404', [
        (r'class="[^"]*notfound', '404 section renders'),
    ]),
]

# The product page is the one that broke twice, so it gets the most assertions.
PRODUCT_CHECKS = [
    (r'class="[^"]*product__title', 'title block'),
    (r'class="[^"]*price', 'price block'),
    (r'name="add"', 'add to cart button'),
    (r'class="[^"]*variants__swatch|has_only_default', 'variant picker or single-variant'),
    (r'class="[^"]*gallery', 'media gallery'),
]


def fetch(base, path, timeout=30):
    url = base.rstrip('/') + path
    req = urllib.request.Request(url, headers={'User-Agent': 'pinafore-smoke/1.0'})
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='ignore')
    except Exception as exc:
        return None, str(exc)


def check_page(base, path, label, assertions):
    status, body = fetch(base, path)
    if status is None:
        print(f'  FAIL  {label:22} unreachable: {body[:70]}')
        return False

    ok = True

    errors = LIQUID_ERROR.findall(body)
    if errors:
        ok = False
        print(f'  FAIL  {label:22} {len(errors)} Liquid error(s), HTTP {status}')
        for e in dict.fromkeys(errors[:3]):
            print(f'          {e.strip()[:150]}')

    if status >= 500:
        ok = False
        print(f'  FAIL  {label:22} HTTP {status}')

    missing = [why for rx, why in assertions if not re.search(rx, body)]
    if missing:
        ok = False
        print(f'  FAIL  {label:22} missing: {", ".join(missing)}')

    if ok:
        print(f'  ok    {label:22} HTTP {status}, {len(body):,} bytes, '
              f'{len(assertions)} assertions')
    return ok


def first_product_path(base):
    """Find a real product URL from the collection page."""
    _, body = fetch(base, '/collections/all')
    m = re.search(r'href="(/products/[^"?#]+)"', body or '')
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:9292')
    a = ap.parse_args()

    print(f'Smoke testing {a.base}\n')

    status, _ = fetch(a.base, '/')
    if status is None:
        print('  Server unreachable. Start it with:\n'
              "    shopify theme dev --store <store>.myshopify.com --store-password '<pw>'")
        return 2

    results = [check_page(a.base, p, label, checks) for p, label, checks in CHECKS]

    product_path = first_product_path(a.base)
    if product_path:
        results.append(check_page(a.base, product_path, 'product', PRODUCT_CHECKS))
    else:
        print('  WARN  product               no product link found on /collections/all')

    failed = results.count(False)
    print(f'\n{len(results) - failed}/{len(results)} pages passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
