#!/usr/bin/env python3
"""
Populate a development store with a catalog shaped like a real children's
boutique, so the theme can be judged against realistic data rather than
against an empty grid.

Why this exists: almost every bug this theme could have — the variant picker,
faceted filters, the brand index, preorder badging, sale pricing — is
invisible on an empty store and only appears with many vendors, apparel
sizing, and mixed inventory states.

Prerequisite (one time, opens a browser):

    shopify store auth --store <store>.myshopify.com \
      --scopes write_products,read_products,write_inventory,read_inventory,write_files

Then:

    python3 tools/seed-dev-store.py --store <store>.myshopify.com
    python3 tools/seed-dev-store.py --store <store>.myshopify.com --dry-run
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'tools' / 'seed-data.json'

AGENT_ENV = {
    'SHOPIFY_CLI_AGENT_INFO': 'n:claude-code|v:none|p:anthropic|m:claude-sonnet-5',
}


def run_graphql(store, query, variables=None, mutation=False, dry_run=False):
    """Execute one operation through the Shopify CLI."""
    cmd = ['shopify', 'store', 'execute', '--store', store, '--query', query]
    if variables is not None:
        cmd += ['--variables', json.dumps(variables)]
    if mutation:
        cmd.append('--allow-mutations')

    if dry_run:
        print(f'  [dry-run] {query.strip().splitlines()[0][:70]}...')
        return None

    env = {**os.environ, **AGENT_ENV}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    if proc.returncode != 0:
        print(f'  CLI error:\n{proc.stderr.strip()[:600]}')
        return None

    # The CLI prints progress lines before the JSON body; take the JSON object.
    out = proc.stdout
    start = out.find('{')
    if start == -1:
        print(f'  No JSON in response: {out.strip()[:300]}')
        return None
    try:
        parsed = json.loads(out[start:])
    except json.JSONDecodeError as exc:
        print(f'  Unparseable response ({exc}): {out[start:start + 300]}')
        return None

    # `shopify store execute` prints the result already unwrapped, without the
    # GraphQL `data` envelope. Accept either shape so this keeps working if
    # that changes.
    return parsed.get('data', parsed) if isinstance(parsed, dict) else parsed


LOCATION_QUERY = """
query {
  locations(first: 1) {
    nodes { id name }
  }
}
"""

PRODUCT_SET = """
mutation SeedProduct($input: ProductSetInput!) {
  productSet(synchronous: true, input: $input) {
    product { id title handle }
    userErrors { field message }
  }
}
"""

COLLECTION_CREATE = """
mutation SeedCollection($input: CollectionInput!) {
  collectionCreate(input: $input) {
    collection { id title handle }
    userErrors { field message }
  }
}
"""


def build_variants(product, location_id):
    """Cross the option values into variants, with per-variant inventory."""
    options = product['options']
    combos = [[]]
    for opt in options:
        combos = [c + [(opt['name'], v)] for c in combos for v in opt['values']]

    qty = product.get('inventory', 0)
    backorder = product.get('backorder', False)
    policy = 'CONTINUE' if backorder else 'DENY'

    variants = []
    for i, combo in enumerate(combos):
        variant = {
            'optionValues': [
                {'optionName': name, 'name': value} for name, value in combo
            ],
            'price': product['price'],
            'inventoryItem': {'tracked': True},
            'inventoryPolicy': policy,
        }
        if product.get('compare_at'):
            variant['compareAtPrice'] = product['compare_at']
        if location_id:
            # Vary stock across variants so sold-out sizes actually appear in
            # the picker — a uniformly stocked product never exercises that path.
            per = qty if qty == 0 else max(0, qty - (i % 4) * 3)
            variant['inventoryQuantities'] = [
                {'locationId': location_id, 'name': 'available', 'quantity': per}
            ]
        variants.append(variant)
    return variants


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', required=True)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-images', action='store_true',
                    help='Skip image attachment; the theme falls back to placeholder SVGs.')
    args = ap.parse_args()

    data = json.loads(DATA.read_text())

    location_id = None
    if not args.dry_run:
        print('Resolving primary location...')
        res = run_graphql(args.store, LOCATION_QUERY)
        nodes = ((res or {}).get('locations') or {}).get('nodes') or []
        if not nodes:
            print('  Could not resolve a location. Has `shopify store auth` been run?')
            return 1
        location_id = nodes[0]['id']
        print(f"  {nodes[0]['name']}  {location_id}")

    print(f"\nCreating {len(data['products'])} products...")
    created = failed = 0
    for product in data['products']:
        payload = {
            'title': product['title'],
            'vendor': product['vendor'],
            'productType': product['type'],
            'tags': product['tags'],
            'descriptionHtml': product['body'],
            'status': 'ACTIVE',
            'productOptions': [
                {'name': o['name'], 'values': [{'name': v} for v in o['values']]}
                for o in product['options']
            ],
            'variants': build_variants(product, location_id),
        }

        if not args.no_images and product.get('image_seed'):
            # Seeded placeholders at a 3:4 portrait ratio, matching the theme's
            # default media shape. Stand-ins, not real product photography.
            seed = product['image_seed']
            payload['files'] = [
                {
                    'originalSource': f'https://picsum.photos/seed/{seed}-{n}/1200/1600',
                    'contentType': 'IMAGE',
                    'alt': product['title'],
                }
                for n in (1, 2)
            ]

        res = run_graphql(args.store, PRODUCT_SET, {'input': payload},
                          mutation=True, dry_run=args.dry_run)
        if args.dry_run:
            print(f"  [dry-run] {product['title']} "
                  f"({len(payload['variants'])} variants, {product['vendor']})")
            continue

        result = (res or {}).get('productSet') or {}
        errors = result.get('userErrors') or []
        if errors:
            failed += 1
            print(f"  FAILED  {product['title']}")
            for e in errors[:3]:
                print(f"          {e.get('field')}: {e.get('message')}")
        elif result.get('product'):
            created += 1
            print(f"  ok      {product['title']}  ({len(payload['variants'])} variants)")
        else:
            failed += 1
            print(f"  FAILED  {product['title']}  (no product returned)")

    print(f"\nCreating {len(data['collections'])} smart collections...")
    for coll in data['collections']:
        payload = {
            'title': coll['title'],
            'ruleSet': {
                'appliedDisjunctively': False,
                'rules': [
                    {'column': 'TAG', 'relation': 'EQUALS', 'condition': coll['rule_tag']}
                ],
            },
        }
        res = run_graphql(args.store, COLLECTION_CREATE, {'input': payload},
                          mutation=True, dry_run=args.dry_run)
        if args.dry_run:
            print(f"  [dry-run] {coll['title']}  (tag = {coll['rule_tag']})")
            continue
        result = (res or {}).get('collectionCreate') or {}
        errors = result.get('userErrors') or []
        if errors:
            print(f"  FAILED  {coll['title']}: {errors[0].get('message')}")
        else:
            print(f"  ok      {coll['title']}")

    if not args.dry_run:
        print(f'\n{created} created, {failed} failed.')
        print('\nNext: in the admin, Search & Discovery > Filters — add filters for '
              'Vendor, Size and Price so the collection facets have something to show.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
