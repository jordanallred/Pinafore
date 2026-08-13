#!/usr/bin/env python3
"""
Crawl the live Little Monkey Toes storefront (BigCommerce Stencil) product by
product.

Why this exists alongside the old Shopify export: the previous Hydrogen-era
Shopify store holds 351 products, but the live store's sitemap lists 720. The
difference is a season and a half of merchandising that never made it across.
This crawl is what tells us which products those are, and captures enough to
rebuild them.

Two requests per product:

  1. The product page, for title, brand, price, images and the size option set.
  2. `/remote/v1/product-attributes/{id}`, the endpoint Stencil's own option
     picker calls. One call returns `in_stock_attributes` -- the option-value
     IDs that are actually purchasable -- so per-size availability costs one
     request per product rather than one per size.

Stock *counts* are not recoverable this way: the store has stock display turned
off, so the endpoint returns `stock: null`. Availability is a boolean here.
Real quantities have to come from a BigCommerce admin export.

    python3 tools/crawl-bigcommerce.py --out tools/live-catalog.json
"""

import argparse
import html as htmllib
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = 'https://littlemonkeytoes.com'
UA = 'Mozilla/5.0 (compatible; lmt-migration/1.0; +owner-authorised)'
SITEMAP = f'{BASE}/xmlsitemap.php?type=products&page=1'


def fetch(url, data=None, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url,
                data=data.encode() if data else None,
                headers={
                    'User-Agent': UA,
                    'X-Requested-With': 'XMLHttpRequest',
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as exc:  # noqa: BLE001 - a crawl should survive one bad page
            if attempt == tries - 1:
                print(f'  ! {url}: {exc}', file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def product_urls():
    markup = fetch(SITEMAP) or ''
    return re.findall(r'<loc>([^<]+)</loc>', markup)


def text(fragment):
    """Collapse a run of markup to its readable text."""
    return htmllib.unescape(re.sub(r'<[^>]+>', '', fragment)).strip()


def parse_product(markup, url):
    pid = re.search(r'name="product_id" value="(\d+)"', markup)
    if not pid:
        return None

    title = re.search(r'<h1 class="productView-title"[^>]*>(.*?)</h1>', markup, re.S)
    brand = re.search(
        r'productView-brand.*?<span itemprop="name">(.*?)</span>', markup, re.S
    )
    price = re.search(
        r'data-product-price-without-tax[^>]*>(.*?)</span>', markup, re.S
    )
    was = re.search(
        r'data-product-non-sale-price-without-tax[^>]*>(.*?)</span>', markup, re.S
    )

    # The gallery lists every image at 1280px; dedupe because the main figure
    # and its thumbnail point at the same file.
    images = []
    for src in re.findall(
        r'data-image-gallery-zoom-image-url="([^"]+)"', markup
    ) or re.findall(r'data-zoom-image="([^"]+)"', markup):
        if src not in images:
            images.append(src)

    # Size (or whatever the option happens to be called) as a select. Capture
    # the attribute id too -- it is the key the availability endpoint wants.
    options = []
    for block in re.findall(
        r'<div class="form-field" data-product-attribute="set-select">(.*?)</div>',
        markup,
        re.S,
    ):
        label = re.search(r'<label[^>]*>\s*([^<]+?)\s*:', block)
        attr = re.search(r'name="attribute\[(\d+)\]"', block)
        values = [
            {'id': int(vid), 'label': htmllib.unescape(lab).strip()}
            for vid, lab in re.findall(
                r'<option data-product-attribute-value="(\d+)" value="\d+" ?>([^<]*)</option>',
                block,
            )
        ]
        if attr and values:
            options.append(
                {
                    'name': label.group(1).strip() if label else 'Size',
                    'attribute_id': int(attr.group(1)),
                    'values': values,
                }
            )

    desc = re.search(
        r'<div class="tab-content is-active" id="tab-description">(.*?)</div>',
        markup,
        re.S,
    )

    return {
        'bc_id': int(pid.group(1)),
        'url': url,
        'handle': urllib.parse.urlparse(url).path.strip('/'),
        'title': text(title.group(1)) if title else '',
        'vendor': text(brand.group(1)) if brand else '',
        'price': text(price.group(1)) if price else '',
        'compare_at': text(was.group(1)) if was else '',
        'images': images,
        'options': options,
        'description_html': desc.group(1).strip() if desc else '',
        'sold_out': 'Out of stock' in markup and 'add-to-cart-wrapper' not in markup,
    }


def availability(product):
    """
    Ask Stencil which option values are purchasable.

    The endpoint needs a concrete selection to respond, so we send the first
    option value; the reply describes the whole option set regardless of which
    one we picked.
    """
    if not product['options']:
        return product
    opt = product['options'][0]
    body = urllib.parse.urlencode(
        {
            'action': 'add',
            'product_id': product['bc_id'],
            f'attribute[{opt["attribute_id"]}]': opt['values'][0]['id'],
            'qty[]': 1,
        }
    )
    raw = fetch(
        f'{BASE}/remote/v1/product-attributes/{product["bc_id"]}', data=body
    )
    if not raw:
        return product
    try:
        data = json.loads(raw)['data']
    except (ValueError, KeyError):
        return product

    in_stock = set(data.get('in_stock_attributes') or [])
    for value in opt['values']:
        value['in_stock'] = value['id'] in in_stock
    product['base_sku'] = data.get('sku')
    return product


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='tools/live-catalog.json')
    ap.add_argument('--delay', type=float, default=0.35)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    urls = product_urls()
    if args.limit:
        urls = urls[: args.limit]
    print(f'{len(urls)} product URLs in the sitemap', file=sys.stderr)

    out = pathlib.Path(args.out)
    products = []
    for i, url in enumerate(urls, 1):
        markup = fetch(url)
        if markup:
            product = parse_product(markup, url)
            if product:
                products.append(availability(product))
        if i % 25 == 0:
            print(f'  {i}/{len(urls)} ({len(products)} parsed)', file=sys.stderr)
            out.write_text(json.dumps({'products': products}, indent=1))
        time.sleep(args.delay)

    out.write_text(json.dumps({'products': products}, indent=1))
    print(f'wrote {len(products)} products to {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
