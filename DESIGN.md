---
name: Dinheiro do Povo
description: Quanto custam e como trabalham deputados e senadores, etiquetado como preço de encarte, com a fonte oficial de cada número.
colors:
  amarelo: "#ffd60a"
  amarelo-escuro: "#f2c400"
  tinta: "#111111"
  tinta-2: "#3d3d3d"
  tinta-amarelo: "#4a3d00"
  papel: "#ffffff"
  papel-2: "#f6f5f0"
  linha: "#dedbd0"
  carimbo: "#1e40af"
  verde: "#12803f"
  vermelho: "#c81e1e"
  s-salario: "#2348c9"
  s-cota: "#c08a00"
  s-verba: "#11845a"
  s-auxilio: "#8a3fb0"
  s-referencia: "#8a8a8a"
typography:
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(2.1rem, 7.2vw, 3.6rem)"
    fontWeight: 850
    lineHeight: 1.02
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 68"
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(1.7rem, 5.6vw, 2.5rem)"
    fontWeight: 850
    lineHeight: 1.02
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 68"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 850
    lineHeight: 1.02
    fontVariation: "'wdth' 68"
  price:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(3rem, 21cqi, 6.6rem)"
    fontWeight: 900
    lineHeight: 0.86
    letterSpacing: "-0.015em"
    fontVariation: "'wdth' 62"
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.5
    fontVariation: "'wdth' 100"
  label:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 800
    lineHeight: 1.15
    fontVariation: "'wdth' 72"
  caption:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 650
    lineHeight: 1.25
    fontVariation: "'wdth' 100"
rounded:
  mark: "4px"
  tag: "6px"
  stamp: "7px"
  field: "9px"
  tile: "10px"
spacing:
  hair: "3px"
  xs: "6px"
  sm: "10px"
  md: "12px"
  tile: "16px"
  tile-wide: "22px"
  section: "18px"
components:
  etiqueta:
    backgroundColor: "{colors.amarelo}"
    textColor: "{colors.tinta}"
    typography: "{typography.price}"
    rounded: "{rounded.field}"
    padding: "8px 14px 6px 12px"
  tag-prateleira:
    backgroundColor: "{colors.amarelo}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.tag}"
    padding: "3px 7px 2px"
  carimbo:
    backgroundColor: "rgba(255,255,255,.6)"
    textColor: "{colors.carimbo}"
    rounded: "{rounded.stamp}"
    padding: "3px 10px"
  carimbo-hover:
    backgroundColor: "{colors.carimbo}"
    textColor: "{colors.papel}"
  ladrilho:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.tile}"
    padding: "{spacing.tile}"
  busca:
    backgroundColor: "{colors.papel}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.field}"
    padding: "0 14px"
    height: "50px"
  topo:
    backgroundColor: "{colors.tinta}"
    textColor: "{colors.papel}"
  nav-baixo:
    backgroundColor: "{colors.tinta}"
    textColor: "{colors.papel}"
    height: "64px"
  nav-baixo-ativo:
    textColor: "{colors.amarelo}"
---

# Design System: Dinheiro do Povo

## Overview

**Creative North Star: "Encarte do Povo"**

The site is a Brazilian supermarket flyer turned into a transparency portal. Every page sits on a flat flyer-yellow field; content lives on white tiles outlined in 2px ink; the cost of a parliamentarian is printed as a shelf price tag with superscript cents, beside the everyday things that money buys (minimum wages, food baskets, plane tickets, square metres). Every number carries a blue rubber stamp that links to the official source it came from.

The flyer gives the material, not the voice. The tag, the stamp, the shelf and the flat clip-art objects are borrowed; the promo grammar (starbursts, "OFERTA", "IMPERDÍVEL", exclamation copy) is excluded, and the copy reads as neutral portal text. The system refuses both the blue government data table and the red protest poster: red appears only inside the ✕ presence mark.

Density is mobile-first and generous: one column of tiles on a phone, a two-column hero and multi-column shelves on desktop, body text always at reading size, charts built in HTML so their labels never shrink.

**Key Characteristics:**
- Flat yellow field, white tiles, 2px ink outlines, no decorative shadows.
- One variable family (Archivo) on two axes: condensed 62–75% width for display, prices and labels; 100% width for body.
- Price tag as the largest object in its frame; cents superscript.
- A source stamp on every number; every R$ value also stated in minimum wages.
- State shown by mark shape (✓ J ✕), not by color alone.

## Colors

A flyer palette: one saturated yellow field, ink black, paper white, one stamp blue, and a separate CVD-validated series palette reserved for charts.

### Primary
- **Flyer Yellow** (amarelo): the page field behind everything, and the fill of every price tag and shelf tag. The yellow is the ground, so tags read as the field showing through an ink outline.
- **Stamp Blue** (carimbo): source stamps, text links inside tiles, the "Ver em tabela" disclosure, focus rings, the J mark, the highlighted bar in comparison charts and patrimony columns.

