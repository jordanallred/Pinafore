#!/usr/bin/env python3
"""
Copy the catalog from the earlier Little Monkey Toes Shopify store into the
theme development store.

That store was built during an abandoned Hydrogen attempt, and the storefront
it powered was thrown away — but the import behind it was not. It holds 351
products with size runs already collapsed into variants, real SKUs, live
inventory counts, Shopify taxonomy categories, product types and tags. All of
that is strictly better than anything recoverable by scraping the live
BigCommerce storefront, which can only report whether a size is in stock, never
how many.

Everything moves in a single `productSet` per product. That mutation is the
only one that creates the product, its media, its options, its variants, the
variant-to-image association and the inventory levels together — which matters
because associating a variant with an image after the fact is the step that has
silently failed here before.

    shopify store auth --store <source>.myshopify.com --scopes read_products,read_inventory
    shopify store auth --store <target>.myshopify.com --scopes write_products,write_inventory,write_files

    python3 tools/migrate-catalog.py --dry-run
    python3 tools/migrate-catalog.py --wipe
"""

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from shopify_api import Store  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = 'rfxmnn-1v.myshopify.com'
TARGET = 'pinafore-bv80ud01.myshopify.com'


# ---------------------------------------------------------------- extraction

EXPORT_QUERY = """
{
  products {
    edges {
      node {
        id title handle vendor productType tags status descriptionHtml
        category { id fullName }
        options { name position optionValues { name } }
        media { edges { node { ... on MediaImage { id alt image { url } } } } }
        variants {
          edges {
            node {
              id title sku price compareAtPrice barcode
              inventoryQuantity inventoryPolicy
              image { url }
              selectedOptions { name value }
            }
          }
        }
      }
    }
  }
}
"""

BULK_RUN = """
mutation ($query: String!) {
  bulkOperationRunQuery(query: $query) {
    bulkOperation { id status }
    userErrors { field message }
  }
}
"""

BULK_POLL = """
{ currentBulkOperation(type: QUERY) { id status errorCode objectCount url } }
"""


def export_source(source, cache):
    """Pull the whole source catalog through one bulk operation."""
    if cache.exists():
        print(f'Using cached export at {cache}')
        return json.loads(cache.read_text())

    print(f'Starting bulk export from {source.domain} ...')
    result = source(BULK_RUN, {'query': EXPORT_QUERY})
    errors = result['bulkOperationRunQuery']['userErrors']
    if errors:
        raise SystemExit(f'Bulk export rejected: {errors}')

    while True:
        time.sleep(3)
        op = source(BULK_POLL)['currentBulkOperation']
        if op['status'] in ('COMPLETED', 'FAILED', 'CANCELED'):
            break
        print(f'  {op["status"]} ({op.get("objectCount") or 0} objects)')
    if op['status'] != 'COMPLETED':
        raise SystemExit(f'Bulk export {op["status"]}: {op.get("errorCode")}')

    import urllib.request

    with urllib.request.urlopen(op['url']) as response:
        lines = response.read().decode().splitlines()

    products = reassemble(lines)
    cache.write_text(json.dumps(products, indent=1))
    print(f'  exported {len(products)} products to {cache}')
    return products


def reassemble(lines):
    """
    Rebuild nested objects from bulk JSONL.

    Bulk results are flat: children carry `__parentId` and arrive after their
    parent. Media and variants are told apart by shape rather than by order,
    since nothing in the format labels which connection a child came from.
    """
    products, children = {}, {}
    for line in lines:
        if not line.strip():
            continue
        node = json.loads(line)
        parent = node.get('__parentId')
        if parent:
            children.setdefault(parent, []).append(node)
        else:
            products[node['id']] = node
    for pid, product in products.items():
        kids = children.get(pid, [])
        product['media'] = [k for k in kids if 'selectedOptions' not in k]
        product['variants'] = [k for k in kids if 'selectedOptions' in k]
    return list(products.values())


# ------------------------------------------------------------------ cleaning

# The old store's descriptions were written by a bulk importer that wrapped
# every body in a snapshot of the then-current theme's section markup. What we
# want is the paragraph the vendor actually wrote, not a fossil of a theme
# that no longer exists.
DESCRIPTION_SHELL = re.compile(
    r'<div class="product-single__description rte">(.*?)</div>', re.S
)
STRIPPED_TAGS = re.compile(r'</?(?:div|section|span)\b[^>]*>')


def clean_description(html):
    if not html:
        return ''
    inner = DESCRIPTION_SHELL.search(html)
    if inner:
        html = inner.group(1)
    html = STRIPPED_TAGS.sub('', html)
    return re.sub(r'\n{3,}', '\n\n', html).strip()


