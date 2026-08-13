#!/usr/bin/env python3
"""
Point the store's collections at the catalog that is actually in it.

The homepage looked empty for a reason that had nothing to do with the theme.
Its sections referenced `new-arrivals`, `best-sellers`, `collegiate` and
`preorder`, and every one of those was a smart collection whose rule matched a
tag the seeded demo products carried and the migrated catalog does not -- `TAG
EQUALS New` against 351 products where no such tag exists. The sections
degraded exactly as designed, printing "choose a collection", which is honest
and also looks like a broken site.

Two more faults in the same place:

  * The sub-collections matched `TYPE EQUALS Dresses`, plural, against a
    catalog whose product types are singular. Nothing matched, and because the
    rules are conjunctive the tag half could not rescue them.

  * No collection had a featured image, so every seasonal tile on the homepage
    rendered as an empty grey box. Collections do not inherit imagery from
    their products; it has to be set.

    python3 tools/merchandise-store.py --dry-run
    python3 tools/merchandise-store.py
"""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from shopify_api import Store  # noqa: E402

TARGET = 'pinafore-bv80ud01.myshopify.com'

# Rules rewritten against tags and types the catalog actually carries. Counts
# in the comments are what each matched when this was written.
SMART_RULES = {
    'sale': [('TAG', 'EQUALS', 'final sale')],                   # 7
    'girls': [('TAG', 'EQUALS', 'girls')],                       # 93
    'boys': [('TAG', 'EQUALS', 'boys')],                         # 94
    'baby': [('TAG', 'EQUALS', 'baby')],                         # 24
    'shoes': [('TAG', 'EQUALS', 'shoes')],                       # 13
    'tween': [('TAG', 'EQUALS', 'tween')],                       # 61

    # Conjunctive: a tag AND a real, singular product type.
    'girls-dresses': [('TAG', 'EQUALS', 'girls'), ('TYPE', 'EQUALS', 'Dress')],
    'girls-tops': [('TAG', 'EQUALS', 'girls'), ('TYPE', 'EQUALS', 'Top')],
    'girls-skirts': [('TAG', 'EQUALS', 'girls'), ('TYPE', 'EQUALS', 'Skirt')],
    'boys-shirts': [('TAG', 'EQUALS', 'boys'), ('TYPE', 'EQUALS', 'Shirt')],
    'boys-shorts': [('TAG', 'EQUALS', 'boys'), ('TYPE', 'EQUALS', 'Shorts')],
    'boys-tees': [('TAG', 'EQUALS', 'boys'), ('TYPE', 'EQUALS', 'T-Shirt')],
    'baby-rompers': [('TAG', 'EQUALS', 'baby'), ('TYPE', 'EQUALS', 'Romper')],
    'sandals': [('TYPE', 'EQUALS', 'Sandals')],                  # 19
    'sneakers': [('TYPE', 'EQUALS', 'Sneakers')],                # 13
}

# Collections that had no data behind them at all. Rather than leave a dead
# handle for the homepage to point at, they are retitled onto something the
# shop really sells.
REPURPOSE = {
    'collegiate': ('Sandals', 'sandals'),
    'preorder': ('Sneakers', 'sneakers'),
}

BY_HANDLE = """
query ($handle: String!) {
  collectionByIdentifier(identifier: { handle: $handle }) {
    id handle title image { url } productsCount { count }
  }
}
"""

UPDATE_RULES = """
mutation ($input: CollectionInput!) {
  collectionUpdate(input: $input) {
    collection { handle productsCount { count } }
    userErrors { field message }
  }
}
"""

CREATE = """
mutation ($input: CollectionInput!) {
  collectionCreate(input: $input) {
    collection { id handle }
    userErrors { field message }
  }
}
"""

# The image a collection should wear is one of its own products'. Sorted by
# inventory so the tile shows something the shop can actually sell.
BEST_IMAGE = """
query ($handle: String!) {
  collectionByIdentifier(identifier: { handle: $handle }) {
    products(first: 12) {
      nodes {
        title
        productType
        totalInventory
        featuredMedia { ... on MediaImage { image { url } } }
      }
    }
  }
}
"""

PUBLISH = """
mutation ($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) { userErrors { message } }
}
"""

ALL_PRODUCTS = """
query ($cursor: String) {
  products(first: 250, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title vendor productType totalInventory
      featuredMedia { ... on MediaImage { image { url } } }
    }
  }
}
"""

ADD_PRODUCTS = """
mutation ($id: ID!, $ids: [ID!]!) {
  collectionAddProducts(id: $id, productIds: $ids) {
    userErrors { message }
  }
}
"""

REMOVE_PRODUCTS = """
mutation ($id: ID!, $ids: [ID!]!) {
  collectionRemoveProducts(id: $id, productIds: $ids) {
    userErrors { message }
  }
}
"""


def curated_pick(pool, count, exclude_ids):
    """
    Pick a shelf that looks like a boutique.

    Sorting by stock alone returns twelve of the same sandal, because the
    deepest inventory sits with whichever brand ships a full size run. One per
    vendor *and* one per product type is what makes a row read as a curated
    selection instead of a warehouse report — which is the whole premise of a
    multi-brand storefront.
    """
    chosen, vendors, types = [], set(), set()
    for product in pool:
        if product['id'] in exclude_ids:
            continue
        if product['vendor'] in vendors or product['productType'] in types:
            continue
        vendors.add(product['vendor'])
        types.add(product['productType'])
        chosen.append(product)
        if len(chosen) == count:
            break
    return chosen


