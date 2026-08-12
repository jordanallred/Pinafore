#!/usr/bin/env python3
"""
Scrape each product's real option set from the live store.

Sizes were previously inferred from the product title, which is guesswork
dressed up as data — a Footmates shoe runs 3.0–13.0 in half sizes, nothing
like the 2T–8 ladder a title-based rule would hand it.

BigCommerce renders options as <option data-product-attribute-value=…> inside
a labelled form field, so the real values are in the served HTML.

    python3 tools/scrape-options.py
"""

import html as htmllib
import json
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools' / 'seed-data-real.json'
OUT = ROOT / 'tools' / 'seed-options.json'

UA = 'Mozilla/5.0 (compatible; theme-dev-seed/1.0)'

# Each option lives in a wrapper carrying its label, followed by its <option>s.
FIELD = re.compile(
    r'<label[^>]*class="[^"]*form-label[^"]*"[^>]*>\s*<span[^>]*>\s*([^<]+?)\s*</span>'
    r'(.*?)</(?:div|fieldset)>',
    re.S)
VALUE = re.compile(r'<option[^>]*data-product-attribute-value="[^"]*"[^>]*>\s*([^<]+?)\s*</option>')

# Fallback: any labelled block containing attribute options.
LOOSE_LABEL = re.compile(r'class="form-label[^"]*"[^>]*>\s*(?:<span[^>]*>)?\s*([A-Za-z ]+?)\s*[:<]')


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='ignore')


def parse_options(markup):
    """-> [{'name': 'Size', 'values': [...]}]"""
    # Narrow to the add-to-cart form so review-form selects are excluded.
    form = markup
    m = re.search(r'<form[^>]*data-cart-item-add[^>]*>(.*?)</form>', markup, re.S)
    if m:
        form = m.group(1)

    found = []
    for label, chunk in FIELD.findall(form):
        values = [htmllib.unescape(v) for v in VALUE.findall(chunk)]
        values = [v for v in values if v and not v.lower().startswith('choose')]
        if values:
            found.append({'name': htmllib.unescape(label).strip(' :'), 'values': values})

    if not found:
        values = [htmllib.unescape(v) for v in VALUE.findall(form)]
        values = [v for v in values if v and not v.lower().startswith('choose')]
        if values:
            label_m = LOOSE_LABEL.search(form)
            name = label_m.group(1).strip() if label_m else 'Size'
            found.append({'name': name, 'values': values})
    return found


def main():
    products = json.loads(SRC.read_text())['products']
    out = {}
    for i, p in enumerate(products):
        try:
            markup = fetch(p['source_url'])
            opts = parse_options(markup)
        except Exception as exc:
            print(f'  [{i:2}] {p["title"][:44]:46} ERROR {exc}')
            opts = []
        out[p['source_url']] = opts
        desc = '; '.join(f"{o['name']}: {', '.join(o['values'][:8])}"
                         f"{'…' if len(o['values']) > 8 else ''}" for o in opts) or '(none)'
        print(f'  [{i:2}] {p["title"][:44]:46} {desc[:80]}')
        time.sleep(0.4)

    OUT.write_text(json.dumps(out, indent=2) + '\n')
    have = sum(1 for v in out.values() if v)
    print(f'\n{have}/{len(products)} products had options -> {OUT}')


if __name__ == '__main__':
    main()
