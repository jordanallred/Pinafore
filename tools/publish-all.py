#!/usr/bin/env python3
"""
Publish every product and collection to the Online Store channel.

`productSet` creates resources but does not publish them, so a freshly seeded
store looks completely empty on the storefront while the admin shows a full
catalog. This closes that gap.

    python3 tools/publish-all.py --store <store>.myshopify.com
"""
import argparse, json, os, re, subprocess, sys

ENV = {'SHOPIFY_CLI_AGENT_INFO': 'n:claude-code|v:none|p:anthropic|m:claude-sonnet-5'}

def gql(store, query, variables=None, mutation=False):
    cmd = ['shopify', 'store', 'execute', '--store', store, '--query', query]
    if variables: cmd += ['--variables', json.dumps(variables)]
    if mutation: cmd.append('--allow-mutations')
    p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **ENV}, timeout=120)
    m = re.search(r'\{[\s\S]*\}', p.stdout)
    if not m:
        print(f'  no JSON: {(p.stdout + p.stderr).strip()[:300]}'); return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        print(f'  unparseable: {m.group(0)[:200]}'); return None
    return d.get('data', d)

PUBLISH = """
mutation Pub($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) {
    userErrors { field message }
  }
}
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', required=True)
    a = ap.parse_args()

    pubs = gql(a.store, 'query { publications(first: 10) { nodes { id name } } }')
    online = next((n['id'] for n in pubs['publications']['nodes'] if n['name'] == 'Online Store'), None)
    if not online:
        print('No Online Store publication found.'); return 1
    print(f'Online Store: {online}\n')

    for kind, q in (('products', 'query { products(first: 100) { nodes { id title } } }'),
                    ('collections', 'query { collections(first: 100) { nodes { id title } } }')):
        res = gql(a.store, q)
        nodes = res[kind]['nodes']
        print(f'Publishing {len(nodes)} {kind}...')
        for n in nodes:
            r = gql(a.store, PUBLISH, {'id': n['id'], 'input': [{'publicationId': online}]}, mutation=True)
            errs = ((r or {}).get('publishablePublish') or {}).get('userErrors') or []
            print(f"  {'FAILED ' if errs else 'ok     '} {n['title']}"
                  + (f"  {errs[0].get('message')}" if errs else ''))
    return 0

if __name__ == '__main__':
    sys.exit(main())
