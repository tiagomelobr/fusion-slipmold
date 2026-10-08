#!/usr/bin/env node
// Repeatable token-usage report over this workspace's Claude Code transcripts, copied from the
// prumofinance repository's scripts/token-usage.mjs: read every *.jsonl, dedupe assistant usage
// by requestId, walk subagents/ and workflows/, cost each call at list price, and print a compact
// stdout summary. The workflow-cost skill (.claude/skills/workflow-cost) says when to run it.
//
// Usage: node scripts/token-usage.mjs [--project <dir>] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
//   [--session <id-prefix>] [--exclude <id-prefix>] [--out <dir>] [--top N]
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import url from "node:url";

// ---------- Pricing (USD per million tokens; list prices, dated 2026-09-27) ----------
// Source: https://platform.claude.com/docs/en/about-claude/pricing
// Columns: input, cache write (5-minute), cache write (1-hour), cache read, output.
// These are Anthropic's published list prices, not what a Max-plan subscription actually costs:
// Max-plan usage is weighted against an unpublished limit, not billed per token.
export const PRICING_DATE = "2026-09-27";
export const PRICING_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing";
export const PRICING = {
  "claude-opus-5-5": { in: 4, cw5: 5, cw1h: 8, read: 0.2, out: 20 },
  "claude-opus-5": { in: 5, cw5: 6.25, cw1h: 10, read: 0.5, out: 25 },
  "claude-sonnet-5": { in: 2, cw5: 2.5, cw1h: 4, read: 0.2, out: 10 },
  "claude-haiku-4-5": { in: 1, cw5: 1.25, cw1h: 2, read: 0.1, out: 5 },
  "claude-fable-5-1": { in: 10, cw5: 12.5, cw1h: 20, read: 0.25, out: 50 },
};
// Longest key first, so "claude-opus-5-5" is tried before the "claude-opus-5" prefix it extends.
const PRICING_KEYS = Object.keys(PRICING).sort((a, b) => b.length - a.length);

export function modelPricing(model) {
  if (!model) return null;
  const key = PRICING_KEYS.find(k => model.startsWith(k));
  return key ? PRICING[key] : null;
}

// A call's five token classes, already split the way the pricing table bills them.
export function tokenClasses(usage) {
  const cwTotal = usage.cache_creation_input_tokens ?? 0;
  const cw1h = usage.cache_creation?.ephemeral_1h_input_tokens ?? 0;
  return {
    input: usage.input_tokens ?? 0,
    cw5: cwTotal - cw1h,
    cw1h,
    read: usage.cache_read_input_tokens ?? 0,
    out: usage.output_tokens ?? 0,
  };
}

// Dollar cost of one API call at list price, or null when the model has no entry in PRICING.
export function callCost(usage, model) {
  const price = modelPricing(model);
  if (!price) return null;
  const c = tokenClasses(usage);
  return (
    (c.input / 1e6) * price.in +
    (c.cw5 / 1e6) * price.cw5 +
    (c.cw1h / 1e6) * price.cw1h +
    (c.read / 1e6) * price.read +
    (c.out / 1e6) * price.out
  );
}

// ---------- JSONL / transcript helpers ----------
// Paths inside this workspace are shown relative to it.
const WORKSPACE_NAME = path.basename(path.resolve(path.dirname(url.fileURLToPath(import.meta.url)), ".."));
const WORKSPACE_PREFIX = new RegExp(`^.*/${WORKSPACE_NAME.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/`, "i");

export function readJsonl(file) {
  const out = [];
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    if (!line.trim()) continue;
    try {
      out.push(JSON.parse(line));
    } catch {
      /* skip a truncated or corrupt line */
    }
  }
  return out;
}

export function textOf(content) {
  if (content == null) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map(c => (c.type === "text" ? c.text : c.type === "image" ? "[image]" : JSON.stringify(c)))
      .join("\n");
  }
  return JSON.stringify(content);
}

export function brief(name, input) {
  if (!input) return "";
  if (input.command) return String(input.command).slice(0, 160).replace(/\s+/g, " ");
  if (input.file_path) return String(input.file_path).replace(/\\/g, "/").replace(WORKSPACE_PREFIX, "");
  if (input.pattern) return `${input.pattern} ${input.path ?? ""} ${input.output_mode ?? ""}`.slice(0, 160);
  if (input.description) return String(input.description).slice(0, 160);
  if (input.url) return input.url;
  if (input.query) return String(input.query).slice(0, 160);
  if (name === "Workflow") return input.script?.match(/name:\s*'([^']+)'/)?.[1] ?? input.scriptPath ?? input.name ?? "";
  return JSON.stringify(input).slice(0, 160);
}

