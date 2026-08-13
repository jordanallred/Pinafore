#!/usr/bin/env python3
"""
Catches a Liquid expression opened with one delimiter and closed with the
other.

    {{ image | image_tag:
         class: 'x'
    %}          <- opened with {{, closed with %}

Trivial to write and invisible to read once a multi-line filter chain runs to
ten lines. Neither `theme check` nor any of the other guards here noticed it;
the upload did, which means the mistake costs a round trip to the store every
time. This makes it cost nothing.

Run from the theme root:  python3 tools/check-liquid-delimiters.py
"""

import pathlib
import re
import sys

# Every delimiter in the file, in order, with its offset.
TOKEN = re.compile(r'\{\{-?|-?\}\}|\{%-?|-?%\}')

OPENERS = {'{{': 'output', '{%': 'tag'}
CLOSERS = {'}}': 'output', '%}': 'tag'}


def kind(token):
    stripped = token.strip('-')
    if stripped in OPENERS:
        return 'open', OPENERS[stripped]
    return 'close', CLOSERS[stripped]


def check(path, source):
    problems = []
    open_token = None
    open_line = 0

    for match in TOKEN.finditer(source):
        role, flavour = kind(match.group(0))
        line = source.count('\n', 0, match.start()) + 1

        if role == 'open':
            if open_token is not None:
                problems.append(
                    (open_line, f'{open_token} at line {open_line} never closed')
                )
            open_token, open_line, open_flavour = match.group(0), line, flavour
        else:
            if open_token is None:
                problems.append((line, f'stray {match.group(0)}'))
                continue
            if flavour != open_flavour:
                problems.append((
                    open_line,
                    f'opened with {open_token} on line {open_line}, '
                    f'closed with {match.group(0)} on line {line}',
                ))
            open_token = None

    if open_token is not None:
        problems.append((open_line, f'{open_token} never closed'))
    return problems


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    found = []

    for path in sorted(root.rglob('*.liquid')):
        if '.git' in path.parts:
            continue
        source = path.read_text()
        # Raw blocks are allowed to contain unbalanced delimiters as content.
        source = re.sub(r'\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}',
                        '', source, flags=re.S)
        for line, message in check(path, source):
            found.append((path.relative_to(root), line, message))

    if not found:
        print('OK  every Liquid expression closes with its own delimiter')
        return 0

    print(f'{len(found)} delimiter problem(s):\n')
    for path, line, message in found:
        print(f'  {path}:{line}')
        print(f'      {message}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
