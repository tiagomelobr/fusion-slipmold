# CLAUDE.md

This workspace builds an agent toolkit (instructions, skills, Python scripts) that turns solids designed in Fusion 360 into plaster slip-casting molds and 3D-printed casings, driven through the Autodesk Fusion MCP server. Windows 11; not a git repository yet.

## Token use

Every call re-reads the whole context from the prompt cache, so whatever enters the context is paid for again on every later call until the session ends or compacts. Keep it out, or keep it small. (Token rules adapted from the prumofinance repository.)

### Reading

- `.claude/settings.json` runs `scripts/ai-hook.mjs` before Bash, PowerShell and Read calls. The hook never approves a call, so every command still goes through the normal permission prompts. It refuses a Read without `limit` of a text file over 40,000 characters, of a saved tool output (`tool-results/`) over 10,000, and of `CLAUDE.md`, which is already in your context. Search first (`rg -n` or Grep), then Read a range with `offset` and `limit`.
- Issue independent searches and reads together in one message.

### Checks

- Run tests, lint and typecheck through the output compressor: `node scripts/ai-exec.mjs <command>` (for example `node scripts/ai-exec.mjs python -m pytest tests/test_x.py -q` or `node scripts/ai-exec.mjs ruff check --output-format concise .`). The hook refuses `pytest`, `python -m pytest`, `ruff check`, `mypy` or `pyright` without it, and names the wrapped command to run instead. Add `--raw` only when you need the full trace of a failure. Put `NAME=value` (Bash) or `$env:NAME='value';` (PowerShell) in front of `node` when a variable must reach the run.
- Run only what the change needs, once: while iterating, only the tests of the code you are changing; before a checkpoint, once for the whole batch. Do not re-run a check that already passed on the same code, and do not have a reviewer re-run the checks the implementer ran (a reviewer reads the diff). No checks for a docs-only change.

### Fusion MCP

- Fusion scripts print compact summaries: counts, names, key dimensions in mm, pass/fail. Never print object dumps, whole timelines or every face; cap loops (first N, then a count). Inspection scripts pass `readOnly: true`.
- A screenshot is an image that stays in context. Take one only when the visual answer matters (a final check, or a question for the user), not to confirm what numbers already prove (bounding box, volume, interference, minimum wall). One view at a time, not a sweep of directions.
- API documentation (`fusion_mcp_read`): query exact class or member names (`^ClassName$`, `^memberName$`) with the matching apiCategory. Broad patterns cost one research agent ~98k characters over 32 queries.
- Only one agent changes the design at a time; subagents may read it.

### Subagents and workflows

- Delegate any work a lower-tier agent can do. Send searches and sweeps expected to take more than about ten tool calls (code, web, API docs) to the read-only `scout` agent (Sonnet, no CLAUDE.md, so its prompt must carry the rules it needs) or to `Explore`. Run checks yourself through `ai-exec`: a delegated check pays a full agent startup to return a few hundred characters. Keep design decisions and design changes with the main session.
- Keep multi-agent work straightforward (user preference, 2026-10-06). Use the lowest tier that can do each job: Haiku for trivial extraction or formatting, `scout` (Sonnet) for search, research and API lookups, Sonnet for mechanical edits, Opus only for geometry, Fusion scripts and design decisions. Prefer the main session or one or two plain subagents over a workflow. No design panels, judges, critics, adversarial voters or loop-until-dry rounds, and no separate verification or test agents by default: the implementer runs its checks and the main session reads the result. Add one reviewer only where a mistake could ship a mold that does not release or cast, or when the user asks. This holds under Ultracode too.
- Load the `workflow-cost` skill before writing a Workflow script or spawning more than two subagents, and follow it even under Ultracode. It overrides the bundled workflow-authoring defaults that say to omit `model` and to ignore token cost.
- Research lands in files (the scratchpad, or `research/` when it should outlive the session) and comes back as a short summary. Never print a whole workflow result, journal or research file into the conversation; grep it.

### Context and sessions

- This workspace compacts at 350k tokens (`autoCompactWindow` in `.claude/settings.local.json`). A compaction summary must keep the Fusion document name and version, body, sketch and feature names, user-parameter names and values, the scripts run and their outcomes, which checks passed on which code, and the files changed. Never quote a dimension or parameter value from a summary: re-query the design. Use `/compact <what to keep>` at phase ends.
- One task per session: at a task boundary, or before a break of more than an hour, end with a self-contained handoff prompt (goal, files, Fusion document, done-when) and suggest `/clear` or a new session. A cold resume re-writes the whole cache. If a session stops mid-work, summarize in chat. Keep longer handoff state in `.local/handoff/<task>.md`.
- To see where tokens went: `node scripts/token-usage.mjs --since <YYYY-MM-DD>` prints list-price cost by session, agent, workflow and tool with waste flags, and writes details to `.local/token-usage/`.
