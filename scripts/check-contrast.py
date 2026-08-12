#!/usr/bin/env python3
"""Validate every colour scheme in config/settings_data.json against WCAG 2.1.

Referenced from snippets/css-variables.liquid. Run after changing any scheme:

    python3 scripts/check-contrast.py

Exits non-zero if any pairing fails, so it can gate a commit.

Thresholds
----------
Text pairings are held to 1.4.3 AA (4.5:1). `border_control` bounds interactive
controls and is held to 1.4.11 (3:1). `border` is decorative hairline only and
is deliberately not checked -- the seam is allowed to be quiet.
"""

import json
import re
import sys

AA_TEXT = 4.5
AA_NON_TEXT = 3.0


def parse_hex(value):
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    channels = []
    for c in rgb:
        c = c / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    a, b = luminance(parse_hex(fg)), luminance(parse_hex(bg))
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# (foreground setting, background setting, threshold, what it is used for)
PAIRINGS = [
    ("text", "background", AA_TEXT, "body copy"),
    ("text_muted", "background", AA_TEXT, "muted copy"),
    ("accent", "background", AA_TEXT, "accent as text"),
    ("sale", "background", AA_TEXT, "sale price"),
    ("button_label", "button", AA_TEXT, "primary button label"),
    ("accent_label", "accent", AA_TEXT, "label on accent fill"),
    ("secondary_button_label", "background", AA_TEXT, "secondary button label"),
    ("border_control", "background", AA_NON_TEXT, "control boundary"),
    ("accent", "background", AA_NON_TEXT, "focus ring"),
]


def main():
    raw = open("config/settings_data.json").read()
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    schemes = json.loads(raw)["current"]["color_schemes"]

    failures = []
    for scheme_id, scheme in sorted(schemes.items()):
        settings = scheme["settings"]
        print(f"\n{scheme_id}  (bg {settings['background']})")
        for fg_key, bg_key, threshold, label in PAIRINGS:
            fg, bg = settings.get(fg_key), settings.get(bg_key)
            if not fg or not bg:
                continue
            ratio = contrast(fg, bg)
            ok = ratio >= threshold
            mark = "PASS" if ok else "FAIL"
            print(
                f"  [{mark}] {ratio:5.2f}:1  (need {threshold})  "
                f"{label}: {fg} on {bg}"
            )
            if not ok:
                failures.append((scheme_id, label, ratio, threshold))

    print()
    if failures:
        print(f"{len(failures)} pairing(s) below threshold:")
        for scheme_id, label, ratio, threshold in failures:
            print(f"  {scheme_id}: {label} at {ratio:.2f}:1, needs {threshold}")
        return 1

    print("All pairings pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
