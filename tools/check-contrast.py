#!/usr/bin/env python3
"""WCAG contrast validator for the Pinafore palette."""

def lum(hexstr):
    h = hexstr.lstrip('#')
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = f(r), f(g), f(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# Two distinct border tokens, deliberately:
#   `border`         - decorative hairlines (card edges, dividers). WCAG 1.4.11
#                      does not apply to purely decorative boundaries, so these
#                      are tuned for looks and are intentionally low-contrast.
#   `border-control` - the visual boundary of interactive controls (inputs,
#                      unselected size pills, checkboxes). These ARE covered by
#                      1.4.11 and must clear 3:1 against their background.
SCHEMES = {
    "1 Paper (default)": {
        "background":        "#FAF8F5",
        "foreground":        "#262A30",
        "muted-foreground":  "#61666E",
        "border":            "#D6D8DC",
        "border-control":    "#7C828A",
        "focus-ring":        "#35506E",
        "button-background": "#262A30",
        "button-foreground": "#FAF8F5",
        "accent-background": "#35506E",
        "accent-foreground": "#FFFFFF",
        "sale":              "#8F3A2E",
    },
    "2 Ink": {
        "background":        "#262A30",
        "foreground":        "#F2F1EE",
        "muted-foreground":  "#A9AEB6",
        "border":            "#3D424A",
        "border-control":    "#858B94",
        "focus-ring":        "#E2C4A8",
        "button-background": "#F2F1EE",
        "button-foreground": "#262A30",
        "accent-background": "#E2C4A8",
        "accent-foreground": "#262A30",
        "sale":              "#E8907F",
    },
    "3 Blush": {
        "background":        "#F3E7DF",
        "foreground":        "#322C2A",
        "muted-foreground":  "#6A625E",
        "border":            "#DCCFC6",
        "border-control":    "#857B75",
        "focus-ring":        "#35506E",
        "button-background": "#322C2A",
        "button-foreground": "#F3E7DF",
        "accent-background": "#35506E",
        "accent-foreground": "#FFFFFF",
        "sale":              "#8F3A2E",
    },
    "4 Sage": {
        "background":        "#3F5044",
        "foreground":        "#F1F1EC",
        "muted-foreground":  "#B5BEB6",
        "border":            "#56675A",
        "border-control":    "#9AAA9C",
        "focus-ring":        "#E2C4A8",
        "button-background": "#F1F1EC",
        "button-foreground": "#3F5044",
        "accent-background": "#E2C4A8",
        "accent-foreground": "#262A30",
        "sale":              "#F5B4A4",
    },
    "5 Snow": {
        "background":        "#FFFFFF",
        "foreground":        "#262A30",
        "muted-foreground":  "#5C6169",
        "border":            "#E2E4E8",
        "border-control":    "#7E848C",
        "focus-ring":        "#35506E",
        "button-background": "#262A30",
        "button-foreground": "#FFFFFF",
        "accent-background": "#35506E",
        "accent-foreground": "#FFFFFF",
        "sale":              "#8F3A2E",
    },
}

# (foreground key, background key, minimum ratio, what it is)
PAIRS = [
    ("foreground",        "background",        4.5, "body text"),
    ("muted-foreground",  "background",        4.5, "secondary text"),
    ("button-foreground", "button-background", 4.5, "primary button label"),
    ("accent-foreground", "accent-background", 4.5, "accent button label"),
    ("border-control",    "background",        3.0, "control boundary (1.4.11)"),
    ("focus-ring",        "background",        3.0, "focus indicator (1.4.11)"),
    ("accent-background", "background",        3.0, "accent surface vs page"),
    # `sale` is a semantic signal held separate from the brand accent, and it
    # is used as text (struck-through compare-at prices), so it needs 4.5:1.
    ("sale",              "background",        4.5, "sale price text"),
]

fails = 0
for name, s in SCHEMES.items():
    print(f"\n{name}")
    for fg, bg, minimum, label in PAIRS:
        r = ratio(s[fg], s[bg])
        ok = r >= minimum
        if not ok:
            fails += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {r:5.2f}:1  (min {minimum})  {label:24} {s[fg]} on {s[bg]}")

print(f"\n{'=' * 62}")
print("ALL PAIRS PASS" if fails == 0 else f"{fails} FAILING PAIR(S)")
