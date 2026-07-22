# CLAUDE.md

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues; use the `gh` CLI. See `docs/agents/issue-tracker.md`. Pre-2026-07 work is archived read-only as local markdown under `.scratch/<feature>/`.

### Triage labels

The five canonical triage roles, each label string equal to its name (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Module map

Which file does what (jump straight there instead of grepping): `docs/agents/map.md`.
Domain *terms* → `CONTEXT.md`; lasting *decisions* → `docs/adr/`; *which file* → the map.
