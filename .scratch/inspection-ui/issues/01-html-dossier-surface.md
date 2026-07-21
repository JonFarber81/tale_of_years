# 01 — HTML dossier surface + shared anatomy

**What to build:** Swap the Inspection dock's plain `QLabel` for a
`QTextBrowser` and introduce the shared dossier anatomy every selection kind
renders through: banner, stat grid, section headers, identity accent. The
foundation ticket — 02 and 03 build on these primitives.

**Blocked by:** —

**Status:** done

- [x] The Inspection dock hosts a `QTextBrowser` (read-only, scrollable,
      selectable); long dossiers scroll instead of overflowing.
- [x] A dossier-HTML helper module (e.g. `ui/dossier_html.py`) provides the
      shared primitives, pure functions returning HTML strings:
      - **banner**(kind_tag, name, accent_color) — small dimmed kind-tag
        (FACTION / HOST / SITE / TILE / EVENT) over the name in large bold,
        with a colored accent bar;
      - **stat grid**(label→value pairs) — compact rows, dimmed small
        labels, full-weight values;
      - **section header**(title) — small dimmed caps, real spacing, no
        ASCII rules.
- [x] Identity accent sourcing: a faction subject (and its hosts/sites)
      wears `tile_render.faction_color`; an event wears its bucket color
      from `annals_style`; unowned/neutral subjects get a palette-derived
      neutral. Colors legible on light and dark palettes.
- [x] The existing describe paths render through the new primitives at
      current content (banner + sections; the content *restructure* is
      ticket 02 — this ticket may keep today's stacking order).
- [x] The event dossier migrates onto the same surface: banner absorbs
      year / bucket / notable-vs-minor; the prose body is unchanged.
- [x] HTML is escaped where names/prose are interpolated (a site or leader
      name containing `<` or `&` must not break rendering).
- [x] Tests cover: banner/grid/section helpers emit well-formed HTML,
      escaping, accent sourcing (faction vs event vs neutral), and the
      dock-level swap (clicking still populates the browser).

## Comments

**2026-07-21 (agent):** Implemented. `ui/dossier_html.py` holds the pure
primitives — `banner` (accent bar as a narrow colored table cell, since
Qt's rich-text subset has no border-left), `stat_grid` (None values drop
their row), `section`, `para`, `text_lines`, `pre_block` (bloodlines keep
their indentation) — with `esc()` escaping every interpolated name. The
dock is a `QTextBrowser` with `setOpenLinks(False)`, ready for the
cross-linking wishlist's anchors. All four describe paths render through
the primitives at today's content and stacking (tile banner + grid, host
banner + grid, faction banner + grid + DIPLOMACY / BLOODLINE / RECENT
EVENTS sections); `_describe_diplomacy` now returns bare lines and the
window wraps them. The event dossier's banner reads
`EVENT · <bucket> · notable|minor` over `TA NNNN` with the bucket-color
accent, sentence italicized, prose body unchanged. Verified with offscreen
renders of tile, host, and battle dossiers from a 30-year campaign run;
suite green.
