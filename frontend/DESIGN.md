---
name: Veritas-Chain explorer
description: A packet-analyzer dissection of a synthetic criminal-network graph and its tamper-evident audit chain.
colors:
  ground: "#0b0f13"
  canvas: "#10151b"
  panel: "#141a21"
  raised: "#1a222b"
  hover: "#1f2832"
  well: "#0c1015"
  rule: "#232d37"
  rule-strong: "#33404d"
  ink: "#e4eaef"
  ink-secondary: "#aab5c0"
  ink-muted: "#85919d"
  ink-faint: "#77838f"
  state-verified: "#0ca30c"
  state-verified-text: "#3cc75a"
  state-no-anchor: "#fab219"
  state-no-anchor-text: "#f5b83d"
  state-tampered: "#e5484d"
  state-tampered-text: "#ff8078"
  state-tampered-ground: "#1d1012"
  state-tampered-rule: "#5c2227"
  entity-person: "#dde4ea"
  entity-phone: "#199e70"
  entity-account: "#c98500"
  entity-organization: "#9085e9"
  entity-event: "#3987e5"
  entity-vehicle: "#d95926"
  entity-location: "#d55181"
typography:
  headline:
    fontFamily: "Atkinson Hyperlegible Next Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Atkinson Hyperlegible Next Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Atkinson Hyperlegible Next Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Atkinson Hyperlegible Next Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.06em"
  data:
    fontFamily: "Atkinson Hyperlegible Mono Variable, ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  xl: "12px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
components:
  button:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "28px"
    padding: "0 10px"
  button-hover:
    backgroundColor: "{colors.hover}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.md}"
    height: "28px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
  segmented-control:
    backgroundColor: "{colors.well}"
    rounded: "{rounded.md}"
    height: "24px"
  segment-checked:
    backgroundColor: "{colors.rule-strong}"
    textColor: "{colors.ink}"
  chip:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.sm}"
    height: "20px"
  chip-tampered:
    backgroundColor: "{colors.state-tampered-ground}"
    textColor: "{colors.state-tampered-text}"
  ranking-row-selected:
    backgroundColor: "{colors.entity-person}"
    textColor: "{colors.canvas}"
  audit-block-failing:
    backgroundColor: "#140a0c"
    textColor: "{colors.state-tampered-text}"
---

# Design System: Veritas-Chain explorer

## Overview

**Creative North Star: "The Dissection"**

The explorer reads like a packet analyzer turned on a case graph. You pick from a list, the selection is taken apart into labelled fields, its hash blocks sit in a hex well underneath, and an expert-info light reports whether the chain holds. Integrity is not a buried button: it is a permanent band across the top, drawn to scale.

The chrome is graphite and quiet so the evidence can be loud. Saturated colour has exactly two jobs, telling entity types apart and reporting chain state, and everything else is ink on graphite with 1px rules. Density is an instrument's density: small type, tabular data, many fields, no decoration standing in for content. The one dramatic moment is failure: a tampered block turns its row, its band and its evidence red on near-black, wherever it appears.

It is dark by use, not by genre: 1,633 hairline links read as structure on graphite and as grey fog on white. It rejects both the neon hacker terminal and the white SaaS dashboard.

**Key Characteristics:**
- Graphite panels separated by 1px rules; no cards inside panes.
- Colour only for entity identity and chain state.
- One humanist family for the interface, its mono sibling for identifiers, hashes, amounts and scores.
- Stored values print plainly; anything the page computes sits in muted brackets.
- The chain is always on screen, to scale, with the selection's blocks marked on it.

## Colors

A graphite ground with seven evidence hues and a reserved three-state signal, nothing else.

### Primary
- **Ink** (`ink`): text, the focus ring, the selected ranking row and the primary button. It is also the Person colour, so selecting a person carries its identity into the list.