def rule_input(rules):
    return {
        'appliedDisjunctively': False,
        'rules': [
            {'column': column, 'relation': relation, 'condition': condition}
            for column, relation, condition in rules
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', default=TARGET)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    store = Store(args.store)
    online = next(
        p['id'] for p in store('{ publications(first: 10) { nodes { id name } } }')
        ['publications']['nodes'] if p['name'] == 'Online Store'
    )

    # 1. Retitle the dead handles onto something real.
    for handle, (title, _) in REPURPOSE.items():
        existing = store(BY_HANDLE, {'handle': handle})['collectionByIdentifier']
        if not existing:
            continue
        print(f'  retitle {handle} -> {title}')
        if not args.dry_run:
            store(UPDATE_RULES, {'input': {'id': existing['id'], 'title': title}})

    # 2. Repair or create every smart collection.
    for handle, rules in SMART_RULES.items():
        existing = store(BY_HANDLE, {'handle': handle})['collectionByIdentifier']
        payload = {'ruleSet': rule_input(rules)}
        if existing:
            payload['id'] = existing['id']
            if args.dry_run:
                print(f'  rules  {handle}: was {existing["productsCount"]["count"]}')
                continue
            result = store(UPDATE_RULES, {'input': payload})['collectionUpdate']
        else:
            payload['title'] = handle.replace('-', ' ').title()
            payload['handle'] = handle
            if args.dry_run:
                print(f'  create {handle}')
                continue
            created = store(CREATE, {'input': payload})['collectionCreate']
            if created['userErrors']:
                print(f'  FAILED {handle}: {created["userErrors"]}')
                continue
            store(PUBLISH, {'id': created['collection']['id'],
                            'input': [{'publicationId': online}]})
            result = {'collection': {'productsCount': {'count': '?'}},
                      'userErrors': []}

        if result['userErrors']:
            print(f'  FAILED {handle}: {result["userErrors"]}')
        else:
            print(f'  rules  {handle}: '
                  f'{result["collection"]["productsCount"]["count"]} products')

    if args.dry_run:
        return

    # 3. Curate the two shelves the homepage leads with.
    #
    #    Neither can be a rule. "Best sellers" has no order history behind it
    #    yet, and "new arrivals" has no recency signal either — the whole
    #    catalog was bulk-imported within a minute of itself, so created_at
    #    says nothing. The nearest tag, `fall-winter`, turned out to be used by
    #    exactly two vendors, which produced a row of eight identical Properly
    #    Tied long-sleeve tees on a storefront whose entire pitch is breadth.
    pool = []
    cursor = None
    while True:
        page = store(ALL_PRODUCTS, {'cursor': cursor})['products']
        pool += [p for p in page['nodes']
                 if p['featuredMedia'] and (p['totalInventory'] or 0) > 3]
        if not page['pageInfo']['hasNextPage']:
            break
        cursor = page['pageInfo']['endCursor']
    pool.sort(key=lambda p: -(p['totalInventory'] or 0))

    best = curated_pick(pool, 12, set())
    fresh = curated_pick(pool, 12, {p['id'] for p in best})

    for handle, picks in (('best-sellers', best), ('new-arrivals', fresh)):
        target = store(BY_HANDLE, {'handle': handle})['collectionByIdentifier']
        if not target:
            continue
        current = store(
            'query($h:String!){collectionByIdentifier(identifier:{handle:$h})'
            '{products(first:100){nodes{id}}}}', {'h': handle}
        )['collectionByIdentifier']['products']['nodes']
        stale = [p['id'] for p in current if p['id'] not in {x['id'] for x in picks}]
        if stale:
            store(REMOVE_PRODUCTS, {'id': target['id'], 'ids': stale})
        result = store(ADD_PRODUCTS, {
            'id': target['id'], 'ids': [p['id'] for p in picks],
        })['collectionAddProducts']
        vendors = len({p['vendor'] for p in picks})
        print(f'  curate {handle}: {len(picks)} products, {vendors} vendors'
              f'{" " + str(result["userErrors"]) if result["userErrors"] else ""}')

    # 4. Give every collection a featured image, or the homepage tiles stay
    #    grey. Smart-collection membership settles asynchronously, so this
    #    runs after the rules are already in place.
    # Deepest stock sits with whichever brand ships a full size run, so
    # picking purely by inventory gave Girls, Boys and the season tile three
    # near-identical green Properly Tied tees. Remembering what has already
    # been spent forces each tile to show something the others do not.
    used_products, used_types = set(), set()

    for handle in list(SMART_RULES) + list(REPURPOSE) + ['new-arrivals', 'best-sellers']:
        data = store(BEST_IMAGE, {'handle': handle})['collectionByIdentifier']
        if not data:
            continue
        candidates = [
            p for p in data['products']['nodes']
            if p['featuredMedia'] and p['featuredMedia'].get('image')
        ]
        if not candidates:
            print(f'  image  {handle}: no product imagery yet')
            continue
        candidates.sort(key=lambda p: -(p['totalInventory'] or 0))
        pick = next(
            (p for p in candidates
             if p['title'] not in used_products and p['productType'] not in used_types),
            None,
        ) or next(
            (p for p in candidates if p['title'] not in used_products),
            candidates[0],
        )
        used_products.add(pick['title'])
        used_types.add(pick['productType'])

        current = store(BY_HANDLE, {'handle': handle})['collectionByIdentifier']
        result = store(UPDATE_RULES, {'input': {
            'id': current['id'],
            'image': {'src': pick['featuredMedia']['image']['url'],
                      'altText': current['title']},
        }})['collectionUpdate']
        status = result['userErrors'] or f'from "{pick["title"][:34]}"'
        print(f'  image  {handle}: {status}')


if __name__ == '__main__':
    main()
