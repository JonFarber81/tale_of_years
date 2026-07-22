# The Ring-hunt is unlocked by Sauron's strength, not the Ring's pull

## Context

The Nazgûl hunt was gated to *begin* only on high Ring **pull** (`HUNT_PULL_MIN`)
and to *abort* when pull fell below a scent floor (`_SCENT_MIN`). A lost or quiet
Ring emits `pull 0`, so the Nine never rode to it even at full `sauron_strength` —
the dark side could not contest a marooned Ring, one of the links that pinned every
run to the `lying_lost` terminal (see ADR-0015).

## Decision

Unlock and sustain the hunt on **`sauron_strength`** (the existing strength
threshold). **Pull is demoted from a hard gate to an urgency/priority modifier** — a
loud Ring still draws the Nine faster, but a silent one no longer stops them — and a
strength-driven hunt no longer aborts on scent-loss; its **search budget** still
bounds how long it rides before turning back.

## Consequences

- The Nine become genuine competitors in the **race for the Ring**: the Shadow can
  reach for a Ring it feels is out there even when the Ring itself has gone quiet.
- Because the Nine ride faster than free-peoples seekers, the balance between
  *lying lost* / *Sauron reclaims* / *destroyed* now rests on **geography and
  tuning** (the Ring starts far from Mordor, close to the free realms), measured
  and adjusted via the playtest harness rather than fixed here.
