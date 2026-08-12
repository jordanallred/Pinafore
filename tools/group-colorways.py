#!/usr/bin/env python3
"""
Collapse colourways that the source store lists as separate products into one
Shopify product with a variant option.

BigCommerce stores commonly publish each colourway as its own product.
Imported one-to-one that produces four near-identical "L'Amour BIRDIE 2945
T-Straps" entries sitting side by side in the grid, which is wrong for the
migration and leaves the theme's swatches — on the card and in the variant
picker — with nothing to render.

The source encodes titles as:  Vendor *TOKEN* Rest

and the token means different things depending on the vendor:

    Footmates *Allie* Apple Red        token = style, rest = colourway
    La Luna *Blue Mouse Ears* Romper   token = colourway, rest = garment

So neither half can be assumed. The discriminator is which half stays
constant across a candidate group: the part that varies is the option, the
part that holds is the product.

Option naming follows the values themselves. "Big Brother / Big Sister" and
"Alabama / Auburn" are real variant axes but they are not colours, and
labelling them Color would put nonsense in the picker and in filters.

    python3 tools/group-colorways.py            # report only
    python3 tools/group-colorways.py --write    # rewrite seed-data-real.json
"""

import argparse
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools' / 'seed-data-real.json'

# Longest first, so "apple red" wins over "red" and "denim blue" over "blue".
COLORS = [
    'apple red', 'denim blue', 'moss green', 'light blue', 'baby blue',
    'navy blue', 'hunter green', 'dusty rose', 'antique white', 'off white',
    'chestnut', 'lavender', 'burgundy', 'charcoal', 'natural', 'oatmeal',
    'crimson', 'magenta', 'mustard', 'emerald', 'scarlet', 'apricot',
    'cobalt', 'yellow', 'orange', 'purple', 'silver', 'bronze', 'indigo',
    'khaki', 'coral', 'peach', 'cream', 'camel', 'taupe', 'olive', 'brown',
    'green', 'white', 'black', 'beige', 'blush', 'misty', 'stone', 'ivory',
    'navy', 'pink', 'blue', 'gray', 'grey', 'mint', 'rose', 'sage', 'fern',
    'gold', 'ecru', 'teal', 'plum', 'aqua', 'sand', 'oat', 'red', 'tan',
    'sky',
]
COLOR_RX = re.compile(r'\b(' + '|'.join(re.escape(c) for c in COLORS) + r')\b', re.I)


def split_title(title, vendor):
    """-> (token, rest). `token` is the *…* part, `rest` is everything else."""
    body = title
    for prefix in (vendor, vendor.replace('  ', ' '), vendor.split()[0]):
        if body.lower().startswith(prefix.lower()):
            body = body[len(prefix):].strip()
            break
    m = re.search(r'\*([^*]+)\*', body)
    token = m.group(1).strip() if m else ''
    rest = re.sub(r'\s+', ' ', re.sub(r'\*[^*]+\*', ' ', body)).strip()
    return token, rest


def norm(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', text.lower())).strip()


def option_name(values):
    """Name the axis after what its values actually are."""
    hits = sum(1 for v in values if COLOR_RX.search(v))
    return 'Color' if hits >= max(1, len(values) // 2) else 'Style'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()

    products = json.loads(SRC.read_text())['products']
    parts = {id(p): split_title(p['title'], p['vendor']) for p in products}

    # Two candidate groupings: hold the rest constant (token varies), or hold
    # the token constant (rest varies).
    by_rest = collections.defaultdict(list)
    by_token = collections.defaultdict(list)
    for p in products:
        token, rest = parts[id(p)]
        # A style number like 2945 is not part of the garment identity.
        rest_key = norm(re.sub(r'\b\d{3,}\b', ' ', rest))
        by_rest[(p['vendor'], rest_key)].append(p)
        if token:
            by_token[(p['vendor'], norm(token))].append(p)

    def distinct(members, pick):
        vals = [pick(m) for m in members]
        return len(set(v.lower() for v in vals)) == len(vals) and all(vals)

    def is_colourway_set(members):
        """
        For the token-constant grouping, the varying half must differ ONLY by a
        colour word. Otherwise these are different garments that happen to share
        a print — "BROTHER Denim Sweatshirt" and "BROTHER Sage Short Sleeve
        T-Shirt" are two products, not two colours of one.

        Strip the colour from each value: if what remains is identical, the
        colour was the only difference.
        """
        remainders = set()
        for m in members:
            rest = parts[id(m)][1]
            if not COLOR_RX.search(rest):
                return False
            remainders.add(norm(COLOR_RX.sub(' ', rest)))
        return len(remainders) == 1

    def colour_of(member):
        """The colour words in the varying half, in source casing."""
        rest = parts[id(member)][1]
        found = COLOR_RX.findall(rest)
        # findall returns the alternation group; re-search for the actual span
        # so multi-word colours keep their spacing.
        spans = [m.group(0) for m in COLOR_RX.finditer(rest)]
        return ' '.join(dict.fromkeys(s.title() for s in spans)) or rest.title()

    claimed, groups = set(), []
    # Prefer whichever grouping actually yields distinct option values, and the
    # larger group when both do.
    candidates = []
    for (vendor, key), members in by_rest.items():
        if len(members) > 1 and distinct(members, lambda m: parts[id(m)][0]):
            candidates.append((len(members), 'token-varies', vendor, key, members))
    for (vendor, key), members in by_token.items():
        if len(members) > 1 and distinct(members, lambda m: parts[id(m)][1]):
            candidates.append((len(members), 'rest-varies', vendor, key, members))
    candidates.sort(key=lambda c: -c[0])

    for _, mode, vendor, key, members in candidates:
        if any(id(m) in claimed for m in members):
            continue
        for m in members:
            claimed.add(id(m))
        groups.append((mode, vendor, members))

    merged = []
    for mode, vendor, members in groups:
        base = members[0]
        base_token, base_rest = parts[id(base)]

        if mode == 'token-varies':
            values = [parts[id(m)][0].title() for m in members]
            product_title = f'{vendor} {base_rest}'
        else:
            values = [parts[id(m)][1].title() for m in members]
            product_title = f'{vendor} {base_token}'

        merged.append({
            'title': re.sub(r'\s+', ' ', product_title).strip(),
            'vendor': vendor,
            'price': base['price'],
            'image': base['image'],
            'source_url': base['source_url'],
            'sold_out': all(m.get('sold_out') for m in members),
            'option_name': option_name(values),
            'colors': [{'name': v, 'image': m['image']}
                       for v, m in zip(values, members)],
        })

    for p in products:
        if id(p) not in claimed:
            merged.append({**p, 'option_name': None, 'colors': []})

    multi = [m for m in merged if m['colors']]
    print(f'{len(products)} source listings -> {len(merged)} products')
    print(f'  {len(multi)} merged, {len(merged) - len(multi)} single\n')
    for m in multi:
        print(f"  {m['title'][:46]:48} {m['option_name']:6} "
              f"{', '.join(c['name'] for c in m['colors'])}")

    if a.write:
        SRC.write_text(json.dumps({'products': merged}, indent=2) + '\n')
        print(f'\nWrote {SRC}')
    else:
        print('\n(report only — pass --write to apply)')


if __name__ == '__main__':
    main()
