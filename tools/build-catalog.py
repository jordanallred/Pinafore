#!/usr/bin/env python3
"""
Join the scraped listings, their real option sets, and the hand-written
curation into the final seed catalog.

Nothing here infers structure. Grouping comes from catalog-curation.json,
sizes come from seed-options.json (scraped from each product's own page), and
images and prices come from the listings.

    python3 tools/build-catalog.py
"""

import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
LISTINGS = ROOT / 'tools' / 'seed-data-real.json'
OPTIONS = ROOT / 'tools' / 'seed-options.json'
CURATION = ROOT / 'tools' / 'catalog-curation.json'
OUT = ROOT / 'tools' / 'seed-data.json'

GIRL = ('dress', 'bloomer', 'bubble', 'smocked', 'skirt', 'romper', 'cheer',
        'gingham', 'ruffle', 'eyelet', 'sister', 'floral', 'peony', 'ballet')
BOY = ('brother', 'shark', 'dinosaur', 'stegosaurus', 'lab', 'retreiver',
       'retriever', 'barn jacket', 'driver')
BABY_WORDS = ('nb', 'newborn', '0-3', '3 mo', '3-6', '6 mo', '9 mo', '12 mo', '18 mo', '24 mo')


def clean(t):
    return re.sub(r'\s+', ' ', t.replace('*', '')).strip()


def classify(title, vendor, sizes):
    t = f'{title} {vendor}'.lower()
    tags = []
    if any(w in t for w in ('shoe', 'sandal', 't-strap', 'driver', 'floafer', 'footmates', "l'amour")):
        tags.append('Shoes')
    if any(w in t for w in ('sock', 'hat', 'backpack', 'lunchbox', 'nap mat', 'go bag', 'sleep bag')):
        tags.append('Accessories')
    if any(w in t for w in GIRL):
        tags.append('Girls')
    if any(w in t for w in BOY):
        tags.append('Boys')
    if sizes and any(any(b in s.lower() for b in BABY_WORDS) for s in sizes[:4]):
        tags.append('Baby')
    if 'alabama' in t or 'auburn' in t or 'cheer' in t:
        tags.append('Collegiate')
    return tags or ['Girls']


def product_type(title):
    t = title.lower()
    for word, label in (('dress', 'Dresses'), ('bloomer', 'Bloomers'), ('bubble', 'Bubbles'),
                        ('romper', 'Rompers'), ('pajama', 'Pajamas'), ('loungewear', 'Pajamas'),
                        ('sock', 'Socks'), ('hat', 'Hats'), ('backpack', 'Bags'),
                        ('lunchbox', 'Bags'), ('go bag', 'Bags'), ('nap mat', 'Nap mats'),
                        ('sleep bag', 'Sleepwear'), ('jacket', 'Outerwear'),
                        ('sweatshirt', 'Tops'), ('tee', 'Tops'), ('t-shirt', 'Tops'),
                        ('strap', 'Shoes'), ('driver', 'Shoes'), ('gown', 'Sleepwear'),
                        ('footie', 'Sleepwear'), ('set', 'Sets'), ('all in one', 'Rompers')):
        if word in t:
            return label
    return 'Apparel'


