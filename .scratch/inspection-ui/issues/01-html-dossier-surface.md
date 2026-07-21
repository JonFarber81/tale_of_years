# 01 — HTML dossier surface + shared anatomy

**What to build:** Swap the Inspection dock's plain `QLabel` for a
`QTextBrowser` and introduce the shared dossier anatomy every selection kind
renders through: banner, stat grid, section headers, identity accent. The
foundation ticket — 02 and 03 build on these primitives.

**Blocked by:** —

**Status:** ready-for-agent

- [ ] The Inspection dock hosts a `QTextBrowser` (read-only, scrollable,
      selectable); long dossiers scroll instead of overflowing.
- [ ] A dossier-HTML helper module (e.g. `ui/dossier_html.py`) provides the
      shared primitives, pure functions returning HTML strings:
      - **banner**(kind_tag, name, accent_color) — small dimmed kind-tag
        (FACTION / HOST / SITE / TILE / EVENT) over the name in large bold,
        with a colored accent bar;
      - **stat grid**(label→value pairs) — compact rows, dimmed small
        labels, full-weight values;
      - **section header**(title) — small dimmed caps, real spacing, no
        ASCII rules.
- [ ] Identity accent sourcing: a faction subject (and its hosts/sites)
      wears `tile_render.faction_color`; an event wears its bucket color
      from `annals_style`; unowned/neutral subjects get a palette-derived
      neutral. Colors legible on light and dark palettes.
- [ ] The existing describe paths render through the new primitives at
      current content (banner + sections; the content *restructure* is
      ticket 02 — this ticket may keep today's stacking order).
- [ ] The event dossier migrates onto the same surface: banner absorbs
      year / bucket / notable-vs-minor; the prose body is unchanged.
- [ ] HTML is escaped where names/prose are interpolated (a site or leader
      name containing `<` or `&` must not break rendering).
- [ ] Tests cover: banner/grid/section helpers emit well-formed HTML,
      escaping, accent sourcing (faction vs event vs neutral), and the
      dock-level swap (clicking still populates the browser).

## Comments
