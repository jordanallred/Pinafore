# Pinafore Theme Redesign — Design Spec

**Date:** 2026-08-12
**Store:** pinafore-bv80ud01.myshopify.com (migrating from littlemonkeytoes.com)
**Theme:** Pinafore 0.1.0

## Context

Pinafore is the Shopify theme for a multi-brand children's boutique. The
storefront marquee claims "60+ brands under one roof"; the seeded catalog
currently holds 47 products across 18 vendors, so the design must scale to the
former while looking right at the latter. The merchandise is classic Southern
children's clothing: smocked bubbles, gingham, Peter Pan collars, monogramming,
gameday. That heritage — not generic pastel — is the source of the theme's
visual identity.

The theme already has a competent token layer in `snippets/css-variables.liquid`.
The problem is not missing architecture; it is that the tokens resolve to values
that contradict each other, and that the merchant settings select the worst
combination available.

## Problems (observed, not assumed)

### P1 — Four radius languages on one screen

`style_corners: round` resolves to `radius_control: 999`, `radius_card: 16`,
`radius_media: 12`; `style_button_shape: pill` forces buttons to 999 as well.
On the collection page this renders 999px pills (Filter and sort, PREORDER /
25% OFF / SOLD OUT badges, 20 brand chips), 16px cards, 12px media, and 50%
circles (swatches) simultaneously.

Both reference sites hold exactly one language: poshpeanut.com clusters at
12px (74 elements) and 16px (55); magneticme.com is 0px plus 50% for icon
buttons only.

### P2 — The accent has two identities

`--color-accent` is `#35506E` (cool slate blue) in schemes 1/3/5 and `#E8CBAE`
(warm sand) in schemes 2/4. The same semantic slot changes hue family as the
page scrolls. `--color-sale` splits three ways: `#9A3B2B`, `#EE9781`, `#F6BCAB`.

The slate blue is also the only cool element on a warm cream page, which is why
the testimonial stars and PREORDER badge read as off-brand.

### P3 — Cream and pure white sit adjacent

Homepage band backgrounds, in order: `#2F2823` (hero) → `#F7E9E4` (marquee) →
`#FBF6F0` → `#FBF6F0` → `#F7E9E4` → `#FBF6F0` → `#FBF6F0` → `#FFFFFF` →
`#2F2823` (footer).

`reviews-band` at `#FBF6F0` against `best-sellers` at `#FFFFFF` is a 5-point
shift. Too small to read as intent, large enough to read as a rendering fault.
Blush also appears twice at arbitrary intervals.

### P4 — Padding is disproportionate to content

`layout_density: spacious` applies a ×1.25 multiplier, and bands carry 50px/50px
padding. But `sizes-band` is 279px tall in total, so padding dominates content.
The hero is 979px of dark brown with no image behind it — a void above the fold.

### P5 — Grid alignment: no defect (withdrawn)

Initially recorded as a defect after reading the rendered page. Reading
`snippets/product-card.liquid` disproved it: `.card__vendor` reserves
`min-height: 1.15em` and `.card__title` reserves `min-height: 2.4em` with
`-webkit-line-clamp: 2`, so a two-line title cannot displace the price.
Re-checking the collection screenshot confirms prices land within 1px across
a row, including the two-line "Amelia Bloomer Pant Set, Pink Microgingham".

No change required. Recorded so the claim is not reintroduced later.

### P6 — Mismatched product photography (highest leverage)

Each vendor supplies its own photo background: white, grey, lavender, ecru —
confirmed on the live collection page across Trotter Street Kids, Apple of My
Isla, The Uptown Baby and Footmates. Product media currently sits directly on
the section background,
so each card renders as a visibly mismatched rectangle against cream. Neither
reference site has this problem — both are single brands shooting one lookbook.

This is the defining visual problem of a multi-brand boutique and it is mostly
not a color problem.

### P7 — Scaffold leftovers

`sections/hello-world.liquid` carries hardcoded `#f6f6f7`, `#eef3ff`, `8px` and
`4px`, and is referenced by no template. Delete.

`sections/custom-section.liquid` is Skeleton scaffold but merchant-addable via
presets, and carried neither a colour scheme nor section spacing — so adding it
would produce a band outside the system. Wire both up rather than delete.

