#!/usr/bin/env python3
"""
Create colour metaobject entries and link every Color option to them.

This is what makes colour filtering usable. Option values are vendor
marketing names — Apple Red, Chestnut, Driftwood Brown — and as plain strings
no filter can group them. Linking each value to a metaobject that carries a
taxonomy base colour lets Search & Discovery collapse them: a shopper clicks
Red and gets Apple Red and Rose.

The same link populates `value.swatch` in Liquid, which is what the variant
picker and the filter chips render.

Colour -> hex -> base colour comes from catalog-curation.json, written by hand.

    python3 tools/link-color-taxonomy.py --store <store>.myshopify.com
    python3 tools/link-color-taxonomy.py --store <store>.myshopify.com --dry-run
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CURATION = ROOT / 'tools' / 'catalog-curation.json'
ENV = {'SHOPIFY_CLI_AGENT_INFO': 'n:claude-code|v:none|p:anthropic|m:claude-sonnet-5'}

# Shopify's managed definition is tried first; a store-owned definition of the
# same shape is the documented fallback and behaves identically for filtering.
MANAGED_TYPE = 'shopify--color-pattern'
CUSTOM_TYPE = 'custom--color-pattern'


def gql(store, query, variables=None, mutation=False, quiet=False):
    cmd = ['shopify', 'store', 'execute', '--store', store, '--query', query]
    if variables:
        cmd += ['--variables', json.dumps(variables)]
    if mutation:
        cmd.append('--allow-mutations')
    p = subprocess.run(cmd, capture_output=True, text=True,
                       env={**os.environ, **ENV}, timeout=120)
    m = re.search(r'\{[\s\S]*\}', p.stdout)
    if not m:
        if not quiet:
            print(f'    no JSON: {(p.stdout + p.stderr).strip()[:200]}')
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return d.get('data', d)


CREATE_DEF = """
mutation D($definition: MetaobjectDefinitionCreateInput!) {
  metaobjectDefinitionCreate(definition: $definition) {
    metaobjectDefinition { id type }
    userErrors { field message code }
  }
}
"""

CREATE_ENTRY = """
mutation M($metaobject: MetaobjectCreateInput!) {
  metaobjectCreate(metaobject: $metaobject) {
    metaobject { id handle type }
    userErrors { field message code }
  }
}
"""

PRODUCTS = """
query {
  products(first: 100) {
    nodes {
      id
      title
      options { id name linkedMetafield { namespace key }
        optionValues { id name linkedMetafieldValue } }
    }
  }
}
"""

LINK = """
mutation L($pid: ID!, $option: OptionUpdateInput!, $updates: [OptionValueUpdateInput!]) {
  productOptionUpdate(
    productId: $pid
    option: $option
    optionValuesToUpdate: $updates
    variantStrategy: LEAVE_AS_IS
  ) {
    product { id }
    userErrors { field message code }
  }
}
"""


def ensure_definition(store, dry_run):
    """Confirm Shopify's managed colour definition is reachable."""
    probe = gql(store,
                'query { metaobjectDefinitionByType(type: "%s") { id type } }' % MANAGED_TYPE,
                quiet=True)
    if probe and probe.get('metaobjectDefinitionByType'):
        print(f'  {MANAGED_TYPE} is reachable')
        return MANAGED_TYPE
    print('  Managed definition not reachable. This needs the write_metaobjects\n'
          '  and read_metaobjects scopes — re-run `shopify store auth` with them.')
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    cur = json.loads(CURATION.read_text())
    colors = cur['colors']

    print('Resolving colour metaobject definition...')
    mtype = ensure_definition(a.store, a.dry_run)
    if not mtype:
        return 1

    print(f'\nCreating {len(colors)} colour entries...')
    handles = {}
    for name, spec in colors.items():
        handle = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        if a.dry_run:
            print(f'  [dry-run] {name:22} {spec["hex"]}  {spec["base"]}/{spec["pattern"]}')
            handles[name] = f'gid://dry-run/{handle}'
            continue

        fields = [
            {'key': 'label', 'value': name},
            {'key': 'color', 'value': spec['hex']},
        ]
        # Both taxonomy references are required by the managed definition.
        # color_taxonomy_reference is a list; pattern is a single value.
        fields.append({
            'key': 'color_taxonomy_reference',
            'value': json.dumps([f'gid://shopify/TaxonomyValue/{spec["base_id"]}']),
        })
        fields.append({
            'key': 'pattern_taxonomy_reference',
            'value': f'gid://shopify/TaxonomyValue/{spec["pattern_id"]}',
        })

        res = gql(a.store, CREATE_ENTRY,
                  {'metaobject': {'type': mtype, 'handle': handle, 'fields': fields}},
                  mutation=True)
        payload = (res or {}).get('metaobjectCreate') or {}
        errs = payload.get('userErrors') or []
        if errs:
            msg = errs[0].get('message', '')
            if 'taken' in msg.lower() or errs[0].get('code') == 'TAKEN':
                found = gql(a.store,
                            'query { metaobjectByHandle(handle: {type: "%s", handle: "%s"}) { id } }'
                            % (mtype, handle), quiet=True)
                existing = (found or {}).get('metaobjectByHandle')
                if existing:
                    handles[name] = existing['id']
                    print(f'  reuse   {name:22} {existing["id"].split("/")[-1]}')
                    continue
            print(f'  FAILED  {name:22} {msg[:80]}')
            continue
        obj = payload.get('metaobject')
        if obj:
            handles[name] = obj['id']
            print(f'  ok      {name:22} {spec["hex"]}  {spec["base"]}/{spec["pattern"]}')

    if a.dry_run:
        print('\n(dry run — no linking attempted)')
        return 0

    if not handles:
        print('\nNo colour entries created; not attempting to link options.')
        return 1

    print(f'\nLinking Color options on products...')
    res = gql(a.store, PRODUCTS)
    linked = skipped = failed = 0
    for p in (res or {}).get('products', {}).get('nodes', []):
        opt = next((o for o in p['options'] if o['name'] == 'Color'), None)
        if not opt:
            skipped += 1
            continue
        if opt.get('linkedMetafield'):
            skipped += 1
            continue

        updates = []
        ok = True
        for ov in opt['optionValues']:
            gid = handles.get(ov['name'])
            if not gid:
                ok = False
                break
            updates.append({'id': ov['id'], 'linkedMetafieldValue': gid})
        if not ok:
            print(f'  skip    {p["title"]}: a value has no colour entry')
            skipped += 1
            continue

        namespace, key = ('shopify', 'color-pattern') if mtype == MANAGED_TYPE else ('custom', 'color-pattern')
        r = gql(a.store, LINK, {
            'pid': p['id'],
            'option': {'id': opt['id'], 'linkedMetafield': {'namespace': namespace, 'key': key}},
            'updates': updates,
        }, mutation=True)
        errs = ((r or {}).get('productOptionUpdate') or {}).get('userErrors') or []
        if errs:
            failed += 1
            print(f'  FAILED  {p["title"]:28} {errs[0].get("message")[:80]}')
        else:
            linked += 1
            print(f'  ok      {p["title"]:28} {len(updates)} values linked')

    print(f'\n{linked} linked, {skipped} skipped, {failed} failed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
