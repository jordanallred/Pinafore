#!/usr/bin/env python3
"""
Apply `tools/catalog-normalization.json` to a store.

The map is hand-written; this script only executes it. It refuses to invent a
rename: anything not named in the map is left exactly as the migration left it.

Three passes, in this order:

  1. Sizes. Option values are renamed in place with `productOptionUpdate`, so
     variants keep their ids, inventory, SKUs and images. Where two values
     normalize onto the same name -- Properly Tied listing both '2t' and '2Y'
     on one pair of shorts -- one has to go, because Shopify cannot hold two
     option values with the same name and a rename into an existing name is
     rejected outright.

     Which one goes depends on how certain the collision is:

       * A pure formatting collision ('1 youth' vs '1 Youth') is beyond doubt
         the same size, so the duplicate is removed and its stock is *added*
         to the survivor. The shop holds 5 pairs under one spelling and 2
         under the other; it holds 7 pairs.

         The survivor does not always have somewhere to put it. Footmates
         listed Silver only under the lowercase spelling, so there was no
         'Silver / 1 Youth' to receive the stock and deleting the duplicate
         would have written off six pairs. Where the counterpart is missing
         it gets created first.

       * A semantic collision ('6Y' onto '6') rests on a judgement about the
         vendor's size chart. Those are merged only when the duplicate holds
         no stock. If both hold stock the product is left untouched and
         reported, because picking one would quietly delete sellable
         inventory and picking the sum would risk overselling. That is the
         owner's call, not this script's.

  2. Product types and tags. A flat `productUpdate`.

  3. Categories. Also `productUpdate`, but kept separate because a wrong
     taxonomy category silently breaks faceted filtering rather than looking
     wrong, so its changes are worth reporting on their own.

    python3 tools/normalize-catalog.py --dry-run
    python3 tools/normalize-catalog.py
"""

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from shopify_api import Store  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAP_FILE = ROOT / 'tools' / 'catalog-normalization.json'
TARGET = 'pinafore-bv80ud01.myshopify.com'

PRODUCTS = """
query ($cursor: String) {
  products(first: 40, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id handle title vendor productType tags
      category { id fullName }
      options { id name optionValues { id name } }
      variants(first: 100) {
        nodes {
          id inventoryQuantity price
          inventoryItem { id }
          selectedOptions { name value }
        }
      }
    }
  }
}
"""

OPTION_UPDATE = """
mutation ($productId: ID!, $option: OptionUpdateInput!,
          $update: [OptionValueUpdateInput!], $delete: [ID!]) {
  productOptionUpdate(
    productId: $productId
    option: $option
    optionValuesToUpdate: $update
    optionValuesToDelete: $delete
    variantStrategy: MANAGE
  ) {
    userErrors { field message code }
  }
}
"""

PRODUCT_UPDATE = """
mutation ($product: ProductUpdateInput!) {
  productUpdate(product: $product) { userErrors { field message } }
}
"""

INVENTORY_ADJUST = """
mutation ($input: InventoryAdjustQuantitiesInput!) {
  inventoryAdjustQuantities(input: $input) { userErrors { field message } }
}
"""

VARIANTS_CREATE = """
mutation ($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkCreate(productId: $productId, variants: $variants) {
    productVariants { id title }
    userErrors { field message }
  }
}
"""

LOCATION = '{ locations(first: 1) { nodes { id } } }'


def formatting_only(old, new):
    """
    True when two labels differ only in how they are typed.

    '1 youth' and '1 Youth' are the same size beyond argument. '6Y' and '6'
    are the same size only if you accept a reading of Properly Tied's size
    chart, and that is a different level of confidence.
    """
    def flatten(value):
        return value.lower().replace(' ', '').replace('-', '').replace('/', '')

    return flatten(old) == flatten(new)


def load_map():
    raw = json.loads(MAP_FILE.read_text())

    def clean(table):
        """Drop the `_`-prefixed annotations that document each block."""
        return {k: v for k, v in table.items()
                if not k.startswith('_') and isinstance(v, str)}

    sizes = raw['sizes']
    return {
        'global': clean(sizes['global']),
        'by_vendor': {v: clean(t) for v, t in sizes['by_vendor'].items()},
        'force_merge': {v: set(clean(t))
                        for v, t in sizes.get('force_merge', {}).items()
                        if isinstance(t, dict)},
        'types': clean(raw['product_types']),
        'tags': clean(raw['tags']),
        'categories': raw['categories']['by_handle'],
    }


