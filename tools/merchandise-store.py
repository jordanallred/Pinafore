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

# Structure comes from the Shopify taxonomy category, not from tags.
#
# Tags are free text typed by whoever loaded the product, and this catalog
# proves how badly that fails: 48 products are footwear by category, and 13 of
# them carry the `shoes` tag. Petit Jolie's nine shoes carry it zero times,
# Salt Water's six likewise. A `TAG EQUALS shoes` collection therefore showed a
# quarter of the shoe department and looked entirely correct doing it.
#
# Category is assigned on 351 of 351 products, it is a controlled vocabulary,
# and `PRODUCT_CATEGORY_ID_WITH_DESCENDANTS` means a rule written against
# "Baby & Toddler Shoes" keeps working when a sandal is added underneath it.
CAT = 'PRODUCT_CATEGORY_ID_WITH_DESCENDANTS'

SMART_RULES = {
    # Footwear. 48 by category against 13 by tag.
    'shoes': {'rules': [(CAT, 'EQUALS', 'aa-8-2')]},
    'sandals': {'rules': [(CAT, 'EQUALS', 'aa-8-2-2')]},
    'sneakers': {'rules': [(CAT, 'EQUALS', 'aa-8-2-5')]},
    'boots': {'rules': [(CAT, 'EQUALS', 'aa-8-2-1')]},

    # Clothing, by garment rather than by who it is for.
    'dresses': {'any': True, 'rules': [
        (CAT, 'EQUALS', 'aa-1-2-3'), (CAT, 'EQUALS', 'aa-1-4')]},
    'tops': {'any': True, 'rules': [
        (CAT, 'EQUALS', 'aa-1-2-9'), (CAT, 'EQUALS', 'aa-1-13')]},
    'bottoms': {'any': True, 'rules': [
        (CAT, 'EQUALS', 'aa-1-2-1'), (CAT, 'EQUALS', 'aa-1-14'),
        (CAT, 'EQUALS', 'aa-1-15')]},
    'outfit-sets': {'rules': [(CAT, 'EQUALS', 'aa-1-2-5')]},
    'sleepwear': {'any': True, 'rules': [
        (CAT, 'EQUALS', 'aa-1-2-6'), (CAT, 'EQUALS', 'aa-1-17')]},
    'swim': {'rules': [(CAT, 'EQUALS', 'aa-1-2-8')]},
    'bags': {'any': True, 'rules': [
        (CAT, 'EQUALS', 'lb-1'), (CAT, 'EQUALS', 'lb-6'),
        (CAT, 'EQUALS', 'lb-13'), (CAT, 'EQUALS', 'aa-5-4')]},
    'accessories': {'any': True, 'rules': [
        (CAT, 'EQUALS', 'aa-2'), (CAT, 'EQUALS', 'hg-11-3-7')]},

    # Price-driven, and the only one that needs no vocabulary at all.
    'sale': {'rules': [('IS_PRICE_REDUCED', 'IS_SET', 'true')]},

    # Gender stays on tags because the taxonomy does not encode it -- there is
    # no "girls' dress" node, only "dress". These are therefore known to be
    # incomplete: 148 of 351 products carry no girls/boys/baby tag at all, so
    # the nav built on them hides two fifths of the shop. Recorded here rather
    # than quietly widened, because inferring a garment's gender from its
    # title or vendor is exactly the brittle guessing this file exists to
    # avoid. The BigCommerce export carries the shop's own gender tree.
    'girls': {'rules': [('TAG', 'EQUALS', 'girls')]},            # 93 of ~?
    'boys': {'rules': [('TAG', 'EQUALS', 'boys')]},              # 94 of ~?
    'baby': {'rules': [('TAG', 'EQUALS', 'baby')]},              # 24 of ~?
    'tween': {'rules': [('TAG', 'EQUALS', 'tween')]},            # 61
}

# Collections that had no data behind them at all. Rather than leave a dead
# handle for the homepage to point at, they are retitled onto something the
# shop really sells.
REPURPOSE = {
    'collegiate': ('Sandals', 'sandals'),
    'preorder': ('Sneakers', 'sneakers'),
}

# Products whose first image is a size chart rather than the product.
#
# Every Chus product leads with one: two are literally named CHUS_SIZE_CHART,
# and the rest are the same 386x290 export under a numeric filename. Their
# actual photographs are 386x257, 386x386, 386x219 or 386x286 — never 386x290.
# That makes the chart identifiable *for this vendor* without guessing.
#
# Deliberately not generalised to "landscape images are charts". Native's shoe
# photographs are 2:1 side profiles and are exactly right as the lead image; a
# ratio rule would have demoted four good photos to fix one bad one.
CHART_FIXES = {
    'Chus': {'width': 386, 'height': 290},
}

