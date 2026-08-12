#!/usr/bin/env python3
"""
Assign each product its Shopify taxonomy category.

The category is what gives a product the shopify.color-pattern metafield, and
without it a Color option is free text that no filter can group. It is also a
prerequisite for the swatch setup done in the admin.

Mapping is hand-written in catalog-curation.json, keyed by product type.

    python3 tools/assign-categories.py --store <store>.myshopify.com
"""
import argparse, json, os, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = {'SHOPIFY_CLI_AGENT_INFO': 'n:claude-code|v:none|p:anthropic|m:claude-sonnet-5'}

def gql(store, query, variables=None, mutation=False):
    cmd = ['shopify','store','execute','--store',store,'--query',query]
    if variables: cmd += ['--variables', json.dumps(variables)]
    if mutation: cmd.append('--allow-mutations')
    p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **ENV}, timeout=120)
    m = re.search(r'\{[\s\S]*\}', p.stdout)
    if not m: return None
    try: d = json.loads(m.group(0))
    except json.JSONDecodeError: return None
    return d.get('data', d)

UPDATE = """
mutation C($id: ID!, $cat: ID!) {
  productUpdate(product: {id: $id, category: $cat}) {
    product { id category { name } }
    userErrors { field message }
  }
}
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', required=True)
    a = ap.parse_args()

    cur = json.loads((ROOT/'tools'/'catalog-curation.json').read_text())
    cats = cur['categories']
    seed = {p['title']: p for p in json.loads((ROOT/'tools'/'seed-data.json').read_text())['products']}

    res = gql(a.store, 'query { products(first: 100) { nodes { id title productType } } }')
    if not res: print('Could not read products.'); return 1

    done = missing = 0
    for p in res['products']['nodes']:
        ptype = (seed.get(p['title']) or {}).get('type') or p['productType']
        handle = cats.get(ptype)
        if not handle:
            missing += 1
            print(f"  no mapping for type '{ptype}' ({p['title']})")
            continue
        r = gql(a.store, UPDATE,
                {'id': p['id'], 'cat': f'gid://shopify/TaxonomyCategory/{handle}'}, mutation=True)
        errs = ((r or {}).get('productUpdate') or {}).get('userErrors') or []
        if errs:
            print(f"  FAILED {p['title']}: {errs[0].get('message')}")
        else:
            done += 1
    print(f'\n{done} categorised, {missing} unmapped.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
