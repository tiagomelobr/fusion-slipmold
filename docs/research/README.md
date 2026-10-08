# Research

| File | What it is |
|---|---|
| [slipcast-mold-research.md](slipcast-mold-research.md) | **Start here.** Curated brief with fact-check corrections applied |
| [design-rules.md](design-rules.md) | All 69 design rules (CER / PRN / SW), each with a default, a fact-check verdict, any corrected value, and sources |
| [fit-tolerances.md](fit-tolerances.md) | Printer fit (PRN-22): every printed clearance, the evidence for it, the nozzle and fit-offset model, plaster facts, calibration (2026-10-07) |
| [sources.md](sources.md) | Every URL cited by the research agents, grouped by domain |
| [raw/](raw/) | Unedited structured output of each research agent (JSON) and the synthesizer's drafts |

Caveats about `raw/`:

- `sweep_claude-code-asset-conventions-*.json` is **unreliable**. It mixes generic advice with conventions that don't exist in this workspace. Ignore it, and use the official Claude Code docs for skill and agent formats.
- `synth_*.md` are pre-fact-check drafts. Where they conflict with `design-rules.md` (🟡 corrected values) or the curated brief, the latter win. For example, the drafts mention a `node scripts/ai-exec.mjs` test runner, which doesn't exist here. Tests run with plain `python -m pytest`.
