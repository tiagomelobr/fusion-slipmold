---
name: workflow-cost
description: Use BEFORE writing any Workflow script, fanning out more than two subagents, or planning an Ultracode run in this workspace. Sets the model, effort, agent type, scope, hand-off and verification rules that keep fan-outs affordable and straightforward, and overrides the bundled workflow-authoring defaults ("omit model", "token cost is not a constraint", panels, judges, adversarial verification).
---

# Workflow cost policy

In this workspace this policy overrides the bundled workflow-authoring guidance on model, effort, cost and verification, including under Ultracode. Thoroughness comes from what the work covers, not from running every stage on the top model at the top effort, and not from extra review layers.

**User preference (2026-10-06):** "For multi-agent work, let's make sure we're using the lowest agents possible for easy work, and reduce the number of testing, verification, critics, and judges - I prefer the work to be done in more a straightforward way." So:
- Use the lowest tier that can do each job: Haiku for trivial extraction or formatting, `scout` (Sonnet) for search, research and API lookups, Sonnet for mechanical edits, Opus only for geometry, Fusion scripts and design decisions.
- Prefer no workflow at all: the main session, or one or two plain subagents. A workflow is for real fan-out (many independent items), kept to about 5 agents.
- No design panels, judges, critics, adversarial voters, completeness critics or loop-until-dry rounds. The main session decides between options itself.
- No separate verification or test agents by default (section 6).

Why:
- Measured in the sibling prumofinance repository (2026-09-27, over Sep 11-27): at list prices cache reads were ~56% of cost, cache writes ~23% and output ~21%. No workflow script set a model, effort or agent type, so every agent inherited Opus at the session effort. One fleet of 41 long implementer agents was 22% of all spend (178 calls each on average, contexts up to 889k). Workflow results of 100-250k characters landed in the main context and were re-read on every later call.
- Measured here (2026-10-02, `slipcast-mold-research`, while it was still running): the script set no model or effort, so all 7 research agents ran on Opus at the session effort; they had cost ~$14 at list price, three were past 200k context and they averaged 45 calls each. They started at ~43-50k tokens each and read 45-72k-character text files whole; one agent spent ~98k characters on 32 broad Fusion API-documentation queries. For comparison, prumofinance measured first-call context at ~62k for workflow agents, ~42k for Explore and ~12k for `scout`.

## 1. Model, effort and agent type on every `agent()` call

Set them explicitly. An omitted `effort` inherits the session effort (xhigh under Ultracode), and an omitted `model` inherits Opus.

| Stage | Options |
|---|---|
| Map, search, sweep, extraction, web research, Fusion API-documentation lookups (read-only) | `{ agentType: 'scout' }`: Sonnet, medium, no CLAUDE.md, cannot edit or change the design. Use `{ agentType: 'Explore', model: 'sonnet', effort: 'medium' }` if scout is unavailable |
| Mechanical edits: moves, renames, boilerplate, doc reformatting, test scaffolding | `{ model: 'sonnet', effort: 'medium' }` (or `'high'` for tricky ones) |
| Implementation: mold-generation geometry, Fusion API scripts, parameter plumbing | `{ effort: 'high' }` (inherits Opus 5.5) |
| Trivial extraction or formatting (pull fields from a file, reformat a table) | `{ model: 'haiku' }` (no effort setting, 200K window) |
| The single reviewer, when section 6 allows one | `{ effort: 'high' }` |

No judge or synthesis agents: decisions between designs stay with the main session.

- Never use `fable` or the `best` alias for fan-out: Fable 5.1 costs 2.5x Opus 5.5 on writes and output.
- Haiku 4.5 for trivial extraction and formatting; it has no effort setting and a 200K window.
- Sonnet 5's cache reads cost the same as Opus 5.5's ($0.20/MTok). It saves ~28% on a typical workflow agent but only ~15% on a long read-heavy one, so pair it with short scopes (section 2).
- Keep options identical across siblings of one stage (model, effort, agentType, schema). Siblings share the prompt-cache prefix only when those match.
- `scout` starts without CLAUDE.md. Its prompt must carry every rule the stage needs, and it never makes a design decision. Stages that decide geometry or change the design use the default type.

## 2. Scope each agent small

- Aim for at most ~40-60 tool calls and ~150-250k context per agent. Subagents compact at the same threshold as the main session (350k here), so size the task instead of relying on compaction.
- Split long work into map or research (scout) -> implement (one coherent step per agent) -> verify, not one agent per wave.
- Tell every agent to batch independent reads and searches in one message, and to search first (`rg -n` or Grep) and then Read ranges. The ai-hook refuses whole reads of files over 40k characters.
- Research agents query Fusion API docs by exact class or member name.

## 3. Give a context pack, not a reading list

- The main session, or one scout stage, builds a pack per step: verbatim excerpts of the plan step and the relevant design rules, the Fusion document name, body/sketch/feature names and user-parameter names, `file:line` anchors taken from the current code, and the check commands. About 10k characters at most. Pass it inline or as a file path. Excerpts must be verbatim, never paraphrased.
- Never tell an agent to read CLAUDE.md (already loaded; the hook refuses it) or whole large files.

## 4. Files in, short results out