`assets/critical.css` sets `border-radius: 2px` inside `:focus-visible`. This is
worse than a hardcoded value: it restyles the *element's own* corners on focus,
so a 10px chip snapped to 2px when focused. Browsers already draw `outline`
following the element's radius, so the declaration is removed outright.

`snippets/product-card.liquid` carries `.card__swatch` / `.card__swatch-more`
rules for classes the markup never renders (it renders `.card__variant`). Dead.

**Withdrawn:** `sections/collection-tiles.liquid:155` `color: #fff` was recorded
as a defect. It is correct — the label sits on a black scrim over a photograph,
so it must be white in every scheme; tokenising it would resolve to near-black
on light schemes and vanish. A comment is added so it is not "fixed" later.

## Direction

**Heirloom Soft.** Cream ground, one soft radius language, quiet chrome, and a
single heritage-navy accent. Childhood is carried by the stitched seam and a
scalloped band edge — sewn-garment references native to a pinafore — not by
pastel chrome. The chrome recedes so that 60 brands' photography can coexist.

## Design

### D1 — One radius language

Rewrite the preset table in `css-variables.liquid` so no preset can produce a
clash:

| preset  | control | card | media |
|---------|---------|------|-------|
| sharp   | 0       | 0    | 0     |
| soft    | 6       | 8    | 8     |
| round   | 10      | 12   | 12    |

Store uses `round`. `style_button_shape` is set to `inherit` so buttons take
`--radius-control`; the `pill` option remains available to merchants but is no
longer selected.

Exactly two shapes ship: **rounded rectangles at 10–12px**, and **true circles**
(`50%`) reserved for color swatches, icon-only buttons (search, account, cart,
carousel arrows), and quantity steppers. Brand chips, size chips, filter
controls and badges move from 999px to `--radius-control`.

### D2 — One accent hue, two lightness variants

The accent keeps one hue identity site-wide. Light and dark schemes select
different *lightness* of the same hue, never a different hue.

| token | light schemes (1, 3, 5) | dark schemes (2, 4) |
|-------|-------------------------|---------------------|
| `--color-accent` | `#22406B` navy | `#A8C0DC` chambray |
| `--color-sale`   | `#9A3B2B` brick | `#E2907F` clay |

Sand `#E8CBAE` is removed from the accent slot entirely.

Every pairing is validated for WCAG contrast against its own scheme background
before commit: accent-as-text ≥ 4.5:1, `--color-border-control` ≥ 3:1.

### D3 — Band rhythm

Cream `#FBF6F0` is the ground. Rules:

- **Cream and white are never adjacent.** `scheme_5` (`#FFFFFF`) is retired from
  storefront use; the best-sellers band moves to cream.
- **Blush** `#F7E9E4` appears at most twice per page, never adjacent to another
  tinted band, always separated by at least two cream bands.
- **Ink** `#2F2823` is reserved for the hero and footer.
- `scheme_4` (sage) is retuned to pair with navy but is unused on the homepage.

### D4 — Product media plate

Every product image renders on its own fixed plate rather than directly on the
section background:

- Fixed `1 / 1` ratio, `object-fit: contain`, consistent internal padding
- Plate background is a new `--color-media-plate` token, fixed at `#FFFFFF` on
  light schemes and `#F6F1EA` on dark schemes. It is deliberately *not* derived
  from `--color-background`, so the plate stays constant while bands change.
- `--radius-media` corners and a 1px `--color-border` hairline, so a product
  shot on true white still reads as a card

**What this does and does not fix.** It does not remove a vendor's photo
background — `contain` letterboxes it rather than erasing it. What it fixes is
that **every tile's outer boundary becomes identical**. Today images are
`object-fit: cover`, so a vendor's white ground fills the tile edge-to-edge and
a grey ground fills it with grey, producing rectangles of varying colour butted
against cream at different sizes. With a constant plate and an inset `contain`
fit, every card presents the same frame and the vendor's ground is demoted to an
interior detail.

Genuinely normalising the photography needs the merchant to reshoot or
background-remove, which is out of scope here.

### D5 — Spacing and alignment

- `layout_density` moves from `spacious` to `default` (×1.0); `--section-spacing` becomes
  `clamp(2rem, 1.5rem + 2vw, 3.5rem)`, giving 4–7rem between bands.