### Neutral
- **Ground** (`ground`): behind every pane, the page itself.
- **Canvas** (`canvas`): the graph's field; the base of every contrast check.
- **Panel** (`panel`): rankings, evidence, top bar, integrity band, status bar.
- **Raised / Hover** (`raised`, `hover`): controls at rest and under the pointer; floating cards.
- **Well** (`well`): the audit trail, segmented tracks, the view expression field: places data is read, not operated.
- **Rules** (`rule`, `rule-strong`): every separation between panes and rows.
- **Secondary, muted and faint ink** (`ink-secondary`, `ink-muted`, `ink-faint`): field values, field names and meta, and hash prefixes. Muted ink holds 5:1 on every panel; faint ink holds 4.5:1 on the grounds it sits on (sunken wells and the canvas), so every text colour in the token set meets WCAG AA (4.5:1) where it is used.

### Entity identity
- **Person** (`entity-person`), **Phone** (`entity-phone`), **Bank account** (`entity-account`), **Organization** (`entity-organization`), **Event** (`entity-event`), **Vehicle** (`entity-vehicle`), **Location** (`entity-location`). Each pairs with its own shape (circle, small circle, square, rounded square, diamond, hexagon, triangle). The source of truth is `src/graph/theme.ts`, which draws both the graph and the legend.

### Chain state
- **Verified** (`state-verified`, text `state-verified-text`), **No anchor** (`state-no-anchor`, text `state-no-anchor-text`), **Tampered** (`state-tampered`, text `state-tampered-text`, ground `state-tampered-ground`, rule `state-tampered-rule`).

### Named Rules
**The Only-Evidence-Glows Rule.** Chrome is monochrome. A saturated colour on screen means an entity type or a chain state; if it means neither, it is wrong.

**The Validated Palette Rule.** Entity colours were checked with a colour-vision validator on the canvas: every pair of types that shares a link differs by ΔE ≥ 15.9 under protanopia and deuteranopia and ≥ 26.5 in normal vision. Person is ink because people link to all six other types. A new type or a changed hue is re-validated, never eyeballed.

**The Reserved Red Rule.** Red belongs to tampering. No entity, link family or decorative element may use it, and it always arrives with a shield icon and a label.

## Typography

**Interface Font:** Atkinson Hyperlegible Next (with Segoe UI, system-ui)
**Data Font:** Atkinson Hyperlegible Mono (with ui-monospace, Cascadia Mono, Consolas)

**Character:** A legibility family drawn to keep 0/O, 1/l/I and 5/S apart, which is exactly where IFSC codes, number plates, account numbers and hashes get misread. Humanist enough to stay calm at 11px.

### Hierarchy
- **Welcome heading** (700, 22px, 1.2): the first-load panel only.
- **Headline** (700, 20px, 1.15–1.2): the selected entity or link, and the chain state.
- **Title** (600, 14px): pane titles.
- **Body** (400, 13px, 1.4): table rows, descriptions, controls.
- **Field** (400, 12px): dissection fields, secondary text, block descriptions.
- **Label** (600, 11px, 0.06em, uppercase): group labels inside a list and legend headings. Never above a heading.
- **Data** (mono, 11–12px, tabular): ids, hashes in groups of eight, scores, counts, timestamps, the view expression.

### Named Rules
**The Mono-Is-Data Rule.** Mono is used only for things a machine wrote: identifiers, hashes, amounts, scores, counts, timestamps, request lines. Never for labels or prose.

**The Brackets Rule.** A value the API stores prints as-is; a value the page derived follows it in muted brackets, e.g. `1.00 [ordinal weight, not a probability]`.

## Layout

A fixed instrument layout for laptop and desktop screens (minimum 960px wide, with a notice below that):

- top bar (44px);
- integrity band (76px at rest, expanding with findings on failure);
- three columns: rankings `clamp(232px, 19vw, 288px)`, the graph, and evidence `clamp(330px, 27vw, 392px)`;
- status bar (26px).