def main():
    listings = json.loads(LISTINGS.read_text())['products']
    options = json.loads(OPTIONS.read_text())
    cur = json.loads(CURATION.read_text())

    titles = cur.get('titles', {})
    vendor_fixes = cur.get('vendors', {})
    unmapped = []

    def final_title(generated):
        if generated in titles:
            return titles[generated]
        unmapped.append(generated)
        return generated

    def final_vendor(v):
        return vendor_fixes.get(v, v)

    dropped = {d['index'] for d in cur.get('drop', [])}
    sizeless = set(cur.get('sizeless', []))

    def sizes_for(idx):
        if idx in sizeless:
            return []
        opts = options.get(listings[idx]['source_url']) or []
        for o in opts:
            if o['values']:
                return o['values']
        return []

    claimed = set()
    products = []

    # --- curated multi-colour products -------------------------------------
    for group in cur['merge']:
        members = group['members']
        idxs = [m['index'] for m in members]
        claimed.update(idxs)
        base = listings[idxs[0]]
        sizes = sizes_for(idxs[0])

        opts = [{'name': group['option'],
                 'values': [m['value'] for m in members]}]
        if sizes:
            opts.append({'name': 'Size', 'values': sizes})

        products.append({
            'title': final_title(group['title']),
            'vendor': final_vendor(base['vendor']),
            'type': product_type(group['title']),
            'tags': classify(group['title'], base['vendor'], sizes),
            'body': f"<p>{group['title']} from {base['vendor']}.</p>",
            'options': opts,
            'price': base['price'],
            'compare_at': None,
            'inventory': 12,
            'image_url': base['image'],
            # One image per colour value, so the swatch has something to swap to.
            'extra_images': [listings[m['index']]['image'] for m in members[1:]],
        })

    # --- everything else stays a single product ----------------------------
    for i, p in enumerate(listings):
        if i in claimed or i in dropped:
            continue
        title = final_title(clean(p['title']))
        sizes = sizes_for(i)
        products.append({
            'title': title,
            'vendor': final_vendor(p['vendor']),
            'type': product_type(title),
            'tags': classify(title, p['vendor'], sizes),
            'body': f"<p>{title} from {p['vendor']}.</p>",
            'options': ([{'name': 'Size', 'values': sizes}] if sizes
                        else [{'name': 'Title', 'values': ['Default Title']}]),
            'price': p['price'],
            'compare_at': None,
            'inventory': 12,
            'image_url': p['image'],
            'extra_images': [],
        })

    # --- deliberate inventory states ---------------------------------------
    for i, p in enumerate(products):
        slot = i % 11
        price = float(p['price'])
        if slot == 2:
            p['inventory'] = 0
        elif slot == 4:
            p['inventory'] = 0
            p['backorder'] = True
            p['tags'].append('Preorder')
        elif slot == 6:
            p['compare_at'] = f'{price * 1.35:.2f}'
            p['tags'].append('Sale')
        elif slot == 8:
            p['inventory'] = 2
        if slot in (0, 1):
            p['tags'].append('New')
        if slot in (3, 7):
            p['tags'].append('Bestseller')

    payload = {
        '_comment': 'Built by tools/build-catalog.py from scraped listings, scraped '
                    'option sets, and the hand-written grouping in catalog-curation.json.',
        'products': products,
        'collections': [
            {'title': 'New Arrivals', 'rule_tag': 'New'},
            {'title': 'Best Sellers', 'rule_tag': 'Bestseller'},
            {'title': 'Girls', 'rule_tag': 'Girls'},
            {'title': 'Boys', 'rule_tag': 'Boys'},
            {'title': 'Baby', 'rule_tag': 'Baby'},
            {'title': 'Shoes', 'rule_tag': 'Shoes'},
            {'title': 'Accessories', 'rule_tag': 'Accessories'},
            {'title': 'Collegiate', 'rule_tag': 'Collegiate'},
            {'title': 'Preorder', 'rule_tag': 'Preorder'},
            {'title': 'Sale', 'rule_tag': 'Sale'},
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2) + '\n')

    multi = [p for p in products if len(p['options']) > 1]
    variants = sum(
        max(1, len(p['options'][0]['values']) * (len(p['options'][1]['values']) if len(p['options']) > 1 else 1))
        for p in products)
    if unmapped:
        print(f'WARNING  {len(unmapped)} product(s) have no hand-written title '
              f'in catalog-curation.json:')
        for u in unmapped:
            print(f'           {u}')
        print()

    print(f'{len(products)} products, {variants} variants, '
          f'{len({p["vendor"] for p in products})} vendors -> {OUT}\n')
    print(f'{len(multi)} products with two option axes:')
    for p in multi:
        a, b = p['options'][0], p['options'][1]
        print(f"  {p['title'][:38]:40} {a['name']}({len(a['values'])}) x {b['name']}({len(b['values'])})")
    states = collections.Counter()
    for p in products:
        if p.get('backorder'): states['preorder'] += 1
        elif p['inventory'] == 0: states['sold out'] += 1
        elif p['compare_at']: states['on sale'] += 1
        elif p['inventory'] == 2: states['low stock'] += 1
    print('\n' + ', '.join(f'{k}: {v}' for k, v in states.items()))


if __name__ == '__main__':
    main()
