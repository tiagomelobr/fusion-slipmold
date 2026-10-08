#!/usr/bin/env node
// PreToolUse hook. Claude Code runs it before Bash, PowerShell and Read calls (.claude/settings.json).
// Adapted from the prumofinance repository's scripts/ai-hook.mjs for this Python/Fusion workspace.
//
// The hook only ever refuses. A test, lint or typecheck command (pytest, ruff check, mypy, pyright)
// that does not go through scripts/ai-exec.mjs is denied, with the wrapped command to run instead;
// every other call gets no output, which leaves it to the normal permission flow. It never returns
// "allow", so a command it misreads can at worst be refused once or run with raw output: it can
// never skip a permission prompt.
//
// A Read call without `limit` (a whole read; `offset` alone still reads to the cap) is denied when
// it would pull a large file into context for the rest of the session:
// - a text file over 40,000 bytes;
// - a persisted tool output (a path with a `tool-results` directory) over 10,000 bytes;
// - CLAUDE.md at the workspace root when the caller already has it loaded: the main thread (no
//   agent_type), or a subagent other than Explore, Plan or a custom agent whose
//   .claude/agents/<name>.md frontmatter says `omitClaudeMd: true`.
// Images, PDFs and notebooks are left alone. Any error on a Read call (a stat failure, an unreadable
// agent file, a non-string agent_type) prints nothing: it fails open.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EXEC_SCRIPT = 'scripts/ai-exec.mjs';

// A check command at a command position: the start of the call or after a separator, then any
// POSIX `NAME=value` assignments, then the runner itself (never an argument: `echo pytest` and
// `rg pytest` do not match). The runner may carry a path (.venv/Scripts/pytest) and may be started
// through `python -m`, `py -m` or `uv run`.
const POSITION = String.raw`(^|[;&|(\n]\s*)`;
const ENV = String.raw`((?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*)`;
const DIR = String.raw`(?:[^\s;&|()'"]*[\\/])?`;
const LAUNCHER = String.raw`(?:${DIR}(?:python3?|py)(?:\.exe)?\s+-m\s+|uv\s+run\s+(?:--?[\w-]+(?:=\S+)?\s+)*)?`;
const RUNNER = String.raw`${LAUNCHER}${DIR}(?:pytest|py\.test|mypy|pyright|ruff(?:\.exe)?\s+check)(?:\.exe)?(?![\w:.-])`;
const CHECK_COMMAND = new RegExp(`${POSITION}${ENV}(${RUNNER})`);

function main() {
  let data;
  try {
    data = JSON.parse(fs.readFileSync(0, 'utf-8'));
  } catch {
    return;
  }
  if (data === null || typeof data !== 'object') return;
  if (data.hook_event_name !== undefined && data.hook_event_name !== 'PreToolUse') return;
  if (data.tool_name === 'Read') {
    let reason;
    try {
      reason = readRefusal(data);
    } catch {
      reason = null;
    }
    if (reason) deny(reason);
    return;
  }
  const command = data.tool_input?.command;
  if (typeof command !== 'string') return;
  const wrapped = wrap(command, execCommand(data.cwd, command));
  if (wrapped === null) return;
  deny(
    `Run test, lint and typecheck commands through the output compressor (CLAUDE.md, "Checks"). ` +
    `Run this instead: ${wrapped}`,
  );
}

// https://code.claude.com/docs/en/hooks, "PreToolUse decision control": "deny" prevents the call
// and shows the reason to Claude, which can then make the call the reason names instead.
function deny(reason) {
  console.log(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: reason,
    },
  }));
}

const LARGE_FILE_BYTES = 40_000;
const LARGE_TOOL_RESULT_BYTES = 10_000;
const CHARS_PER_TOKEN = 3;
const MEDIA = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.svg', '.pdf', '.ipynb']);
const INSTRUCTIONS = new Set(['claude.md']);
// Built-in subagents that start without CLAUDE.md.
const WITHOUT_INSTRUCTIONS = new Set(['Explore', 'Plan']);