The evidence column stacks the dissection over the audit trail. The trail sizes to its blocks up to 45% of the column, so a single record leaves the dissection more room.

Spacing runs on a 4px base (4, 8, 12, 16, 24). Panes use 14px side padding; dissection fields indent 34px under their disclosure chevron.

**The Clear-Of-Overlays Rule.** Camera fits keep the graph clear of the legend (above it or beside it, whichever allows the larger zoom) and of the welcome panel while it is open.

## Elevation & Depth

Flat by default. Panes separate by 1px rules and tonal steps (ground, panel, raised, well). Exactly three things float and carry a shadow: the hover preview, the welcome panel and open listboxes.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45)`): hover preview, listbox.
- **Dock** (`box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5)`): the welcome panel.

## Shapes

Small, even corners that read as instrument controls: 4px for chips, op tags and segments; 6px for buttons, fields and segmented tracks; 8px for the legend, hover card, listbox and starting points; 12px for the welcome panel only. Graph marks use shape as a second channel for type, never decoration. The chain strip is a 2px-radius bar with 1.5px ticks and a 3px head cap.

## Components

### Buttons
- **Shape:** 6px radius, 28px tall (24px small).
- **Default:** raised graphite, ink text, strong rule; hover lifts to the hover tone.
- **Primary:** ink fill with canvas text; reserved for Verify before a chain has been checked.
- **Ghost:** no fill, secondary ink; for dismissals and secondary actions.
- **Press:** scales to 0.97 over 160ms; none under reduced motion.

### Segmented controls and listbox
- **Segmented:** a well-toned track with 2px inset; the checked segment takes the strong rule tone. Arrow keys move and select.
- **Listbox:** a custom select whose options carry a one-line explanation; opens in 140ms from 4px above, keyboard complete (arrows, Home/End, Enter, Escape).

### Chips
- **Style:** raised, 1px rule, 11px secondary ink, 20px tall. Tone variants add a state icon: verified and no-anchor tint only the icon; tampered tints text, ground and rule.

### Integrity band (signature)
State readout with shield icon, the chain strip drawn to scale with the selection's blocks as ink ticks and failing blocks as red ticks at their index, and the head hash. On failure the band takes the tampered ground and opens a findings table with "Inspect the changed link" and "Copy findings".

### Dissection pane (signature)
Headline, then a type line (glyph, type, id), then chips, then collapsible sections (Stored attributes, Provenance grouped by structured records and report text, Links, Record, All records). A 2px top rule in the selection's entity or link-family colour. A failing record's section moves first, and a graph-versus-log amount mismatch renders as a two-cell red comparison.

### Audit block
Index in mono, operation tag, UTC time, one-sentence description, hash and previous hash in groups of eight. A block that fails verification takes the bad-checksum treatment: red text on near-black with a "hash check failed" chip.

### Hover preview
Title first, type line, id, and two or three facts in mono. Appears after 250ms of rest, instantly when moving from one mark to the next, and hides on click.

## Do's and Don'ts

### Do:
- **Do** take every entity colour and shape from `src/graph/theme.ts`, so the graph and the legend can't disagree.
- **Do** pair every chain-state colour with its shield or warning icon and a word.
- **Do** keep labels at a fixed screen size and let context fade to 14% opacity rather than disappear.
- **Do** keep camera moves at 380ms ease-in-out and interruptible, and jump instead of flying under reduced motion.
- **Do** show loading as the requests being waited on, and failures with the recovery (`npm run dev`, Try again).

### Don't:
- **Don't** put a small uppercase label above a heading; the type line goes under the title.
- **Don't** use red, or any saturated colour, for chrome, decoration or a new series.
- **Don't** use mono for labels or prose.
- **Don't** add borders, cards or shadows inside panes; separate with 1px rules.
- **Don't** imply data the API doesn't serve (communities, anomaly flags, evidence sentences).
