#!/usr/bin/env python3
"""
Turn scraped Little Monkey Toes listings into seed input.

The scrape gives real titles, vendors, prices and photography but no variant
structure, because the listing pages do not expose it. Sizes are inferred from
what the product plainly is — a sock is not sized like a shoe, and a bloomer
is not sized like a size-7 dress — so the variant picker gets exercised
against realistic option sets rather than one generic ladder.

Inventory states are assigned deliberately rather than randomly, so every
badge path in the theme has at least one product proving it:
sale, preorder (backordered), sold out, low stock, plain in-stock.

    python3 tools/build-seed-from-real.py
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools' / 'seed-data-real.json'
OUT = ROOT / 'tools' / 'seed-data.json'

# Size ladders by what the product actually is.
SIZES = {
    'sock': ['6-18M', '2-4Y', '4-6Y'],
    'shoe': ['5', '6', '7', '8', '9', '10', '11', '12'],
    'baby': ['3M', '6M', '12M', '18M', '24M'],
    'kid': ['2T', '3T', '4T', '5', '6', '7', '8'],
}

SHOE_WORDS = ('shoe', 'sandal', 'sneaker', 'boot', 'floafer', 'mary jane', 'loafer', 'moccasin')
BABY_WORDS = ('bloomer', 'bubble', 'romper', 'onesie', 'coverall', 'footie', 'layette', 'bonnet')
# Accessories are one-size: giving a hairbow a size ladder would be nonsense
# data that makes the picker look broken rather than exercised.
ONE_SIZE_WORDS = ('bow', 'headband', 'hat', 'cap', 'bag', 'backpack', 'nap mat',
                  'blanket', 'lunch', 'tote', 'necklace', 'bracelet', 'clip')

GIRL_WORDS = ('dress', 'bloomer', 'bubble', 'smocked', 'bow', 'skirt', 'pinafore',
              'ruffle', 'tutu', 'jumper', 'floral')
BOY_WORDS = ('short', 'polo', 'boys', 'gingham shirt', 'button down', 'overall', 'tie')


def ladder(title, vendor):
    t = f'{title} {vendor}'.lower()
    if any(w in t for w in ONE_SIZE_WORDS):
        return None
    if any(w in t for w in SHOE_WORDS):
        return SIZES['shoe']
    if 'sock' in t or 'tight' in t:
        return SIZES['sock']
    if any(w in t for w in BABY_WORDS):
        return SIZES['baby']
    return SIZES['kid']


def tags_for(title, vendor, sizes):
    t = f'{title} {vendor}'.lower()
    tags = []
    if any(w in t for w in SHOE_WORDS):
        tags.append('Shoes')
    if 'sock' in t or 'tight' in t or any(w in t for w in ONE_SIZE_WORDS):
        tags.append('Accessories')
    if any(w in t for w in GIRL_WORDS):
        tags.append('Girls')
    if any(w in t for w in BOY_WORDS):
        tags.append('Boys')
    if sizes is SIZES['baby']:
        tags.append('Baby')
    if not tags:
        tags.append('Girls')
    return tags


def product_type(title, vendor, sizes):
    t = f'{title} {vendor}'.lower()
    for word, label in (('dress', 'Dresses'), ('bloomer', 'Bloomers'), ('bubble', 'Bubbles'),
                        ('short', 'Shorts'), ('sock', 'Socks'), ('bow', 'Accessories'),
                        ('hat', 'Accessories'), ('bag', 'Bags'), ('nap mat', 'Nap mats'),
                        ('polo', 'Tops'), ('shirt', 'Tops'), ('set', 'Sets')):
        if word in t:
            return label
    if sizes is SIZES['shoe']:
        return 'Shoes'
    return 'Apparel'


def clean_title(raw):
    """The live store shouts print names in asterisks; keep them, drop the noise."""
    return re.sub(r'\s+', ' ', raw.replace('*', '')).strip()


def main():
    src = json.loads(SRC.read_text())['products']
    out = []

    for i, p in enumerate(src):
        title = clean_title(p['title'])
        sizes = ladder(title, p['vendor'])
        tags = tags_for(title, p['vendor'], sizes)
        price = float(p['price'])

        entry = {
            'title': title,
            'vendor': p['vendor'],
            'type': product_type(title, p['vendor'], sizes),
            'tags': tags,
            'body': f"<p>{title} from {p['vendor']}.</p>",
            # A one-size item gets Shopify's default option rather than a
            # single-value "Size" ladder, so has_only_default_variant is true
            # and the theme hides the picker instead of showing one lone pill.
            'options': ([{'name': 'Size', 'values': sizes}] if sizes
                        else [{'name': 'Title', 'values': ['Default Title']}]),
            'price': f'{price:.2f}',
            'compare_at': None,
            'inventory': 14,
            'image_url': p['image'],
        }

        # Deterministic spread of states, so re-running produces the same store
        # and every badge path has a product proving it.
        slot = i % 12
        if p.get('sold_out') or slot == 3:
            entry['inventory'] = 0
        elif slot == 5:
            entry['inventory'] = 0
            entry['backorder'] = True
            entry['tags'].append('Preorder')
        elif slot == 7:
            entry['compare_at'] = f'{price * 1.35:.2f}'
            entry['tags'].append('Sale')
        elif slot == 9:
            entry['inventory'] = 2
        if slot in (0, 1):
            entry['tags'].append('New')
        if slot in (2, 6):
            entry['tags'].append('Bestseller')

        out.append(entry)

    payload = {
        '_comment': 'Generated by tools/build-seed-from-real.py from real Little '
                    'Monkey Toes listings. Sizes are inferred from product type; '
                    'inventory states are assigned deterministically so every badge '
                    'path in the theme has at least one product exercising it.',
        'products': out,
        'collections': [
            {'title': 'New Arrivals', 'rule_tag': 'New'},
            {'title': 'Best Sellers', 'rule_tag': 'Bestseller'},
            {'title': 'Girls', 'rule_tag': 'Girls'},
            {'title': 'Boys', 'rule_tag': 'Boys'},
            {'title': 'Baby', 'rule_tag': 'Baby'},
            {'title': 'Shoes', 'rule_tag': 'Shoes'},
            {'title': 'Accessories', 'rule_tag': 'Accessories'},
            {'title': 'Preorder', 'rule_tag': 'Preorder'},
            {'title': 'Sale', 'rule_tag': 'Sale'},
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2) + '\n')

    variants = sum(max(1, len(p['options'][0]['values']) if p['options'] else 1) for p in out)
    states = {
        'sold out': sum(1 for p in out if p['inventory'] == 0 and not p.get('backorder')),
        'preorder': sum(1 for p in out if p.get('backorder')),
        'on sale': sum(1 for p in out if p['compare_at']),
        'low stock': sum(1 for p in out if p['inventory'] == 2),
    }
    print(f'{len(out)} products, ~{variants} variants, '
          f'{len({p["vendor"] for p in out})} vendors -> {OUT}')
    print('  ' + ', '.join(f'{k}: {v}' for k, v in states.items()))


if __name__ == '__main__':
    main()