// The reason to refuse a Read call, or null to leave it alone. A stat or read failure throws, and
// the caller then leaves the call alone.
function readRefusal(data) {
  const input = data.tool_input;
  const filePath = input?.file_path;
  if (typeof filePath !== 'string' || filePath === '') return null;
  if (input.limit !== undefined && input.limit !== null) return null;
  const absolute = path.resolve(typeof data.cwd === 'string' ? data.cwd : REPO, filePath);
  const inRepo = repoRelative(absolute);
  const shown = inRepo ?? absolute.replace(/\\/g, '/');

  if (inRepo !== null && INSTRUCTIONS.has(inRepo.toLowerCase()) && hasInstructionsLoaded(data.agent_type)) {
    return `${shown} is already in your context: it was loaded at session start and is re-injected after ` +
      `compaction, so do not read it again. If you need to quote one section, find it with ` +
      `rg -n '<heading>' ${shown} and Read only that range with offset and limit.`;
  }

  const stat = fs.statSync(absolute);
  if (!stat.isFile()) return null;
  const size = stat.size;
  if (MEDIA.has(path.extname(absolute).toLowerCase())) return null;

  if (absolute.split(/[\\/]/).includes('tool-results')) {
    if (size <= LARGE_TOOL_RESULT_BYTES) return null;
    return `${shown} is a saved tool output of ${describeSize(size)}. Do not pull the whole saved output ` +
      `back into context: search it for what you need (rg -n '<pattern>' ${shown}, or Grep), or Read a range ` +
      `with offset and limit.`;
  }

  if (size <= LARGE_FILE_BYTES) return null;
  return `${shown} has ${describeSize(size)}; a whole read would stay in context for the rest of the ` +
    `session. Search it first (rg -n '<symbol or heading>' ${shown}, or Grep), then Read with offset and ` +
    `limit (a window of about 200-400 lines). If you truly need the whole file, read it in ranges.`;
}

function describeSize(bytes) {
  const tokens = Math.round(bytes / CHARS_PER_TOKEN / 1000) * 1000;
  return `about ${bytes.toLocaleString('en-US')} characters (~${tokens.toLocaleString('en-US')} tokens)`;
}

// The path relative to the workspace with forward slashes, or null when it is outside it.
function repoRelative(absolute) {
  const relative = path.relative(REPO, absolute);
  if (relative === '' || relative.startsWith('..') || path.isAbsolute(relative)) return null;
  return relative.replace(/\\/g, '/');
}

// Whether the caller started with CLAUDE.md in context: the main thread, or a subagent other than
// a built-in or custom agent that starts without it.
function hasInstructionsLoaded(agentType) {
  if (agentType === undefined || agentType === null || agentType === '') return true;
  if (typeof agentType !== 'string') throw new Error('agent_type is not a string');
  if (WITHOUT_INSTRUCTIONS.has(agentType)) return false;
  if (!/^[\w-]+$/.test(agentType)) return true;
  for (const dir of [path.join(REPO, '.claude', 'agents'), path.join(os.homedir(), '.claude', 'agents')]) {
    let definition;
    try {
      definition = fs.readFileSync(path.join(dir, `${agentType}.md`), 'utf-8');
    } catch (error) {
      if (error?.code === 'ENOENT') continue;
      throw error;
    }
    return !omitsInstructions(definition);
  }
  return true;
}

// `omitClaudeMd: true` in the definition's YAML frontmatter.
function omitsInstructions(definition) {
  const frontmatter = /^﻿?---\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(definition);
  return frontmatter !== null && /^omitClaudeMd:[ \t]*true[ \t]*\r?$/m.test(frontmatter[1]);
}

// The command with `exec` in front of its first check command, or null when it has none or
// already goes through ai-exec. Environment assignments stay in front, so they reach the run.
function wrap(command, exec) {
  if (command.includes('ai-exec.mjs')) return null;
  const match = CHECK_COMMAND.exec(command);
  if (!match) return null;
  const at = match.index + match[1].length + match[2].length;
  return `${command.slice(0, at)}${exec} ${command.slice(at)}`;
}

// `node scripts/ai-exec.mjs` from the workspace root; the absolute path when the call runs
// elsewhere (Claude's cwd moved, or the command changes directory itself).
function execCommand(cwd, command) {
  if ((!cwd || samePath(cwd, REPO)) && !/(^|[;&|(\n]\s*)(cd|pushd|Set-Location|sl)\s/i.test(command)) {
    return `node ${EXEC_SCRIPT}`;
  }
  const script = path.join(REPO, EXEC_SCRIPT).replace(/\\/g, '/');
  return `node ${/^[\w@+=:./-]+$/.test(script) ? script : `"${script}"`}`;
}

function samePath(a, b) {
  const normalize = p => {
    const resolved = path.resolve(p);
    return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
  };
  return normalize(a) === normalize(b);
}

main();
