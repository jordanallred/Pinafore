#!/usr/bin/env python3
"""
Check that every section and snippet closes the tags it opens.

Unbalanced markup does not fail `shopify theme check` and does not raise a
Liquid error — the browser silently repairs it, usually by closing an
ancestor early. A stray </div> in the product card ended up closing the <li>
and <ul> around it, so 21 of 22 cards rendered outside the grid at their
image's intrinsic width. The page looked broken; nothing in the toolchain
noticed.

Liquid branches make exact counting impossible, so this compares totals per
file and flags only clear imbalances.

    python3 tools/check-html-balance.py
"""
import pathlib
import re
import sys

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr', 'path', 'circle', 'rect'}
TAGS = ['div', 'article', 'section', 'ul', 'ol', 'li', 'form', 'fieldset',
        'header', 'footer', 'nav', 'main', 'table', 'tbody', 'thead', 'tr',
        'td', 'th', 'details', 'summary', 'dialog', 'button', 'label',
        'h1', 'h2', 'h3', 'h4', 'figure', 'picture', 'select', 'textarea']


def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    problems = []
    for path in sorted(list((root / 'sections').glob('*.liquid'))
                       + list((root / 'snippets').glob('*.liquid'))
                       + list((root / 'layout').glob('*.liquid'))):
        markup = path.read_text().split('{% stylesheet %}')[0].split('{% javascript %}')[0]
        markup = re.sub(r'\{%-?\s*comment.*?endcomment\s*-?%\}', '', markup, flags=re.S)
        markup = re.sub(r'\{%-?\s*doc.*?enddoc\s*-?%\}', '', markup, flags=re.S)
        for tag in TAGS:
            if tag in VOID:
                continue
            opens = len(re.findall(rf'<{tag}(?=[\s>])', markup))
            closes = len(re.findall(rf'</{tag}\s*>', markup))
            if opens != closes:
                problems.append((path.relative_to(root), tag, opens, closes))

    if not problems:
        print('OK  every section and snippet balances its tags')
        return 0
    print(f'{len(problems)} imbalance(s):\n')
    for path, tag, o, c in problems:
        print(f'  {path}:  <{tag}>  {o} open / {c} close')
    print('\nA stray close tag silently breaks out of its parent at render time.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