def fetch_products(store):
    products, cursor = [], None
    while True:
        page = store(PRODUCTS, {'cursor': cursor})['products']
        products += page['nodes']
        if not page['pageInfo']['hasNextPage']:
            break
        cursor = page['pageInfo']['endCursor']
    return products


def target_name(rules, vendor, value):
    """Per-vendor rules win; the global table only holds catalog-wide truths."""
    vendor_rules = rules['by_vendor'].get(vendor, {})
    if value in vendor_rules:
        return vendor_rules[value]
    return rules['global'].get(value, value)


def plan_sizes(product, rules):
    """
    Work out the renames, and which duplicates have to go.

    Returns (option_id, renames, deletes, transfers, creates, notes, blocked).

    `transfers` are inventory moves that must happen *before* a delete, since
    deleting an option value takes its variants and their stock with it.
    `blocked` are collisions this script refuses to resolve on its own.
    """
    option = next((o for o in product['options'] if o['name'] == 'Size'), None)
    if not option:
        return None

    vendor = product['vendor']
    mapped = {}
    for value in option['optionValues']:
        mapped[value['id']] = (
            value['name'], target_name(rules, vendor, value['name'])
        )

    # Index variants by their size label, and by the rest of their options, so
    # a merge can move stock between the two listings of one physical size
    # colour by colour rather than in a lump.
    stock = collections.Counter()
    by_size = collections.defaultdict(list)
    for variant in product['variants']['nodes']:
        selected = dict((s['name'], s['value']) for s in variant['selectedOptions'])
        size = selected.get('Size')
        if size is None:
            continue
        stock[size] += max(0, variant.get('inventoryQuantity') or 0)
        siblings = tuple(sorted(
            (k, v) for k, v in selected.items() if k != 'Size'
        ))
        by_size[size].append((siblings, variant))

    by_target = collections.defaultdict(list)
    for vid, (old, new) in mapped.items():
        by_target[new].append(vid)

    renames, deletes, transfers, creates, notes, blocked = [], [], [], [], [], []
    for new, vids in by_target.items():
        if len(vids) == 1:
            vid = vids[0]
            if mapped[vid][0] != new:
                renames.append({'id': vid, 'name': new})
            continue

        # Prefer the value already spelled the way we want; failing that, the
        # one carrying the most stock.
        survivor = max(vids, key=lambda v: (mapped[v][0] == new, stock[mapped[v][0]]))
        losers = [v for v in vids if v != survivor]
        survivor_label = mapped[survivor][0]

        # Either the collision is self-evident from the spelling, or the map
        # names it explicitly as settled by the brand's published chart.
        authorised = rules['force_merge'].get(vendor, set())
        certain = all(
            formatting_only(mapped[v][0], new) or mapped[v][0] in authorised
            for v in losers
        )
        held = sum(stock[mapped[v][0]] for v in losers)

        if not certain and held > 0:
            blocked.append(
                f'{"/".join(mapped[v][0] for v in losers)} -> {new!r}: '
                f'{held} units in stock under the duplicate. Left as-is.'
            )
            continue

        for loser in losers:
            loser_label = mapped[loser][0]
            if certain:
                # Same size, two spellings: carry the stock across so the
                # merge does not quietly write off sellable units.
                survivors = dict(by_size[survivor_label])
                for siblings, variant in by_size[loser_label]:
                    quantity = max(0, variant.get('inventoryQuantity') or 0)
                    if not quantity:
                        continue
                    target = survivors.get(siblings)
                    if target:
                        transfers.append({
                            'inventoryItemId': target['inventoryItem']['id'],
                            'delta': quantity,
                        })
                    else:
                        # No counterpart under the surviving spelling. Build
                        # one, otherwise deleting the duplicate destroys the
                        # only record that this colour comes in this size.
                        creates.append({
                            'optionValues': (
                                [{'optionName': name, 'name': value}
                                 for name, value in siblings]
                                + [{'optionName': 'Size', 'name': new}]
                            ),
                            'price': variant.get('price'),
                            'inventoryQuantities': [{'availableQuantity': quantity}],
                            '_from': variant['id'],
                        })
            deletes.append(loser)
            notes.append(
                f'merged {loser_label!r} (stock {stock[loser_label]}) into '
                f'{new!r} (stock {stock[survivor_label]})'
                + (' — stock carried over' if certain and stock[loser_label] else '')
            )
        if survivor_label != new:
            renames.append({'id': survivor, 'name': new})

    return option['id'], renames, deletes, transfers, creates, notes, blocked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', default=TARGET)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    rules = load_map()
    store = Store(args.store)
    location = store(LOCATION)['locations']['nodes'][0]['id']
    products = fetch_products(store)
    print(f'{len(products)} products in {args.store}\n')

    size_changes = merges = type_changes = tag_changes = cat_changes = 0
    failures, needs_review = [], []

    for product in products:
        plan = plan_sizes(product, rules)
        if plan:
            option_id, renames, deletes, transfers, creates, notes, blocked = plan
            label = f'{product["vendor"]} — {product["title"]}'
            for note in blocked:
                needs_review.append(f'{label}: {note}')
            if renames or deletes or creates:
                size_changes += len(renames)
                merges += len(deletes)
                for rename in renames:
                    print(f'  size  {label}: -> {rename["name"]!r}')
                for note in notes:
                    print(f'  MERGE {label}: {note}')
                for create in creates:
                    size = next(o['name'] for o in create['optionValues']
                                if o['optionName'] == 'Size')
                    others = ' / '.join(o['name'] for o in create['optionValues']
                                        if o['optionName'] != 'Size')
                    print(f'  BUILD {label}: {others} / {size} — '
                          f'{create["inventoryQuantities"][0]["availableQuantity"]} '
                          f'units had no home under the surviving spelling')
                if not args.dry_run:
                    # Rebuild first, so the stock about to be freed by the
                    # delete has somewhere to land.
                    if creates:
                        payload = []
                        for create in creates:
                            entry = {k: v for k, v in create.items()
                                     if not k.startswith('_')}
                            entry['inventoryQuantities'] = [
                                {**q, 'locationId': location}
                                for q in entry['inventoryQuantities']
                            ]
                            payload.append(entry)
                        result = store(VARIANTS_CREATE, {
                            'productId': product['id'], 'variants': payload,
                        })['productVariantsBulkCreate']
                        if result['userErrors']:
                            failures.append((product['handle'], result['userErrors']))
                            continue
                    # Stock first: deleting an option value takes its variants
                    # and their inventory with it.
                    if transfers:
                        result = store(INVENTORY_ADJUST, {'input': {
                            'name': 'available',
                            'reason': 'correction',
                            'changes': [
                                {**t, 'locationId': location} for t in transfers
                            ],
                        }})['inventoryAdjustQuantities']
                        if result['userErrors']:
                            failures.append((product['handle'], result['userErrors']))
                            continue
                    result = store(OPTION_UPDATE, {
                        'productId': product['id'],
                        'option': {'id': option_id},
                        'update': renames,
                        'delete': deletes,
                    })['productOptionUpdate']
                    if result['userErrors']:
                        failures.append((product['handle'], result['userErrors']))

        update = {'id': product['id']}

        new_type = rules['types'].get(product['productType'])
        if new_type and new_type != product['productType']:
            update['productType'] = new_type
            type_changes += 1
            print(f'  type  {product["title"]}: '
                  f'{product["productType"]!r} -> {new_type!r}')

        new_tags = [rules['tags'].get(t, t) for t in product['tags']]
        new_tags = sorted(set(new_tags))
        if new_tags != sorted(product['tags']):
            update['tags'] = new_tags
            tag_changes += 1

        category = rules['categories'].get(product['handle'])
        if category:
            current = (product.get('category') or {}).get('id')
            if current != category['id']:
                update['category'] = category['id']
                cat_changes += 1
                print(f'  cat   {product["title"]}: {category["why"]}')

        if len(update) > 1 and not args.dry_run:
            result = store(PRODUCT_UPDATE, {'product': update})['productUpdate']
            if result['userErrors']:
                failures.append((product['handle'], result['userErrors']))

    verb = 'would change' if args.dry_run else 'changed'
    print(f'\n{verb}: {size_changes} size labels, {merges} duplicate sizes merged, '
          f'{type_changes} product types, {tag_changes} tag sets, '
          f'{cat_changes} categories')

    if needs_review:
        print(f'\nLeft alone — {len(needs_review)} collisions holding stock, '
              f'for the owner to decide:')
        for note in needs_review:
            print(f'  {note}')

    for handle, errors in failures:
        print(f'  FAILED {handle}: {json.dumps(errors)[:300]}')


if __name__ == '__main__':
    main()