export function cmdCategory(cmd) {
  const c = cmd.trim();
  if (/ai-exec\.mjs/.test(c)) {
    if (/pytest/.test(c)) return "ai-exec pytest";
    if (/mypy|pyright/.test(c)) return "ai-exec typecheck";
    if (/ruff/.test(c)) return "ai-exec lint";
    return "ai-exec other";
  }
  if (/^git\s|&&\s*git\s|;\s*git\s/.test(c)) return "git";
  if (/\b(rg|grep|findstr|Select-String)\b/.test(c)) return "grep/rg";
  if (/^(cat|sed|head|tail|Get-Content|type)\b/.test(c)) return "cat/sed/head";
  if (/^node\s+-e|^node\s+--input-type|^node\s+-p/.test(c)) return "node -e";
  if (/^node\s/.test(c)) return "node script";
  if (/^(ls|find|dir|Get-ChildItem|tree)\b/.test(c)) return "ls/find";
  if (/curl|Invoke-WebRequest|wget/.test(c)) return "http";
  if (/sqlite3|better-sqlite/.test(c)) return "sqlite";
  if (/^(uv|python|py)\b/.test(c)) return "python";
  if (/^pnpm\s/.test(c)) return "pnpm other";
  if (/^npx\s/.test(c)) return "npx other";
  return "other";
}

// A gap over 60 minutes followed by a cache write over half the call's context: the cache had
// gone cold and the agent paid to rebuild it.
const COLD_GAP_MS = 60 * 60 * 1000;

