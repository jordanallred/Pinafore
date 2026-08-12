#!/usr/bin/env python3
"""
Pull real catalog data from the live Little Monkey Toes storefront so the dev
store can be seeded with the actual products, prices and photography rather
than placeholders.

Random stock photos are worse than useless for judging a childrenswear theme:
the whole design rests on how smocking, gingham and pale product shots sit
against the palette. This scrapes the store's own brand listing pages, which
give vendor attribution for free.

    python3 tools/scrape-lmt.py --out tools/seed-data-real.json

Only reads public product listing pages, at a deliberate crawl delay.
"""

import argparse
import html
import json
import pathlib
import re
import sys
import time
import urllib.request

BASE = 'https://littlemonkeytoes.com'

UA = 'Mozilla/5.0 (compatible; theme-dev-seed/1.0)'

BRAND_SITEMAP = f'{BASE}/xmlsitemap.php?type=brands&page=1'


def discover_brands():
    """
    Read the brand list from the store's own sitemap rather than hardcoding it.

    Many brands carry nothing at any given moment — the catalog is seasonal,
    so a hardcoded list quietly goes stale and silently returns fewer vendors
    than the brand index needs to be tested against.
    """
    markup = fetch(BRAND_SITEMAP)
    handles = []
    for loc in re.findall(r'<loc>([^<]+)</loc>', markup):
        m = re.match(rf'{re.escape(BASE)}/([a-z0-9-]+)/?$', loc)
        if m and m.group(1) != 'brands':
            handles.append(m.group(1))
    return handles


def title_from_page(markup, handle):
    """The brand's display name as the store spells it."""
    m = re.search(r'<h1 class="page-heading"[^>]*>\s*([^<]+)', markup)
    if m:
        return html.unescape(m.group(1)).strip()
    return handle.replace('-', ' ').title()


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='ignore')


def parse_cards(markup, vendor):
    """Extract products from a BigCommerce Stencil brand listing page."""
    out = []
    for card in re.findall(r'<article class="card[^"]*".*?</article>', markup, re.S):
        title_m = re.search(
            r'<h[34][^>]*class="card-title"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>\s*([^<]+)',
            card)
        if not title_m:
            continue
        url, title = title_m.group(1), html.unescape(title_m.group(2)).strip()

        # The visible <img src> is a lazy-load placeholder; the real asset is
        # in data-src. Prefer the largest stencil rendition available.
        img = None
        for m in re.finditer(r'data-src="([^"]+)"', card):
            candidate = m.group(1)
            if 'cdn11.bigcommerce.com' in candidate and '/products/' in candidate:
                img = candidate
                break
        if not img:
            m = re.search(r'srcset="([^"]+)"', card)
            if m:
                last = m.group(1).split(',')[-1].strip().split(' ')[0]
                if '/products/' in last:
                    img = last
        if not img:
            continue

        # Ask the CDN for a larger rendition than the grid thumbnail.
        img = re.sub(r'/images/stencil/\d+x\d+/', '/images/stencil/1280x1280/', img)

        price_m = re.search(r'class="price price--withoutTax"[^>]*>\s*([^<]+)', card)
        price = None
        if price_m:
            cleaned = price_m.group(1).strip().replace('$', '').replace(',', '')
            try:
                price = f'{float(cleaned):.2f}'
            except ValueError:
                price = None
        if not price:
            continue

        sold_out = 'card--sold-out' in card or 'Out of stock' in card

        out.append({
            'title': title,
            'vendor': vendor,
            'price': price,
            'image': img,
            'source_url': url,
            'sold_out': sold_out,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='tools/seed-data-real.json')
    ap.add_argument('--per-brand', type=int, default=6)
    ap.add_argument('--delay', type=float, default=0.6)
    ap.add_argument('--max-brands', type=int, default=0,
                    help='Stop after this many brands that actually have stock.')
    args = ap.parse_args()

    print('Discovering brands from the sitemap...')
    handles = discover_brands()
    print(f'  {len(handles)} brand pages\n')

    products = []
    stocked = 0
    for handle in handles:
        if args.max_brands and stocked >= args.max_brands:
            break
        try:
            markup = fetch(f'{BASE}/{handle}/')
        except Exception as exc:
            print(f'  skip {handle}: {exc}')
            continue

        vendor = title_from_page(markup, handle)
        found = parse_cards(markup, vendor)[:args.per_brand]
        if found:
            stocked += 1
            print(f'  {vendor:26} {len(found)}')
            products.extend(found)
        time.sleep(args.delay)

    print(f'\n{stocked} brands had stock')

    out_path = pathlib.Path(args.out)
    out_path.write_text(json.dumps({'products': products}, indent=2) + '\n')
    print(f'{len(products)} products -> {out_path}')
    return 0 if products else 1


if __name__ == '__main__':
    sys.exit(main())
