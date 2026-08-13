#!/usr/bin/env python3
"""
Derive the store's collection structure from Shopify's product taxonomy.

The earlier version of this hardcoded a dozen category ids picked by eye off a
frequency list. That is not using the taxonomy, it is hardcoding against it —
it invented department names Shopify already had better names for, it missed
whole branches nobody happened to notice, and it went stale the moment the
catalog changed.

Shopify publishes the whole tree, and every node knows its ancestors, its
children and its depth. So the departments can be *read* instead of guessed:

  1. Ask each product which category it is in.
  2. Roll those counts up every ancestor chain, so an interior node knows how
     much of the catalog sits beneath it.
  3. Keep the nodes that are worth navigating to, and name them from the
     taxonomy itself.

The result adapts. Add fifteen raincoats and "Baby & Toddler Outerwear"
appears on its own; it does not need a code change, and it cannot silently
hide a department the way a tag-matching rule did.

    python3 tools/build-taxonomy-nav.py --dry-run
    python3 tools/build-taxonomy-nav.py
"""

import argparse
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from shopify_api import Store  # noqa: E402

TARGET = 'pinafore-bv80ud01.myshopify.com'

# A department has to be broad enough to be worth a nav slot and specific
# enough to mean something. Level 1 is "Apparel & Accessories", which is the
# whole shop; the useful range starts below it.
MIN_DEPARTMENT = 8      # products beneath a level 2-3 node
MIN_SUBCATEGORY = 5     # products beneath a level 4+ node
TOP_LEVEL = 1           # skip: too broad to navigate

# A node covering most of the shop is not a department, it is the shop. In
# this catalog "Clothing" holds 275 of 351 and "Baby & Toddler Clothing" 233;
# neither narrows anything down, and the garment nodes beneath them (Tops 119,
# Outfits 36, Bottoms 28, Dresses 25) are the ones a customer actually wants.
MAX_SHARE = 0.6

PRODUCT_CATEGORIES = """
query ($cursor: String) {
  products(first: 250, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes { id category { id } }
  }
}
"""

CATEGORY = """
query ($id: ID!) {
  node(id: $id) {
    ... on TaxonomyCategory { id name fullName level isLeaf ancestorIds }
  }
}
"""

