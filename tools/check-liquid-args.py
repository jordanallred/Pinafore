#!/usr/bin/env python3
"""
Catches filter chains used inside a filter's named argument.

Liquid filter arguments are plain values. This is invalid and fails only at
upload time, not during `shopify theme check` on some versions:

    {{ img | image_tag: alt: product.title | escape, loading: 'lazy' }}
                             ^^^^^^^^^^^^^^^^^^^^^^

The pipe binds to the whole output expression, so `escape` swallows the rest
of the argument list. Resolve the value into a variable first:

    {% assign alt = product.title | escape %}
    {{ img | image_tag: alt: alt, loading: 'lazy' }}

Run from the theme root:  python3 tools/check-liquid-args.py
"""

import pathlib
import re
import sys

# `name: something | filter` appearing after a filter's colon, where the line
# ends in a comma — i.e. it is one argument in a multi-argument filter call.
SUSPECT = re.compile(r'^\s*(\w+):\s*[^\'"\n]*?\|\s*\w+\s*,\s*$')

# A named argument whose value contains a pipe, on a line inside a filter call.
INLINE = re.compile(r'\|\s*\w+:\s*[^,\n]*\|\s*\w+\s*,')

# The same mistake inside a *tag* argument, e.g.
#     {% form 'product', product, id: 'X-' | append: section.id %}
# Liquid reads the piped expression as the next positional argument, so the
# form type becomes the id. This one only surfaces at render time.
TAG_ARG = re.compile(
    r'\{%-?\s*(?:form|render|include|section|paginate|liquid)\b[^%]*?'
    r'\b\w+:\s*[^,%]*?\|\s*\w+'
)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    problems = []

    for path in sorted(root.rglob('*.liquid')):
        if '.git' in path.parts:
            continue
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines, 1):
            if SUSPECT.match(line) or INLINE.search(line) or TAG_ARG.search(line):
                problems.append((path.relative_to(root), i, line.strip()))

    if not problems:
        print('OK  no filter chains inside filter arguments')
        return 0

    print(f'{len(problems)} suspect line(s) — filter chain inside a filter argument:\n')
    for path, line_no, text in problems:
        print(f'  {path}:{line_no}')
        print(f'      {text}')
    print('\nResolve the value with {% assign %} before passing it.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
