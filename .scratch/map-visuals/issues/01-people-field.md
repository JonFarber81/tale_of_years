# 01 — People: the broad folk a faction belongs to

**What to build:** A `people` field on `Faction` — domain data, not render
styling — authored on every roster seed. Foundation for the army-sprite
ticket (03), and available to any future rule that cares about folk.

**Blocked by:** —

**Status:** done

- [x] A `People` enum (or equivalent string-value set) in
      `src/arda_sim/factions.py`: `men | elves | dwarves | orcs | hobbits`.
- [x] `Faction` gains a `people: str` field (default `men`, matching the
      other string-backed enum fields like `faction_kind`), round-tripping
      through canonical JSON like the rest of the entity record.
- [x] `_FactionSeed` carries `people` and every `_ROSTER` entry sets it:
      - **men** — Gondor, Rohan, Dúnedain of the North, **Isengard**, Dale,
        Bree-land, Dunland, and all provider peoples (Haradrim, etc.)
      - **elves** — Rivendell, Lothlórien, Woodland Realm, Grey Havens
      - **dwarves** — Durin's Folk
      - **orcs** — Mordor, Dol Guldur
      - **hobbits** — The Shire
- [x] Isengard is deliberately **men** (TA 2965, pre-Uruk-hai) — keep the
      seed's comment saying so, so nobody "fixes" it to orcs later.
- [x] CONTEXT.md already defines **People** (added during the grilling
      session) — verify the implementation matches the glossary wording.
- [x] Tests: seeds carry the expected people; serialization round-trips the
      field; an unset field defaults sanely for any faction constructed
      outside the roster.

## Notes

Decided in the grilling session: this could have been a render-only
name→sprite lookup, but the user chose to make it domain-truth ("Rivendell
is an elf realm" is a fact about the world, not a style choice).
