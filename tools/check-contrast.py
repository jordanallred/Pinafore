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
    "1 Cream (default)": {
        "background":        "#FBF6F0",
        "foreground":        "#2F2823",
        "muted-foreground":  "#6E635A",
        "border":            "#E6DCD0",
        "border-control":    "#8A7F73",
        "focus-ring":        "#35506E",
        "button-background": "#2F2823",
        "button-foreground": "#FBF6F0",
        "accent-background": "#35506E",
        "accent-foreground": "#FFFFFF",
        "sale":              "#9A3B2B",
    },
    "2 Ink": {
        "background":        "#2F2823",
        "foreground":        "#F6F1EA",
        "muted-foreground":  "#B5A99C",
        "border":            "#463D35",
        "border-control":    "#8E8175",
        "focus-ring":        "#E8CBAE",
        "button-background": "#F6F1EA",
        "button-foreground": "#2F2823",
        "accent-background": "#E8CBAE",
        "accent-foreground": "#2F2823",
        "sale":              "#EE9781",
    },
    "3 Blush": {
        "background":        "#F7E9E4",
        "foreground":        "#3A2C28",
        "muted-foreground":  "#6F5D57",
        "border":            "#E8D3CC",
        "border-control":    "#8C7770",
        "focus-ring":        "#35506E",
        "button-background": "#3A2C28",
        "button-foreground": "#F7E9E4",
        "accent-background": "#35506E",
        "accent-foreground": "#FFFFFF",
        "sale":              "#9A3B2B",
    },
    "4 Sage": {
        "background":        "#49584A",
        "foreground":        "#F4F2EB",
        "muted-foreground":  "#C6CFC3",
        "border":            "#5E6E5F",
        "border-control":    "#A3B2A2",
        "focus-ring":        "#E8CBAE",
        "button-background": "#F4F2EB",
        "button-foreground": "#49584A",
        "accent-background": "#E8CBAE",
        "accent-foreground": "#2F2823",
        "sale":              "#F6BCAB",
    },
    "5 Snow": {
        "background":        "#FFFFFF",
        "foreground":        "#2F2823",
        "muted-foreground":  "#665C53",
        "border":            "#EDE5DC",
        "border-control":    "#8A7F73",
        "focus-ring":        "#35506E",
        "button-background": "#2F2823",
        "button-foreground": "#FFFFFF",
        "accent-background": "#35506E",
        "accent-foreground": "#FFFFFF",
        "sale":              "#9A3B2B",
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