def build_input(product, location_id, status_mode):
    """Turn one exported product into a single `ProductSetInput`."""
    files, seen = [], set()

    def add_file(url, alt):
        if url and url not in seen:
            seen.add(url)
            files.append(
                {'originalSource': url, 'contentType': 'IMAGE', 'alt': alt or ''}
            )

    for media in product['media']:
        add_file((media.get('image') or {}).get('url'), media.get('alt'))
    for variant in product['variants']:
        add_file((variant.get('image') or {}).get('url'), product['title'])

    options = [
        {
            'name': option['name'],
            'position': option['position'],
            'values': [{'name': value['name']} for value in option['optionValues']],
        }
        for option in product['options']
    ]

    variants = []
    for variant in product['variants']:
        entry = {
            'optionValues': [
                {'optionName': selected['name'], 'name': selected['value']}
                for selected in variant['selectedOptions']
            ],
            'price': variant['price'],
            'inventoryPolicy': variant.get('inventoryPolicy') or 'DENY',
            'inventoryItem': {'tracked': True},
            'inventoryQuantities': [
                {
                    'locationId': location_id,
                    'name': 'available',
                    # Oversold lines come back negative; a migration should
                    # carry "none left", not a debt into a fresh store.
                    'quantity': max(0, variant.get('inventoryQuantity') or 0),
                }
            ],
        }
        if variant.get('sku'):
            entry['sku'] = variant['sku']
        if variant.get('barcode'):
            entry['barcode'] = variant['barcode']
        if variant.get('compareAtPrice'):
            entry['compareAtPrice'] = variant['compareAtPrice']
        image = (variant.get('image') or {}).get('url')
        if image:
            entry['file'] = {'originalSource': image, 'contentType': 'IMAGE'}
        variants.append(entry)

    tags = list(product.get('tags') or [])
    status = product.get('status') or 'ACTIVE'
    if status_mode == 'active' and status != 'ACTIVE':
        # Keep the fact rather than the state: the development store needs
        # every product to render, but which ones were drafts is real
        # merchandising information and is not ours to discard.
        tags.append('source-status:draft')
        status = 'ACTIVE'

    payload = {
        'title': product['title'],
        'handle': product['handle'],
        'vendor': product.get('vendor') or '',
        'productType': product.get('productType') or '',
        'descriptionHtml': clean_description(product.get('descriptionHtml')),
        'tags': tags,
        'status': status,
        'productOptions': options,
        'variants': variants,
    }
    if files:
        payload['files'] = files
    if product.get('category'):
        payload['category'] = product['category']['id']
    return payload


# ------------------------------------------------------------------ loading

LOCATION = '{ locations(first: 1) { nodes { id name } } }'

# The handle is passed as an identifier rather than left inside the input, so
# a re-run updates the existing product instead of failing on a duplicate
# handle. Without it, `--only` can never repair anything.
PRODUCT_SET = """
mutation ($input: ProductSetInput!, $identifier: ProductSetIdentifiers) {
  productSet(input: $input, identifier: $identifier, synchronous: true) {
    product { id handle variants(first: 1) { nodes { id } } }
    userErrors { field message code }
  }
}
"""

EXISTING = """
query ($cursor: String) {
  products(first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes { id handle }
  }
}
"""

DELETE = """
mutation ($id: ID!) {
  productDelete(input: { id: $id }) { deletedProductId userErrors { message } }
}
"""


def wipe(target):
    """Clear the target so handles do not collide with the earlier hand-seed."""
    ids, cursor = [], None
    while True:
        page = target(EXISTING, {'cursor': cursor})['products']
        ids += [node['id'] for node in page['nodes']]
        if not page['pageInfo']['hasNextPage']:
            break
        cursor = page['pageInfo']['endCursor']
    print(f'Deleting {len(ids)} existing products from {target.domain} ...')
    for i, pid in enumerate(ids, 1):
        target(DELETE, {'id': pid})
        if i % 25 == 0:
            print(f'  {i}/{len(ids)}')
    return len(ids)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default=SOURCE)
    parser.add_argument('--target', default=TARGET)
    parser.add_argument('--wipe', action='store_true',
                        help='delete every product in the target first')
    parser.add_argument('--status', choices=('active', 'preserve'), default='active',
                        help='"active" publishes source drafts and tags them')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--only', default='',
                        help='comma-separated handles, to re-run a few products')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--cache', default='tools/old-store-export.json')
    args = parser.parse_args()

    source = Store(args.source)
    products = export_source(source, ROOT / args.cache)
    if args.only:
        wanted = {h.strip() for h in args.only.split(',') if h.strip()}
        products = [p for p in products if p['handle'] in wanted]
        missing = wanted - {p['handle'] for p in products}
        if missing:
            raise SystemExit(f'No such handle in the export: {sorted(missing)}')
    if args.limit:
        products = products[: args.limit]

    if args.dry_run:
        sample = build_input(products[0], 'gid://shopify/Location/0', args.status)
        print(json.dumps(sample, indent=1)[:2500])
        print(f'\n{len(products)} products, '
              f'{sum(len(p["variants"]) for p in products)} variants, '
              f'{sum(len(p["media"]) for p in products)} images')
        return

    target = Store(args.target)
    location_id = target(LOCATION)['locations']['nodes'][0]['id']
    print(f'Target location: {location_id}')

    if args.wipe:
        wipe(target)

    failures = []
    for i, product in enumerate(products, 1):
        payload = build_input(product, location_id, args.status)
        try:
            result = target(PRODUCT_SET, {
                'input': payload,
                'identifier': {'handle': product['handle']},
            })['productSet']
        except RuntimeError as exc:
            failures.append((product['handle'], str(exc)[:300]))
            continue
        errors = result['userErrors']
        if errors:
            failures.append((product['handle'], json.dumps(errors)[:300]))
        if i % 25 == 0:
            print(f'  {i}/{len(products)} ({len(failures)} failed)')

    print(f'\nImported {len(products) - len(failures)}/{len(products)} products.')
    for handle, message in failures:
        print(f'  FAILED {handle}: {message}')


if __name__ == '__main__':
    main()