BY_HANDLE = """
query ($handle: String!) {
  collectionByIdentifier(identifier: { handle: $handle }) {
    id handle productsCount { count }
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

UPDATE = """
mutation ($input: CollectionInput!) {
  collectionUpdate(input: $input) {
    collection { handle }
    userErrors { field message }
  }
}
"""

PUBLISH = """
mutation ($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) { userErrors { message } }
}
"""


def handleize(name):
    """A Shopify handle from a taxonomy name."""
    slug = re.sub(r"[^a-z0-9]+", '-', name.lower()).strip('-')
    # "Baby & Toddler Sandals" -> "sandals": the qualifier is on every node in
    # a children's catalog and adds nothing to a URL.
    slug = re.sub(r'^baby-(and-)?toddler-', '', slug)
    slug = re.sub(r'^baby-', '', slug)
    return slug or 'collection'


def load_tree(store):
    """Product counts, and every taxonomy node those products sit under."""
    counts = collections.Counter()
    total = 0
    cursor = None
    while True:
        page = store(PRODUCT_CATEGORIES, {'cursor': cursor})['products']
        for product in page['nodes']:
            total += 1
            if product['category']:
                counts[product['category']['id']] += 1
        if not page['pageInfo']['hasNextPage']:
            break
        cursor = page['pageInfo']['endCursor']

    nodes = {}
    to_fetch = set(counts)
    while to_fetch:
        node_id = to_fetch.pop()
        if node_id in nodes:
            continue
        node = store(CATEGORY, {'id': node_id})['node']
        if not node:
            continue
        nodes[node_id] = node
        to_fetch.update(a for a in node['ancestorIds'] if a not in nodes)

    # Roll each product up its whole ancestor chain, so an interior node
    # reports everything beneath it rather than only what is filed directly on
    # it. Without this, "Baby & Toddler Shoes" reads as 6 products when it
    # actually covers 48.
    rolled = collections.Counter()
    for category_id, count in counts.items():
        rolled[category_id] += count
        for ancestor in nodes.get(category_id, {}).get('ancestorIds', []):
            rolled[ancestor] += count

    return counts, rolled, nodes, total


def group_by_handle(chosen, rolled):
    """
    Collapse nodes that want the same name into one collection.

    The taxonomy files dresses under both "Dresses" and "Baby & Toddler
    Dresses", and a children's shop wants one Dresses page holding both.
    Emitting a collection per node instead would fight over the handle and
    leave whichever lost pointing at a fraction of the department.
    """
    groups = collections.defaultdict(list)
    for node in chosen:
        groups[handleize(node['name'])].append(node)
    return {
        handle: sorted(group, key=lambda n: -rolled[n['id']])
        for handle, group in groups.items()
    }


def choose(rolled, nodes, total):
    """
    Keep the nodes worth navigating to.

    A node earns a collection if enough of the catalog sits beneath it. It
    loses that place again if an ancestor we already kept covers exactly the
    same products — a chain like Shoes > Baby & Toddler Shoes where the parent
    has no other children is one department wearing two names.
    """
    keep = {}
    for node_id, count in rolled.items():
        node = nodes.get(node_id)
        if not node or node['level'] <= TOP_LEVEL:
            continue
        if count > total * MAX_SHARE:
            continue
        floor = MIN_DEPARTMENT if node['level'] <= 3 else MIN_SUBCATEGORY
        if count >= floor:
            keep[node_id] = node

    for node_id in list(keep):
        # An earlier iteration may already have dropped this node as some
        # other node's redundant ancestor.
        node = keep.get(node_id)
        if not node:
            continue
        for ancestor in node['ancestorIds']:
            if ancestor in keep and rolled[ancestor] == rolled[node_id]:
                # Identical coverage: keep the more specific name.
                keep.pop(ancestor, None)
    return keep


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', default=TARGET)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    store = Store(args.store)
    counts, rolled, nodes, total = load_tree(store)
    print(f'{total} products across {len(counts)} categories, '
          f'{len(nodes)} nodes in their combined tree\n')

    keep = choose(rolled, nodes, total)
    groups = group_by_handle(keep.values(), rolled)
    ordered = sorted(
        groups.items(),
        key=lambda kv: -sum(rolled[n['id']] for n in kv[1]),
    )

    covered = set()
    for _, group in ordered:
        for node in group:
            for category_id in counts:
                if (category_id == node['id']
                        or node['id'] in nodes[category_id]['ancestorIds']):
                    covered.add(category_id)
    missing = sum(counts[c] for c in counts if c not in covered)

    print(f'{len(ordered)} collections, covering {total - missing} of {total} products\n')
    for handle, group in ordered:
        reach = len({c for n in group for c in counts
                     if c == n['id'] or n['id'] in nodes[c]['ancestorIds']})
        size = sum(counts[c] for c in counts
                   if any(c == n['id'] or n['id'] in nodes[c]['ancestorIds']
                          for n in group))
        names = ' + '.join(n['name'] for n in group)
        print(f'  {size:4d}  {handle:20} {names}')

    if missing:
        print(f'\n{missing} products sit under nodes too small to warrant a '
              f'collection; they remain reachable by search, brand and filter.')

    if args.dry_run:
        return

    online = next(
        p['id'] for p in store('{ publications(first: 10) { nodes { id name } } }')
        ['publications']['nodes'] if p['name'] == 'Online Store'
    )

    print()
    for handle, group in ordered:
        rule = {
            # Several taxonomy nodes can feed one department, so the rules are
            # a union rather than an intersection.
            'appliedDisjunctively': True,
            'rules': [{
                'column': 'PRODUCT_CATEGORY_ID_WITH_DESCENDANTS',
                'relation': 'EQUALS',
                'condition': node['id'],
            } for node in group],
        }
        existing = store(BY_HANDLE, {'handle': handle})['collectionByIdentifier']
        if existing:
            result = store(UPDATE, {'input': {
                'id': existing['id'], 'ruleSet': rule,
            }})['collectionUpdate']
            verb = 'update'
        else:
            result = store(CREATE, {'input': {
                'title': group[0]['name'], 'handle': handle, 'ruleSet': rule,
            }})['collectionCreate']
            verb = 'create'
            if not result['userErrors']:
                store(PUBLISH, {'id': result['collection']['id'],
                                'input': [{'publicationId': online}]})
        status = result['userErrors'] or 'ok'
        print(f'  {verb} {handle:22} {status}')


if __name__ == '__main__':
    main()
