#!/usr/bin/env python3
"""Delete every product and collection, so a reseed starts clean.

Destructive by design and intended only for a development store.
"""
import argparse, json, os, re, subprocess, sys
ENV = {'SHOPIFY_CLI_AGENT_INFO': 'n:claude-code|v:none|p:anthropic|m:claude-sonnet-5'}

def gql(store, query, variables=None, mutation=False):
    cmd = ['shopify', 'store', 'execute', '--store', store, '--query', query]
    if variables: cmd += ['--variables', json.dumps(variables)]
    if mutation: cmd.append('--allow-mutations')
    p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **ENV}, timeout=120)
    m = re.search(r'\{[\s\S]*\}', p.stdout)
    if not m: return None
    try: d = json.loads(m.group(0))
    except json.JSONDecodeError: return None
    return d.get('data', d)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', required=True)
    ap.add_argument('--yes', action='store_true', help='Required; this deletes data.')
    a = ap.parse_args()
    if not a.yes:
        print('Refusing to run without --yes. This deletes every product and collection.')
        return 1

    for kind, q, mut, field in (
        ('products', 'query { products(first: 100) { nodes { id title } } }',
         'mutation D($input: ProductDeleteInput!) { productDelete(input: $input) { deletedProductId userErrors { message } } }', 'input'),
        ('collections', 'query { collections(first: 100) { nodes { id title } } }',
         'mutation D($id: ID!) { collectionDelete(input: {id: $id}) { deletedCollectionId userErrors { message } } }', 'id'),
    ):
        while True:
            res = gql(a.store, q)
            nodes = ((res or {}).get(kind) or {}).get('nodes') or []
            # "Home page" is a Shopify built-in; deleting it is not our business.
            nodes = [n for n in nodes if n['title'] != 'Home page']
            if not nodes: break
            print(f'Deleting {len(nodes)} {kind}...')
            for n in nodes:
                v = {'input': {'id': n['id']}} if field == 'input' else {'id': n['id']}
                gql(a.store, mut, v, mutation=True)
            print(f'  done')
            break
    print('Reset complete.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
