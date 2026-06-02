---
name: autotiers-ff-knowledge
description: Structured catalogue of fantasy football heuristics with sources, confidence ratings, and implementation status in AutoTiers. Invoke when scoping a new rule, validating an existing rule in `backend/app/engine/builtin_rules.py`, or briefing a non-FF-native agent on the conventional wisdom (and its limits) for a position or strategy. Curated by the autotiers-researcher agent.
---

# AutoTiers fantasy football knowledge base

Each entry is one heuristic. Read the source links before relying on it — confidence ratings are a guide, not a substitute.

## How to use this file

- **Scoping a new rule?** Search by position or theme. Each entry's "Implementation status" line tells you whether the rule already exists.
- **Validating an existing rule?** Find the entry whose "Implementation status" points at the rule file. The "Sources" section is the audit trail.
- **Adding a new entry?** Use the template at the bottom of this file. Keep entries terse. Cite sources with author + year + URL.

## Currently shipped rules (cross-reference)

These rules exist in `backend/app/engine/builtin_rules.py`. Researcher entries should reference them by name when relevant:

- **"370 Touches"** — high-volume RB workload curse, penalizes RBs with prior-season touches above a threshold.
- **"Year After the Year After"** — post-breakout regression for receivers two seasons after a sudden leap.
- **"Bad Offense"** — penalty for skill-position players on low-projected-points teams.
- **"Follow the Money"** — uses free-agent contract size as a signal for target/touch share at the new team.

When research validates, refines, or contradicts one of these, say so in the entry's "Implementation status" line.

## Entries

<!-- Researcher: append entries here, one per heuristic, using the template below. Keep newest at the top. -->

*(No entries yet — populate via the `autotiers-researcher` agent.)*

---

## Entry template

```
### <Short heuristic name>

- **Claim (operational form):** <one sentence the mathematician could turn into a formula>
- **Position(s) / league type(s):** <where this applies — e.g. "RB, standard + half-PPR redraft">
- **Reasoning:** <one paragraph: why is this thought to be true? what's the mechanism?>
- **Sources:**
  - <Author, Year, Title — URL — credibility (high/medium/low)>
  - ...
- **Disagreements / counterevidence:** <if any source disagrees, name them and what they say>
- **Confidence:** <high | medium | low> — <one sentence on why>
- **Implementation status:** <not implemented | implemented as <file:function> | superseded by <other entry>>
- **Suggested next step:** <if not implemented and worth shipping, one sentence on what the rule would compute>
```

## Credibility rubric

- **High:** Established analyst publications with public track records (PFF, FantasyPoints, Establish The Run, RotoViz, Football Outsiders, PFR), academic sports-analytics papers.
- **Medium:** Podcasts with named analysts, well-cited Substacks/X threads from credentialed people, longform with shown reasoning.
- **Low:** Reddit consensus, unsourced rules of thumb, generic ranking sites without methodology. Useful as folk-knowledge signal, never as the only source.

A heuristic with three medium-credibility sources that converge is stronger than one high-credibility source making a contrarian claim. Surface the convergence/divergence explicitly in the entry's "Confidence" line.