### Neutral
- **Ink** (tinta): all text, tile outlines, the black top band and bottom nav, the "Todos" reference bar in comparisons.
- **Soft Ink** (tinta-2): secondary text on white (captions, chart labels, minimum-wage lines).
- **Yellow Ink** (tinta-amarelo): secondary text set directly on the yellow field (footer, notes under shelves), where gray would muddy.
- **Paper** (papel) and **Shelf Paper** (papel-2): tile fill and the hover / reference-row fill.
- **Dotted Rule** (linha): table rules, chart baselines, row dividers inside tiles.
- **Deep Yellow** (amarelo-escuro): scrollbar track only.

### Chart series (validated for color-vision deficiency and contrast on white)
- **Salário Blue** (s-salario), **Cota Ochre** (s-cota), **Verba Green** (s-verba), **Auxílio Violet** (s-auxilio), **Reference Gray** (s-referencia, the minimum-wage reference and non-highlighted bars).

### Mark colors
- **Present Green** (verde): fill of the ✓ mark only.
- **Absence Red** (vermelho): fill of the ✕ mark only.

### Named Rules
**The Red Is a Mark Rule.** Red (#c81e1e) exists only as the fill of the ✕ "absence without justification" mark. Never use it for text, alerts, emphasis, headlines, or chart series.

**The Series Stay in Charts Rule.** The five series colors encode the four cost components and the reference, consistently on every page (salário, cota, verba, auxílio, salário mínimo). Do not reuse them as UI accents, and do not swap their order or meaning.

**The Ink Labels Rule.** Chart text is always ink, never the series color.

## Typography

**Display Font:** Archivo variable (self-hosted `archivo-var.woff2`, weight 100–900, width 62–125%), fallback system-ui, sans-serif
**Body Font:** Archivo at 100% width
**Label Font:** Archivo condensed (68–75% width)

**Character:** One family doing two jobs by its width axis: compressed, heavy, flyer-price numerals for anything that is a headline, a price or a label, and a calm full-width text face for reading.

### Hierarchy
- **Price** (900, 62% width, fluid by container: `clamp(3rem, 21cqi, 6.6rem)` inside the price block; 0.86 line-height): the cost tag. Currency at 0.46em and cents at 0.38em, both top-aligned as superscripts.
- **Display** (850, 68% width, `clamp(2.1rem, 7.2vw, 3.6rem)`, 1.02): page H1, balanced wrap.
- **Headline** (850, 68% width, `clamp(1.7rem, 5.6vw, 2.5rem)`, 1.02): section H2.
- **Title** (850, 68% width, 1.35rem): tile H3.
- **Big numerals** (900, 62–68% width, 1.25–4.6rem, ~0.84–1 line-height): equivalence quantities, shelf values, presence counts, the wordmark (900, 62%, uppercase).
- **Label** (750–800, 70–75% width, 0.9–1.15rem): price captions, equivalence object names, table headers, stamps.
- **Body** (400, 100% width, 17px, 1.5): paragraphs, max 68ch (72ch in long text), pretty wrap.
- **Caption** (600–650, 100% width, 0.875rem): evidence states, minimum-wage lines, chart labels, "cada" lines.

### Named Rules
**The Two Widths Rule.** Condensed width (62–75%) is for display, prices, numerals and labels; running text is always 100% width. Never set a paragraph condensed.

**The Superscript Cents Rule.** A price shown as a tag splits into R$ / integer / cents, with currency and cents raised and reduced. Inline prices in prose stay plain `R$ 46.366,19`.

**The Tabular Rule.** Every numeric column, chart value and table cell uses tabular numerals.

## Layout

Single max-width column (1120px) of tiles on the yellow field. Phone: 16px page padding, 18px vertical gap between blocks, tiles padded 16px. At 760px and up: 24px page padding, 22px gaps, tiles padded 22px, the top band becomes a three-column row (wordmark, search, nav) and the bottom nav disappears. The hero splits 1.15fr / 1fr (price tile beside equivalence tiles); equivalence grids go 2 → 3 columns, and 6 at 1100px.

The price block is a size container: the tag scales with its own width (`21cqi`), so it is always the largest object in its tile whatever the viewport.

Spacing is a small set of steps: 3px between counted marks and pile items, 6px inside label stacks, 10–12px between tiles and grid cells, 16/22px tile padding. Party shelves stack as rows inside one outlined gondola; on phones (≤480px) each shelf value becomes a label-left / value-right line.

## Elevation & Depth

Flat. Depth comes from the ink outline and the contrast of white tiles on yellow, never from shadows. The single shadow in the system belongs to a floating overlay: the search results panel, which must detach from the black band.

### Shadow Vocabulary
- **Overlay lift** (`box-shadow: 0 10px 28px rgba(0,0,0,.28)`): search results dropdown only.

### Named Rules
**The Outline Not Shadow Rule.** A surface is separated by a 2px ink border on yellow. Tiles, cards, tags and stamps carry no shadow; only true floating overlays may.

## Shapes

Soft-cornered print rectangles with ink outlines. Radii step with object size: 4px marks and chart bar tips, 6px shelf tags and vote boxes, 7px stamps and party seals, 9px price tags and inputs, 10px tiles. Borders are 2px ink by default, 3px on the large price tag and big seal, 2.5px on stamps. Chart bars have a straight base and a 4–5px rounded data end. Dotted 2px ink rules divide the footer of an equivalence tile, like a coupon perforation. The source stamp is the only rotated shape (-2deg).

## Components

### Price tag (etiqueta)
The signature object. Yellow fill, 3px ink border, 9px radius, condensed 900 numerals, superscript currency and cents, never wraps. Sizes: large inside the price block (container-query sized, full tile width), medium, and small (1.9rem, 2.5px border). Always followed by a "por mês" label and a minimum-wage line, and sits with a source stamp.

### Source stamp (carimbo)
A link that looks like a rubber stamp: stamp-blue text and 2.5px blue border, 7px radius, translucent white fill, condensed 750 label, external-link glyph, rotated -2deg. Hover fills blue with white text. The hero stamp lands with a one-time stamp animation (scale 1.22 / -7deg to rest, 0.5s, `cubic-bezier(.16,1,.3,1)`), removed under reduced motion. Every published number has one nearby.

### Evidence state (ev)
A caption line under a number declaring what kind of number it is: official (plain), our calculation (calculator glyph, olive-brown text), or delayed by the source (clock glyph).

### Presence marks (✓ J ✕)
24-unit circular SVG marks whose interior drawing carries the state: ✓ on green (present), J on stamp blue (justified absence), ✕ on red (unjustified absence); a hollow ink dash for no vote. Rendered day by day, 18px, in wrapping rows per month; each is focusable with a date tooltip.

### Equivalence tiles (eq)
White outlined tiles: a flat SVG object (ink 3px outline, filled with stamp blue, yellow and white only), a huge condensed quantity, the object name, and a dotted-rule footer with the unit price, date and a "fonte" link.

### Countable pile (pilha)
Cost shown as mass: repeated 26px flat objects with 3px gaps, capped at 60, then a condensed "+ N".

### Party shelf (gôndola / prateleira)
One outlined gondola; each party is a row (logo or ink seal with the acronym, name, member count) followed by three values. Cost appears as a small yellow shelf tag; presence leads with the ✓ mark; patrimony is a plain condensed numeral. The "Câmara inteira" row is the comparison baseline on shelf paper. Rows hover to shelf paper; a chevron points to the party page.

### Minimum-wage ruler (sm)
A caption line, "= N salários mínimos" (short form "sal. mínimos"), attached under every R$ value: tags, shelf values, table cells.

### Charts
HTML/CSS bars, max 24px thick, 2px gaps between segments, one shared scale per chart, ink value labels, black tooltip on hover/focus, and a "Ver em tabela" disclosure with the equivalent table. Months after the data cutoff are hatched in their series color.

### Search combobox
In the black top band: white field, 50px tall, 9px radius, white 2px border that turns yellow on focus, search glyph. Results open in a white outlined panel (the overlay shadow) with photo or seal, name, role and party; hovered/selected option fills yellow. Arrow-key navigation with `aria-selected`.

### Navigation
Desktop: black band with condensed uppercase wordmark, search, and white text links that turn yellow when current or hovered. Phone: fixed black bottom bar, four equal cells (Início, Buscar, Partidos, Semana) with 24px stroke icons over 0.82rem labels; current turns yellow. Focus rings in the dark bands are yellow; elsewhere 3px stamp blue.

### Icons
An authored SVG sprite: navigation icons on a 24-unit grid with ~2.2px round strokes in currentColor; presence marks; flat everyday objects. No icon font, no emoji.

## Do's and Don'ts

### Do:
- **Do** put content on white tiles with a 2px ink border and 10px radius over the yellow field.
- **Do** show a cost as a yellow price tag with superscript cents, and make it the largest object in its frame.
- **Do** link every number to its official source with a blue stamp or a "fonte" link, and label its evidence state.
- **Do** state every R$ value also in minimum wages.
- **Do** encode state by mark shape (✓ J ✕) with color only as reinforcement.
- **Do** use the five series colors for cost components and the reference, with ink labels, and pair every chart with an equivalent table.
- **Do** keep copy neutral, in the voice of a transparency portal.

### Don't:
- **Don't** use the flyer's promo grammar: no starbursts, "OFERTA", "IMPERDÍVEL", or sale exclamations.
- **Don't** use red for anything but the ✕ mark.
- **Don't** add shadows to tiles, tags or stamps; outline instead.
- **Don't** set running text in condensed width.
- **Don't** drift toward a blue government data table or a red protest poster.
- **Don't** generate paid images (Magnific or similar) without the user's explicit request; objects and icons are hand-authored SVG.