- Each agent writes bulk detail to an exact path under the session scratchpad (pass it via `args`), framed as input for the next stage, for example `${S}/research/<key>.md`, read by the synthesis or implement stage. It returns a schema result of about 2k tokens or less.
- The script returns a summary first (under ~10k characters in total), then rows and file paths, with no duplicate copies of findings.
- The main session reads the summary and greps the files for what it needs. It never prints a whole workflow result, journal or JSON file.
- Dimensions, volumes and parameter values in agent reports are leads, not facts. The main session re-queries Fusion before quoting or acting on one.

## 5. The Fusion design is one shared, live document

- Only one agent changes the design at a time. Steps that create or edit bodies, sketches, features or parameters run one after another (a `for` loop with `await`), never in `parallel` or across `pipeline` items. Read-only agents may run alongside.
- Fusion scripts print compact summaries (counts, names, key dimensions in mm, pass/fail), never object dumps or whole timelines. Screenshots only where the step needs a visual check, one view at a time.

## 6. Keep verification minimal

- Default: no separate verification, test or critic agent. The implementer runs its own checks through `ai-exec` and the pipeline's scripted checks (S6, S7-S9 checks, `readOnly` measuring scripts); the main session reads the summary and spot-checks the numbers that matter.
- At most one reviewer (`{ effort: 'high' }`), and only where a mistake could ship a mold that does not release or cast (undercuts, parting lines, wall thickness, keys and seams), or when the user asks. Never several reviewers on the same change, voting, or a review of the review.
- Treat a `null` or partial agent result (failure, turn limit) as incomplete, never as clean: log it, then re-run or report it. The same goes for a result whose fields look like placeholders. In prumofinance a Sonnet implementer whose structured output kept failing validation once returned `filesChanged: ["a"]`, `summary: "test"`.
- Reviewers check the files and the design themselves, never only from the implementer's report. Until this workspace is a git repository, list changed files by modification time (`find . -type f -newer <marker> -not -path './.local/*'`, with a marker the main session touches before the run).
- Keep schemas for Sonnet stages flat and short: few required fields and no long free-text fields that invite embedded markup.

## 7. Never

- `isolation: 'worktree'`: each worktree loses the shared prompt cache (and this workspace is not a git repository).
- Check-runner agents. The implementer runs its own checks through `node scripts/ai-exec.mjs`, and reviewers read the diff.
- A final agent message or workflow result over ~20k characters.

## 8. Size and budget

- Prefer the main session or one or two plain `Agent` calls. A workflow is for real fan-out and stays at about 5 agents; chain across turns rather than growing one.
- Honour a `+Nk` budget directive; it counts output tokens only. Guard loops with `budget.remaining()`.
- If a cap drops coverage (top-N, sampling, no retry), `log()` what was dropped.

## 9. After every run

- Check `/workflows` per-agent tokens. Flag any agent over 100 calls or 200k context, a file read whole by 3+ siblings, a result over 20k characters, and any stage without model or effort.
- For the list-price view and waste flags, run `node scripts/token-usage.mjs --since <YYYY-MM-DD>` (output under `.local/token-usage/`).
- When a waste pattern repeats, add a line to this skill.

## Template

```js
export const meta = {
  name: 'example-research-build',
  description: 'Scouts research in parallel; build steps change the live design one at a time',
  phases: [{ title: 'Research' }, { title: 'Build' }],
}
const S = args.scratch                          // session scratchpad, passed in args
const SCOUT = { agentType: 'scout' }            // Sonnet, medium, read-only, no CLAUDE.md
const BUILD = { effort: 'high' }                // inherits Opus 5.5; CLAUDE.md loaded
const RULES = 'Read-only. Never read a file over 40k characters whole: search with rg -n, then read ranges.'
// NOTES and IMPL (with files: string[], checks: string) are small flat JSON schemas defined here.

// Research fans out: read-only, files in, short results out.
const notes = await parallel(args.topics.map(t => () =>
  agent(`${RULES}\nResearch: ${t.question}\nWrite findings with sources (URL, date) to ${S}/research/${t.key}.md (read by the build stage). Return at most 10 bullets.`,
    { label: `research:${t.key}`, phase: 'Research', schema: NOTES, ...SCOUT })))
const incomplete = args.topics.filter((t, i) => !notes[i]).map(t => t.key)
if (incomplete.length) log(`incomplete research: ${incomplete.join(', ')}`)

// Build steps change the live Fusion design, so they run one at a time.
const rows = []
for (const s of args.steps) {                   // [{ key, pack }], pack = verbatim excerpts + names + anchors
  const impl = await agent(`Implement step ${s.key}. Pack:\n${s.pack}\nResearch notes: ${S}/research/\nFusion scripts print compact summaries; no screenshots unless the step needs a visual check. Run only this step's checks through node scripts/ai-exec.mjs.`,
    { label: `build:${s.key}`, phase: 'Build', schema: IMPL, ...BUILD })
  if (!impl) { log(`build ${s.key}: no result; later steps not run`); break }
  rows.push({ key: s.key, files: impl.files, checks: impl.checks })   // the main session reads these; no review agent
}
return { incomplete, rows, research: `${S}/research/` }
```