PRODUCT_MEDIA = """
query ($cursor: String, $query: String!) {
  products(first: 50, after: $cursor, query: $query) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title vendor
      media(first: 12) { nodes { ... on MediaImage { id image { url width height } } } }
    }
  }
}
"""

REORDER = """
mutation ($id: ID!, $moves: [MoveInput!]!) {
  productReorderMedia(id: $id, moves: $moves) {
    userErrors { field message }
  }
}
"""


def demote_charts(store):
    """Push each size chart to the end so the product leads with itself."""
    fixed = 0
    for vendor, size in CHART_FIXES.items():
        cursor = None
        while True:
            page = store(PRODUCT_MEDIA, {
                'cursor': cursor, 'query': f'vendor:"{vendor}"',
            })['products']
            for product in page['nodes']:
                media = [m for m in product['media']['nodes']
                         if m and m.get('image')]
                if len(media) < 2:
                    continue
                lead = media[0]['image']
                if (lead.get('width'), lead.get('height')) != (size['width'], size['height']):
                    continue
                result = store(REORDER, {
                    'id': product['id'],
                    'moves': [{'id': media[0]['id'],
                               'newPosition': str(len(media) - 1)}],
                })['productReorderMedia']
                if result['userErrors']:
                    print(f'  chart  {product["title"]}: {result["userErrors"]}')
                else:
                    fixed += 1
                    print(f'  chart  {vendor} — {product["title"][:38]}: '
                          f'size chart moved off the front')
            if not page['pageInfo']['hasNextPage']:
                break
            cursor = page['pageInfo']['endCursor']
    return fixed


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


def rule_input(spec):
    """
    Build a rule set. `any: True` unions the rules instead of intersecting
    them, which is what a department spanning several taxonomy nodes needs --
    dresses live under both "Baby & Toddler Dresses" and plain "Dresses".
    """
    return {
        'appliedDisjunctively': bool(spec.get('any')),
        'rules': [
            {
                'column': column,
                'relation': relation,
                # Category rules want the full gid; the bare handle is
                # rejected with "Enter value for Category is equal to".
                'condition': (
                    f'gid://shopify/TaxonomyCategory/{condition}'
                    if column.startswith('PRODUCT_CATEGORY') else condition
                ),
            }
            for column, relation, condition in spec['rules']
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

    # 0. Products leading with a size chart instead of the product.
    if not args.dry_run:
        demote_charts(store)

    # 1. Retitle the dead handles onto something real.
    for handle, (title, _) in REPURPOSE.items():
        existing = store(BY_HANDLE, {'handle': handle})['collectionByIdentifier']
        if not existing:
            continue
        print(f'  retitle {handle} -> {title}')
        if not args.dry_run:
            store(UPDATE_RULES, {'input': {'id': existing['id'], 'title': title}})

    # 2. Repair or create every smart collection.
    for handle, spec in SMART_RULES.items():
        existing = store(BY_HANDLE, {'handle': handle})['collectionByIdentifier']
        payload = {'ruleSet': rule_input(spec)}
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

        # A smart collection cannot be turned into a manual one. Passing
        # `ruleSet: null` is accepted and silently ignored, which left
        # new-arrivals holding its old `TAG EQUALS fall-winter` rule *plus*
        # the twelve curated products — 51 items where 12 were intended. The
        # only way across is to delete and rebuild on the same handle.
        if target:
            has_rules = store(
                'query($h:String!){collectionByIdentifier(identifier:{handle:$h})'
                '{ruleSet{rules{column}}}}', {'h': handle}
            )['collectionByIdentifier']['ruleSet']
            if has_rules:
                store('mutation($input:CollectionDeleteInput!)'
                      '{collectionDelete(input:$input){deletedCollectionId '
                      'userErrors{message}}}', {'input': {'id': target['id']}})
                target = None
                print(f'  rebuild {handle}: was smart, recreating as manual')

        if not target:
            created = store(CREATE, {'input': {
                'title': handle.replace('-', ' ').title(),
                'handle': handle,
            }})['collectionCreate']
            if created['userErrors']:
                print(f'  FAILED {handle}: {created["userErrors"]}')
                continue
            target = {'id': created['collection']['id']}
            store(PUBLISH, {'id': target['id'],
                            'input': [{'publicationId': online}]})
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
