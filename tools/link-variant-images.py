#!/usr/bin/env python3
"""
Attach each colourway's photograph to the variants of that colour.

`productSet` uploads files to the product but does not associate them with
variants, so `variant.featured_media` comes back null. Everything that depends
on knowing which photo is which colour is dead until this runs:

  - the product page swapping the gallery when a colour is chosen
  - colour thumbnails on the collection card
  - showing the filtered colour's photo when a colour filter is applied

The mapping is positional and comes from the seed data, where a product's
image_url is the first colour and extra_images follow in option-value order.

    python3 tools/link-variant-images.py --store <store>.myshopify.com
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEED = ROOT / 'tools' / 'seed-data.json'
ENV = {'SHOPIFY_CLI_AGENT_INFO': 'n:claude-code|v:none|p:anthropic|m:claude-sonnet-5'}


def gql(store, query, variables=None, mutation=False):
    cmd = ['shopify', 'store', 'execute', '--store', store, '--query', query]
    if variables:
        cmd += ['--variables', json.dumps(variables)]
    if mutation:
        cmd.append('--allow-mutations')
    p = subprocess.run(cmd, capture_output=True, text=True,
                       env={**os.environ, **ENV}, timeout=120)
    m = re.search(r'\{[\s\S]*\}', p.stdout)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return d.get('data', d)


PRODUCTS = """
query {
  products(first: 100) {
    nodes {
      id
      title
      options { name optionValues { name } }
      media(first: 20) { nodes { id ... on MediaImage { image { url } } } }
      variants(first: 100) {
        nodes { id title selectedOptions { name value } }
      }
    }
  }
}
"""

LINK = """
mutation Link($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    userErrors { field message }
  }
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', required=True)
    a = ap.parse_args()

    seed = {p['title']: p for p in json.loads(SEED.read_text())['products']}

    res = gql(a.store, PRODUCTS)
    if not res:
        print('Could not read products.')
        return 1

    linked = skipped = failed = 0
    for prod in res['products']['nodes']:
        spec = seed.get(prod['title'])
        if not spec:
            continue

        # Only products whose first option is a colourway axis carry per-value
        # photography; a size ladder shares one image.
        opts = spec.get('options') or []
        if not opts or opts[0]['name'] not in ('Color', 'Team'):
            skipped += 1
            continue

        axis = opts[0]['name']
        values = opts[0]['values']
        media = prod['media']['nodes']
        if len(media) < 2:
            skipped += 1
            continue

        # Positional: image i belongs to option value i. Any colour beyond the
        # images we have falls back to the first image rather than guessing.
        value_to_media = {}
        for i, value in enumerate(values):
            value_to_media[value] = media[i]['id'] if i < len(media) else media[0]['id']

        updates = []
        for v in prod['variants']['nodes']:
            chosen = next((o['value'] for o in v['selectedOptions'] if o['name'] == axis), None)
            media_id = value_to_media.get(chosen)
            if media_id:
                updates.append({'id': v['id'], 'mediaId': media_id})

        if not updates:
            skipped += 1
            continue

        # Bulk update caps well below our largest product (92 variants), so
        # send in chunks.
        ok = True
        for i in range(0, len(updates), 50):
            chunk = updates[i:i + 50]
            r = gql(a.store, LINK, {'productId': prod['id'], 'variants': chunk}, mutation=True)
            errs = ((r or {}).get('productVariantsBulkUpdate') or {}).get('userErrors') or []
            if errs:
                ok = False
                print(f"  FAILED  {prod['title']}: {errs[0].get('message')}")
                break
        if ok:
            linked += 1
            print(f"  ok      {prod['title']:34} {len(updates)} variants -> {len(set(value_to_media.values()))} images")
        else:
            failed += 1

    print(f'\n{linked} products linked, {skipped} skipped (single image or size-only), {failed} failed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