// Whether a Workflow tool call's script text ever passes model/effort/agentType to an agent(...)
// call. Looks inside each balanced agent( ... ) call for the option keys, and also anywhere in the
// script body after the meta block, because scripts often spread a shared options constant
// (`const LEAN = { agentType: 'scout' }` ... `agent(p, { ...LEAN })`). A script with no agent( )
// call at all (nothing to configure) is not flagged.
const OPTION_KEY = /\b(?:model|effort|agentType)\s*:/;
export function scriptSetsAgentOptions(scriptText) {
  const text = String(scriptText ?? "");
  const calls = extractBalancedCalls(text, /\bagent\s*\(/g);
  if (calls.length === 0) return { hasAgentCalls: false, setsAny: true };
  const setsAny = calls.some(call => OPTION_KEY.test(call)) || OPTION_KEY.test(withoutMeta(text));
  return { hasAgentCalls: true, setsAny };
}

// The script without its `export const meta = { ... }` block, whose phases may name a model.
function withoutMeta(text) {
  const start = text.search(/export\s+const\s+meta\s*=\s*\{/);
  if (start < 0) return text;
  let depth = 0;
  for (let i = text.indexOf("{", start); i < text.length; i++) {
    if (text[i] === "{") depth++;
    else if (text[i] === "}" && --depth === 0) return text.slice(0, start) + text.slice(i + 1);
  }
  return text;
}

function extractBalancedCalls(text, startPattern) {
  const calls = [];
  const re = new RegExp(startPattern.source, startPattern.flags.includes("g") ? startPattern.flags : `${startPattern.flags}g`);
  let m;
  while ((m = re.exec(text))) {
    let depth = 1;
    let i = m.index + m[0].length;
    const start = i;
    while (i < text.length && depth > 0) {
      if (text[i] === "(") depth++;
      else if (text[i] === ")") depth--;
      i++;
    }
    calls.push(text.slice(start, Math.max(start, i - 1)));
    re.lastIndex = i;
  }
  return calls;
}

// ---------- Per-transcript analysis ----------
export function analyzeTranscript(file, kind) {
  const rows = readJsonl(file);
  const s = {
    file: path.basename(file),
    kind,
    title: null,
    first: null,
    last: null,
    calls: 0,
    input: 0,
    cw5: 0,
    cw1h: 0,
    read: 0,
    out: 0,
    thinking: 0,
    maxCtx: 0,
    firstCtx: null,
    cost: 0,
    unpricedTokens: 0,
    /** @type {Record<string, number>} */
    models: {},
    /** @type {Record<string, number>} */
    modelCost: {},
    compactions: [],
    /** @type {Record<string, {n: number, resultChars: number, maxResult: number}>} */
    tools: {},
    /** @type {Record<string, {n: number, chars: number}>} */
    bashCats: {},
    /** @type {Record<string, {n: number, chars: number}>} */
    reads: {},
    bigResults: [],
    hookDenials: 0,
    errors: 0,
    skillCalls: [],
    webSearches: 0,
    webFetches: 0,
    coldCacheEvents: [],
  };
  const byReq = new Map();
  const toolUses = new Map();
  let lastCallTs = null;
  for (const o of rows) {
    if (o.timestamp) {
      s.first ??= o.timestamp;
      s.last = o.timestamp;
    }
    if (o.type === "custom-title" && o.customTitle) s.title = o.customTitle;
    if (o.type === "summary" && o.summary && !s.title) s.title = o.summary;
    if (o.type === "system" && o.subtype === "compact_boundary") {
      s.compactions.push({ ts: o.timestamp, trigger: o.compactMetadata?.trigger, pre: o.compactMetadata?.preTokens, post: o.compactMetadata?.postTokens });
    }
    if (o.type === "assistant" && o.message) {
      const m = o.message;
      const key = o.requestId ?? m.id ?? o.uuid;
      if (m.usage && !byReq.has(key)) byReq.set(key, { u: m.usage, model: m.model, ts: o.timestamp });
      for (const c of Array.isArray(m.content) ? m.content : []) {
        if (c.type === "tool_use") {
          toolUses.set(c.id, { name: c.name, input: c.input, ts: o.timestamp });
          s.tools[c.name] ??= { n: 0, resultChars: 0, maxResult: 0 };
          s.tools[c.name].n++;
          if (c.name === "Skill") s.skillCalls.push(c.input?.skill);
        }
      }
    }
    if (o.type === "user" && o.message && Array.isArray(o.message.content)) {
      for (const c of o.message.content) {
        if (c.type !== "tool_result") continue;
        const tu = toolUses.get(c.tool_use_id);
        const name = tu?.name ?? "unknown";
        const t = textOf(c.content);
        const len = t.length;
        if (c.is_error) s.errors++;
        if (/through the output compressor/.test(t)) s.hookDenials++;
        s.tools[name] ??= { n: 0, resultChars: 0, maxResult: 0 };
        s.tools[name].resultChars += len;
        s.tools[name].maxResult = Math.max(s.tools[name].maxResult, len);
        const b = brief(name, tu?.input);
        s.bigResults.push({ name, chars: len, brief: b, ts: o.timestamp });
        if (name === "Bash" || name === "PowerShell") {
          const cat = cmdCategory(String(tu?.input?.command ?? ""));
          s.bashCats[cat] ??= { n: 0, chars: 0 };
          s.bashCats[cat].n++;
          s.bashCats[cat].chars += len;
        }
        if (name === "Read") {
          const f = b;
          s.reads[f] ??= { n: 0, chars: 0 };
          s.reads[f].n++;
          s.reads[f].chars += len;
        }
        if (name === "WebSearch") s.webSearches++;
        if (name === "WebFetch") s.webFetches++;
      }
    }
  }
  for (const [, { u, model, ts }] of byReq) {
    s.calls++;
    s.models[model] = (s.models[model] ?? 0) + 1;
    const cls = tokenClasses(u);
    s.input += cls.input;
    s.cw5 += cls.cw5;
    s.cw1h += cls.cw1h;
    s.read += cls.read;
    s.out += cls.out;
    s.thinking += u.output_tokens_details?.thinking_tokens ?? 0;
    const ctx = cls.input + cls.cw5 + cls.cw1h + cls.read;
    s.maxCtx = Math.max(s.maxCtx, ctx);
    if (s.firstCtx === null) s.firstCtx = ctx;
    const cost = callCost(u, model);
    if (cost === null) {
      s.unpricedTokens += cls.input + cls.cw5 + cls.cw1h + cls.read + cls.out;
    } else {
      s.cost += cost;
      s.modelCost[model] = (s.modelCost[model] ?? 0) + cost;
    }
    const cwTotal = cls.cw5 + cls.cw1h;
    if (ts && lastCallTs) {
      const gapMs = new Date(ts).getTime() - new Date(lastCallTs).getTime();
      if (gapMs > COLD_GAP_MS && ctx > 0 && cwTotal > 0.5 * ctx) {
        s.coldCacheEvents.push({ ts, gapMin: Math.round(gapMs / 60000), cwTotal, ctx });
      }
    }
    if (ts) lastCallTs = ts;
  }
  s.bigResults.sort((a, b) => b.chars - a.chars);
  s.bigResults = s.bigResults.slice(0, 25);
  return s;
}

// ---------- Walking a project directory ----------
export function defaultProjectDir() {
  const cwd = process.cwd().replace(/[:\\/]/g, "-");
  return path.join(os.homedir(), ".claude", "projects", cwd);
}

export function defaultOutDir() {
  return path.join(process.cwd(), ".local", "token-usage");
}

function inRange(iso, since, until) {
  if (!iso) return true;
  const day = iso.slice(0, 10);
  if (since && day < since) return false;
  if (until && day > until) return false;
  return true;
}

export function collectProject(projectDir, opts = {}) {
  const sessions = [];
  const agents = [];
  const workflows = [];
  const entries = fs.existsSync(projectDir) ? fs.readdirSync(projectDir) : [];
  for (const f of entries) {
    if (!f.endsWith(".jsonl")) continue;
    const id = f.replace(/\.jsonl$/, "");
    if (opts.session && !id.startsWith(opts.session)) continue;
    if (opts.exclude && id.startsWith(opts.exclude)) continue;
    const s = analyzeTranscript(path.join(projectDir, f), "main");
    if (!inRange(s.first, opts.since, opts.until)) continue;
    s.id = id;
    const dir = path.join(projectDir, id);
    s.subagents = { n: 0, cost: 0, read: 0, out: 0, cw: 0 };
    s.workflows = [];
    if (fs.existsSync(path.join(dir, "subagents"))) {
      const walk = (d, wf) => {
        for (const e of fs.readdirSync(d, { withFileTypes: true })) {
          const p = path.join(d, e.name);
          if (e.isDirectory()) {
            walk(p, e.name.startsWith("wf_") ? e.name : wf);
          } else if (e.name.endsWith(".jsonl")) {
            const a = analyzeTranscript(p, "agent");
            a.session = id;
            a.workflow = wf ?? null;
            const metaPath = p.replace(/\.jsonl$/, ".meta.json");
            if (fs.existsSync(metaPath)) {
              try {
                a.meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
              } catch {
                /* meta is best-effort */
              }
            }
            agents.push(a);
            s.subagents.n++;
            s.subagents.cost += a.cost;
            s.subagents.read += a.read;
            s.subagents.out += a.out;
            s.subagents.cw += a.cw5 + a.cw1h;
          }
        }
      };
      walk(path.join(dir, "subagents"), null);
    }
    if (fs.existsSync(path.join(dir, "workflows"))) {
      for (const wf of fs.readdirSync(path.join(dir, "workflows"))) {
        if (!wf.endsWith(".json")) continue;
        try {
          const w = JSON.parse(fs.readFileSync(path.join(dir, "workflows", wf), "utf8"));
          const optionCoverage = scriptSetsAgentOptions(w.script);
          const entry = {
            session: id,
            runId: w.runId,
            name: w.workflowName,
            agentCount: w.agentCount,
            totalTokens: w.totalTokens,
            totalToolCalls: w.totalToolCalls,
            durationMin: Math.round((w.durationMs ?? 0) / 60000),
            resultChars: JSON.stringify(w.result ?? "").length,
            scriptSetsNoAgentOptions: optionCoverage.hasAgentCalls && !optionCoverage.setsAny,
            // Filled from the agent transcripts once every session has been walked.
            agentsFound: 0,
            cost: 0,
            avgFirstCtx: 0,
            avgCalls: 0,
            avgMaxCtx: 0,
            /** @type {string[]} */
            sharedReadFiles: [],
            /** @type {string[]} */
            wasteFlags: [],
          };
          workflows.push(entry);
          s.workflows.push(entry.runId);
        } catch {
          /* a malformed workflow record is skipped, not fatal */
        }
      }
    }
    // A workflow that was stopped, or is still running, has agent transcripts but no run record.
    // Its script is saved as workflows/scripts/<name>-<runId>.js.
    const unrecorded = new Set(agents.filter(a => a.session === id && a.workflow && !s.workflows.includes(a.workflow)).map(a => a.workflow));
    for (const runId of unrecorded) {
      const scriptsDir = path.join(dir, "workflows", "scripts");
      const scriptFile = fs.existsSync(scriptsDir) ? fs.readdirSync(scriptsDir).find(f => f.endsWith(`-${runId}.js`)) : undefined;
      const script = scriptFile ? fs.readFileSync(path.join(scriptsDir, scriptFile), "utf8") : "";
      const optionCoverage = scriptSetsAgentOptions(script);
      workflows.push({
        session: id,
        runId,
        name: `${scriptFile ? scriptFile.slice(0, -`-${runId}.js`.length) : runId} (no run record)`,
        agentCount: null,
        totalTokens: null,
        totalToolCalls: null,
        durationMin: null,
        resultChars: 0,
        scriptSetsNoAgentOptions: optionCoverage.hasAgentCalls && !optionCoverage.setsAny,
        agentsFound: 0,
        cost: 0,
        avgFirstCtx: 0,
        avgCalls: 0,
        avgMaxCtx: 0,
        sharedReadFiles: [],
        wasteFlags: [],
      });
      s.workflows.push(runId);
    }
    sessions.push(s);
  }
  for (const w of workflows) {
    const as = agents.filter(a => a.workflow === w.runId);
    w.agentsFound = as.length;
    w.cost = as.reduce((x, a) => x + a.cost, 0);
    w.avgFirstCtx = as.length ? Math.round(as.reduce((x, a) => x + (a.firstCtx ?? 0), 0) / as.length) : 0;
    w.avgCalls = as.length ? Math.round(as.reduce((x, a) => x + a.calls, 0) / as.length) : 0;
    w.avgMaxCtx = as.length ? Math.round(as.reduce((x, a) => x + a.maxCtx, 0) / as.length) : 0;
    const readers = {};
    for (const a of as) for (const f of Object.keys(a.reads)) readers[f] = (readers[f] ?? 0) + 1;
    w.sharedReadFiles = Object.entries(readers).filter(([, n]) => n >= 3).map(([f]) => f);
    w.wasteFlags = workflowWasteFlags(w, as);
  }
  return { sessions, agents, workflows };
}

function workflowWasteFlags(w, agentTranscripts) {
  const flags = [];
  const over100Calls = agentTranscripts.filter(a => a.calls > 100).length;
  if (over100Calls) flags.push(`${over100Calls} agent(s) over 100 calls`);
  const over200kCtx = agentTranscripts.filter(a => a.maxCtx > 200_000).length;
  if (over200kCtx) flags.push(`${over200kCtx} agent(s) over 200k context`);
  if (w.sharedReadFiles.length) flags.push(`${w.sharedReadFiles.length} file(s) read whole by 3+ sibling agents`);
  if (w.resultChars > 20_000) flags.push(`result ${w.resultChars} chars returned to main`);
  if (w.scriptSetsNoAgentOptions) flags.push("script sets no model/effort/agentType on any agent() call");
  return flags;
}

// ---------- Rendering ----------
const k = n => (n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(Math.round(n)));
const money = n => `$${n.toFixed(2)}`;

export function renderSummary({ sessions, agents, workflows }, opts = {}) {
  const top = opts.top ?? 15;
  const allCalls = [...sessions, ...agents];
  let md = "# Token usage report\n\n";
  md += `List-price equivalent (source: ${PRICING_SOURCE}, dated ${PRICING_DATE}). ` +
    "A Max-plan subscription is not billed per token; its usage limit weighting is unpublished, so this is a cost proxy, not a bill.\n\n";
  md += `Main sessions: ${sessions.length}; subagent transcripts: ${agents.length}; workflows: ${workflows.length}.\n\n`;

  // Totals and cost by token class and by model.
  const sum = key => allCalls.reduce((a, s) => a + s[key], 0);
  const totalCost = allCalls.reduce((a, s) => a + s.cost, 0);
  const unpricedTokens = allCalls.reduce((a, s) => a + s.unpricedTokens, 0);
  md += "## Totals\n\n| class | tokens |\n|---|---|\n";
  md += `| input | ${k(sum("input"))} |\n| cache write 5m | ${k(sum("cw5"))} |\n| cache write 1h | ${k(sum("cw1h"))} |\n| cache read | ${k(sum("read"))} |\n| output | ${k(sum("out"))} |\n`;
  md += `\nTotal list-price cost: **${money(totalCost)}**` + (unpricedTokens ? ` (plus ${k(unpricedTokens)} unpriced tokens on unlisted models)` : "") + ".\n\n";

  const modelCost = {};
  const modelTokens = {};
  for (const s of allCalls) {
    for (const [m, c] of Object.entries(s.modelCost)) modelCost[m] = (modelCost[m] ?? 0) + c;
    for (const [m, n] of Object.entries(s.models)) modelTokens[m] = (modelTokens[m] ?? 0) + n;
  }
  md += "## Cost by model\n\n| model | calls | cost | priced |\n|---|---|---|---|\n";
  for (const [m, n] of Object.entries(modelTokens).sort((a, b) => (modelCost[b[0]] ?? 0) - (modelCost[a[0]] ?? 0))) {
    const priced = modelPricing(m) !== null;
    md += `| ${m} | ${n} | ${priced ? money(modelCost[m] ?? 0) : "-"} | ${priced ? "yes" : "no (unlisted)"} |\n`;
  }

  // Main vs subagents vs workflow agents.
  const workflowAgents = agents.filter(a => a.workflow);
  const plainAgents = agents.filter(a => !a.workflow);
  const costOf = list => list.reduce((a, s) => a + s.cost, 0);
  md += "\n## Main vs subagents vs workflow agents\n\n| group | transcripts | calls | cost |\n|---|---|---|---|\n";
  md += `| main | ${sessions.length} | ${sum2(sessions, "calls")} | ${money(costOf(sessions))} |\n`;
  md += `| subagents (non-workflow) | ${plainAgents.length} | ${sum2(plainAgents, "calls")} | ${money(costOf(plainAgents))} |\n`;
  md += `| workflow agents | ${workflowAgents.length} | ${sum2(workflowAgents, "calls")} | ${money(costOf(workflowAgents))} |\n`;

  // Top sessions by cost.
  md += `\n## Top sessions by cost (top ${top})\n\n| id | title | date | calls | maxCtx | meanCtx | cost | subagent cost | compactions (preTokens) |\n|---|---|---|---|---|---|---|---|---|\n`;
  for (const s of [...sessions].sort((a, b) => b.cost + b.subagents.cost - (a.cost + a.subagents.cost)).slice(0, top)) {
    const meanCtx = s.calls ? Math.round((s.maxCtx + (s.firstCtx ?? 0)) / 2) : 0;
    md += `| ${s.id.slice(0, 8)} | ${(s.title ?? "").slice(0, 40)} | ${(s.first ?? "").slice(0, 10)} | ${s.calls} | ${k(s.maxCtx)} | ${k(meanCtx)} | ${money(s.cost)} | ${money(s.subagents.cost)} | ${s.compactions.map(c => `${c.trigger}:${k(c.pre ?? 0)}`).join(", ")} |\n`;
  }

  // Workflows.
  md += "\n## Workflows\n\n| session | name | agents | cost | avg first ctx | avg calls/agent | avg max ctx | result chars | waste flags |\n|---|---|---|---|---|---|---|---|---|\n";
  for (const w of [...workflows].sort((a, b) => b.cost - a.cost)) {
    md += `| ${w.session.slice(0, 8)} | ${w.name} | ${w.agentCount ?? w.agentsFound} | ${money(w.cost)} | ${k(w.avgFirstCtx)} | ${w.avgCalls} | ${k(w.avgMaxCtx)} | ${k(w.resultChars)} | ${w.wasteFlags.join("; ") || "-"} |\n`;
  }

  // First-call context by agent type.
  const byType = {};
  for (const a of agents) {
    const t = a.meta?.agentType ?? "unknown";
    byType[t] ??= { n: 0, first: 0 };
    byType[t].n++;
    byType[t].first += a.firstCtx ?? 0;
  }
  md += "\n## First-call context by agent type\n\n| agentType | n | avg first ctx |\n|---|---|---|\n";
  for (const [t, v] of Object.entries(byType).sort((a, b) => b[1].n - a[1].n)) md += `| ${t} | ${v.n} | ${k(v.first / v.n)} |\n`;

  // Tool results by tool.
  const toolTot = {};
  for (const s of allCalls) for (const [t, v] of Object.entries(s.tools)) { toolTot[t] ??= { n: 0, resultChars: 0 }; toolTot[t].n += v.n; toolTot[t].resultChars += v.resultChars; }
  md += "\n## Tool results by tool\n\n| tool | calls | result chars |\n|---|---|---|\n";
  for (const [t, v] of Object.entries(toolTot).sort((a, b) => b[1].resultChars - a[1].resultChars).slice(0, 20)) md += `| ${t} | ${v.n} | ${k(v.resultChars)} |\n`;

  // Shell command categories.
  const bashTot = {};
  for (const s of allCalls) for (const [t, v] of Object.entries(s.bashCats)) { bashTot[t] ??= { n: 0, chars: 0 }; bashTot[t].n += v.n; bashTot[t].chars += v.chars; }
  md += "\n## Shell command categories\n\n| category | calls | result chars |\n|---|---|---|\n";
  for (const [t, v] of Object.entries(bashTot).sort((a, b) => b[1].chars - a[1].chars)) md += `| ${t} | ${v.n} | ${k(v.chars)} |\n`;

  // Largest tool results.
  const big = allCalls.flatMap(s => s.bigResults.map(b => ({ ...b, where: s.kind === "main" ? s.id?.slice(0, 8) : `${s.session?.slice(0, 8)}/${s.meta?.description ?? s.file}` })));
  big.sort((a, b) => b.chars - a.chars);
  md += "\n## 15 largest tool results\n\n| where | tool | chars | input |\n|---|---|---|---|\n";
  for (const b of big.slice(0, 15)) md += `| ${b.where} | ${b.name} | ${k(b.chars)} | ${String(b.brief).replace(/\|/g, "\\|").slice(0, 100)} |\n`;

  // Files read 4+ times in one transcript.
  const rep = [];
  for (const s of allCalls) for (const [f, v] of Object.entries(s.reads)) if (v.n >= 4) rep.push({ where: s.kind === "main" ? s.id.slice(0, 8) : `${s.session.slice(0, 8)}/${s.meta?.description ?? ""}`, f, ...v });
  rep.sort((a, b) => b.chars - a.chars);
  md += "\n## Files read 4+ times in one transcript (top 15)\n\n| where | file | reads | chars |\n|---|---|---|---|\n";
  for (const r of rep.slice(0, 15)) md += `| ${r.where} | ${r.f} | ${r.n} | ${k(r.chars)} |\n`;

  // Cold cache rewrites.
  const cold = allCalls.flatMap(s => s.coldCacheEvents.map(e => ({ ...e, where: s.kind === "main" ? s.id?.slice(0, 8) : `${s.session?.slice(0, 8)}/${s.meta?.description ?? ""}` })));
  md += `\n## Cold cache rewrites (gap over 60min, cache write over half context): ${cold.length}\n\n`;
  if (cold.length) {
    md += "| where | gap (min) | cache write | context |\n|---|---|---|---|\n";
    for (const e of cold.slice(0, top)) md += `| ${e.where} | ${e.gapMin} | ${k(e.cwTotal)} | ${k(e.ctx)} |\n`;
  }

  return md;
}

function sum2(list, key) {
  return list.reduce((a, s) => a + s[key], 0);
}

// ---------- CLI ----------
function parseArgs(argv) {
  const opts = { top: 15 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--project") opts.project = argv[++i];
    else if (a === "--since") opts.since = argv[++i];
    else if (a === "--until") opts.until = argv[++i];
    else if (a === "--session") opts.session = argv[++i];
    else if (a === "--exclude") opts.exclude = argv[++i];
    else if (a === "--out") opts.out = argv[++i];
    else if (a === "--top") opts.top = Number(argv[++i]);
  }
  return opts;
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const projectDir = opts.project ?? defaultProjectDir();
  const outDir = opts.out ?? defaultOutDir();
  if (!fs.existsSync(projectDir)) {
    console.error(`token-usage: no project directory at ${projectDir}`);
    process.exitCode = 1;
    return;
  }
  const data = collectProject(projectDir, opts);
  const md = renderSummary(data, opts);
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "sessions.json"), JSON.stringify(data.sessions, null, 1));
  fs.writeFileSync(path.join(outDir, "agents.json"), JSON.stringify(data.agents, null, 1));
  fs.writeFileSync(path.join(outDir, "workflows.json"), JSON.stringify(data.workflows, null, 1));
  fs.writeFileSync(path.join(outDir, "summary.md"), md);

  const lines = md.split("\n");
  const compact = lines.length > 120 ? [...lines.slice(0, 120), `... [${lines.length - 120} more lines in ${path.join(outDir, "summary.md")}]`] : lines;
  console.log(compact.join("\n"));
}

const isMain = (() => {
  try {
    return import.meta.url === url.pathToFileURL(process.argv[1]).href;
  } catch {
    return false;
  }
})();
if (isMain) main();