- Short bands (marquee, sizes, brands) take a reduced-padding modifier so
  padding never dominates their content.
- Hero: no arbitrary height cap. Reading `sections/hero.liquid` located the
  actual defect — `min-height` applies the merchant's height setting whether or
  not an image exists, and `.hero__content` is `align-self: end`, so a hero with
  no photograph paints a full slab of scheme colour with the copy pinned to its
  bottom edge. A `.hero--no-media` modifier drops `min-height` to 0 and centres
  the content, making it a typographic band sized by its content. The full-bleed
  treatment returns automatically once an image is set. The height setting is
  left alone: at 75svh *with* an image it is a normal hero and overriding a
  merchant's choice would be wrong.
- Product card row alignment already works (see P5); left alone.

### D6 — Type

Playfair Display + Karla is kept — it mirrors the serif-display / sans-body
structure of both references (Lora + Montserrat; SangBleu + Serenity).

- `type_heading_scale` 115 → 105. At 115 the `--text-4xl` step reached 6.3rem.
- `type_heading_letter_spacing` stays at -1. The setting is a `step: 1` range in
  hundredths of an em, so -0.5 is not representable; -1 resolves to -0.01em,
  which at display sizes is within a hair of the -0.5px Lora carries on
  poshpeanut.com.
- The vendor eyebrow moves from `--text-2xs` (~11px) to `--text-xs` for
  legibility. Tracking stays at `0.12em` uppercase; both references do this.

### D7 — Childhood motifs

1. **Stitched seam.** Already defined in the token layer as a dashed gradient.
   Promoted to the theme's sole structural divider between bands.
2. **Scalloped edge.** CSS-only radial-gradient mask on the bottom edge of
   feature bands. References pinafore hems, bibs and baby blankets — childhood
   without pastel cliché, at zero image or JS cost.

Nothing else. No patterns or illustration competing with 60 brands' photography.

### D9 — Navigation and discovery

Navigation is reachable via the Admin GraphQL `menus` / `menuUpdate` API, so it
is in scope. Current `main-menu` is Home / Catalog / Contact — placeholder.

Per Shopify's faceted-navigation guidance, facets belong on category pages as
*supplementary refinement*, not as primary discovery. A sitewide mega-menu is
the strongest internal-link signal on the site, so it must point at real,
indexable collections — never at filter URLs.

**Structure:**

```
New · Girls ▾ · Boys ▾ · Baby ▾ · Shoes · Accessories ▾ · Brands ▾ · Sale
```

Shoes (3 products) and Collegiate (1) stay flat — a dropdown onto three items
reads emptier than no dropdown.

**Sub-items** are automated collections with `TAG AND TYPE` rules, so they
self-maintain as inventory grows. Only intersections holding ≥3 products earn a
page:

| collection | rule | count |
|---|---|---|
| girls-dresses | tag Girls + type Dresses | 5 |
| girls-bubbles | tag Girls + type Bubbles | 3 |
| girls-bags | tag Girls + type Bags | 3 |
| boys-hats | tag Boys + type Hats | 4 |
| boys-tops | tag Boys + type Tops | 4 |
| baby-dresses | tag Baby + type Dresses | 4 |
| baby-rompers | tag Baby + type Rompers | 3 |
| baby-pajamas | tag Baby + type Pajamas | 3 |
| baby-outerwear | tag Baby + type Outerwear | 3 |

Everything below the threshold (Girls/Socks 2, Boys/Shoes 1, Baby/Sets 2, …)
stays reachable through facets only. The threshold is re-evaluated when the full
catalog lands; these counts reflect the 47-product seed.

**Brands** dropdown lists vendors, linking to `/collections/vendors?q=<vendor>`.
This is a bounded set of 12 real listing pages, not a combinatorial facet
space, so it does not carry the sprawl risk that keeps facets out of the menu.
Per-vendor automated collections would give cleaner URLs and is the natural
upgrade if brand pages become a priority.

**Collections created through the Admin API are not published to any sales
channel.** `collectionCreate` succeeded and `productsCount` was correct, but
every new collection returned 404 on the storefront because
`resourcePublications` was empty — where the pre-existing `girls` collection
showed `Online Store: isPublished true`. Each new collection needs a
`publishablePublish` call against the Online Store publication
(`read_publications` / `write_publications` to find and set it). Requesting
`publishedOnCurrentPublication` in the mutation response additionally requires
`read_product_listings`; omit it unless that scope is granted.

Menu items bind by `resourceId` (type `COLLECTION`) rather than URL string, so
renaming a collection handle cannot break the navigation.

Verification: every menu destination is fetched and asserted 200 — 29 URLs,
including all vendor links.

### D10 — Indexation hygiene

Three defects found in `snippets/meta-tags.liquid` and `layout/theme.liquid`:

1. **Two canonical tags per page.** `theme.liquid:7` and `meta-tags.liquid:95`
   both emit `<link rel="canonical">`. Remove the one in `theme.liquid`.
2. **Duplicated head meta.** `charset` and `viewport` are emitted in both files;
   `meta-tags.liquid` also adds a legacy `X-UA-Compatible`. Deduplicate.
3. **No robots meta anywhere.** Every facet combination is currently indexable.

Fix: `meta-tags.liquid` owns SEO/social meta, `theme.liquid` owns document meta,
and the canonical is emitted exactly once. `<meta name="robots"
content="noindex,follow">` is emitted when a collection has active filters
(including price-range bounds), when the URL is a `/collections/<x>/<tag>` path,
or on internal search results.

**Pagination is deliberately excluded**, correcting an earlier draft of this
spec. Once Google settles on a page as `noindex` it stops crawling it, and
`follow` stops being honoured — so noindexing page 2+ eventually strips the
internal links to products that appear only deep in a collection. Paginated
pages stay indexable with a self-referencing canonical.

### D8 — Cleanup

Delete `hello-world.liquid`. Audit `custom-section.liquid` for scaffold status.
Replace the hardcoded values in `collection-tiles.liquid` and `critical.css`
with tokens.

## Revision — palette replaced with "Sugar" (2026-08-12)

D2 and D3 above describe the cream/navy palette as originally shipped. It was
correct on its own terms — 72% warm cream, one accent — but reviewed as too
reserved for the shop's audience. Five genuinely distinct directions were put up
side by side on real product photography; **Sugar** was chosen. The reasoning
above is kept rather than rewritten, because the diagnosis it records (one
radius language, one accent hue, no cream/white adjacency) still governs — only
the hues changed.

| token | page | tinted band |
|---|---|---|
| background | `#FFF4EC` peach cream | `#F6CFC2` strawberry |
| text | `#3E2622` | `#40241E` |
| accent / sale | `#B4402F` cherry | `#A5382A` |
| plate | `#FFFBF7` | — |

Structural consequences:

- **No band is dark.** The hero moves from `scheme_2` to `scheme_1` and the
  footer from `scheme_2` to `scheme_3`. The ink schemes remain defined and
  contrast-valid but are unused on the storefront — removing the dark mass is
  most of what makes this palette read warm.
- **Accent and sale collapse to one warm red family.** The navy/chambray split
  is gone. Nothing cool remains anywhere in the theme, including the dynamic
  checkout button, which inherits the accent.
- **The plate warms** from `#FFFFFF` to `#FFFBF7`. This deliberately accepts a
  small amount of the vendor-photo mismatch described in D4: brands shooting on
  true white now show a faint rectangle. At a 0/4/8 per-channel delta it is
  barely perceptible, and it was judged worth it to stop the grid reading as
  clinical. If it ever grates, `--color-media-plate` is a one-line revert.
- Contrast revalidated: 45 pairings across 5 schemes, all passing.

## Scope

In scope: token layer, homepage bands, collection/PLP, product/PDP, cart drawer,
header, footer, mega-menu component, navigation content via Admin API, the nine
automated collections in D9, and indexation hygiene.

Out of scope: product photography, marketing copy, and the "60+ brands" claim in
the marquee (merchant copy, and currently inaccurate against the seeded catalog).

## Verification

- Contrast validated per scheme for accent-as-text and control borders
- Radius audit: no `border-radius` outside `--radius-*` tokens; no `999px`
  outside chips that opt in
- Band-order audit: no cream/white adjacency on any template
- Visual regression: homepage, collection, product, cart drawer screenshotted
  before and after at desktop and mobile widths
