#!/usr/bin/env node
// Runs a check command (pytest, ruff check, mypy, pyright, or a Python script) and prints a compact
// result for an agent: one summary line when tests pass, and, when long output has to be cut, every
// failure and error message with its location, every warning and the summary, with each cut marked.
// `--raw` streams the command's own output instead.
// Adapted from the prumofinance repository's scripts/ai-exec.mjs (vitest/tsc/eslint) for Python.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const rawArgs = process.argv.slice(2);
const isRaw = rawArgs.includes('--raw');
const args = rawArgs.filter(arg => arg !== '--raw');

if (args.length === 0) {
  console.error('Usage: node scripts/ai-exec.mjs [--raw] <command...>');
  process.exit(1);
}

const isWindows = process.platform === 'win32';

// Each argument is quoted for the platform shell (cmd.exe on Windows, sh elsewhere), so an
// argument such as `-k "name with spaces"` reaches the command as one argument and shell syntax
// inside an argument (& | %VAR%) stays literal.
const commandStr = args.map(quoteArg).join(' ');

// Success output longer than this, and failure output longer than FAILURE_LINES, keeps only
// failures, error messages, warnings, locations and the summary (keepImportant).
const SUCCESS_LINES = 60;
const FAILURE_LINES = 400;

// A local virtual environment (.venv) goes first on PATH, so `pytest` or `ruff` run without a
// prefix. Python writes UTF-8 to the pipe instead of the Windows code page. The rest of the
// environment passes through unchanged.
const env = { ...process.env };
const pathKey = Object.keys(env).find(k => k.toLowerCase() === 'path') || 'PATH';
const venvBin = path.resolve(process.cwd(), '.venv', isWindows ? 'Scripts' : 'bin');
if (fs.existsSync(venvBin)) env[pathKey] = `${venvBin}${path.delimiter}${env[pathKey] || ''}`;
env.PYTHONIOENCODING ??= 'utf-8';

const child = spawn(commandStr, {
  shell: true,
  stdio: ['inherit', 'pipe', 'pipe'],
  env,
});

// One buffer in arrival order, so an error printed on stderr stays beside the stdout around it.
let output = '';
child.stdout.setEncoding('utf8');
child.stderr.setEncoding('utf8');

child.stdout.on('data', chunk => {
  output += chunk;
  if (isRaw) process.stdout.write(chunk);
});

child.stderr.on('data', chunk => {
  output += chunk;
  if (isRaw) process.stderr.write(chunk);
});

child.on('error', error => {
  console.error(`ai-exec: could not start "${commandStr}": ${error.message}`);
  process.exitCode = 1;
});

child.on('close', (code, signal) => {
  // A command stopped by a signal has no exit code; it did not succeed.
  const exitCode = code ?? 1;
  process.exitCode = exitCode;
  if (isRaw) return;

  const clean = stripAnsi(output).replace(/\r\n/g, '\n').trim();

  if (exitCode === 0) {
    handleSuccess(clean, commandStr);
  } else {
    handleFailure(clean, commandStr, exitCode);
  }
  if (signal) console.error(`ai-exec: the command was stopped by ${signal}`);
});

function quoteArg(arg) {
  if (isWindows) {
    // cmd.exe expands %NAME% even between double quotes, so every % is written outside the quotes
    // as ^%. cmd.exe expands variables before it removes carets, so each name it could look up
    // ends in ^, which no variable has, and the caret then leaves a plain %.
    return arg === '' ? '""' : arg.split('%').map(quoteWindowsPiece).join('^%');
  }
  if (/^[\w@%+=:,./-]+$/.test(arg)) return arg;
  return `'${arg.replace(/'/g, `'\\''`)}'`;
}

// cmd.exe treats everything between double quotes literally (apart from %, handled above).
// Python and most Windows programs split the line by the MSVC rules, so backslashes that end up
// before a quote are doubled and an inner quote is written "", which also keeps cmd.exe's own
// quote tracking in step.
function quoteWindowsPiece(piece) {
  if (/^[\w@+=:./\\-]*$/.test(piece)) return piece;
  return `"${piece.replace(/(\\*)"/g, '$1$1""').replace(/(\\+)$/, '$1$1')}"`;
}

function stripAnsi(str) {
  // eslint-disable-next-line no-control-regex
  return str.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
}

function isTestCommand(text, command) {
  return /\b(?:pytest|py\.test)\b/i.test(command) || /^=+ test session starts =+$/m.test(text);
}

// pytest's last summary line with its counts: "==== 3 passed, 1 skipped, 2 warnings in 0.12s ====",
// "3 passed in 0.01s" under -q, "==== no tests ran in 0.01s ====".
function pytestSummary(text) {
  const matches = text.match(/^=*\s*(?:no tests ran|\d+ [a-z]+(?:, \d+ [a-z]+)*) in \d+(?:\.\d+)?s\b.*$/gm);
  if (!matches) return null;
  const line = matches[matches.length - 1].replace(/^=+\s*|\s*=+$/g, '');
  const counts = {};
  for (const [, n, label] of line.matchAll(/(\d+) (passed|failed|skipped|xfailed|xpassed|errors?|deselected|warnings?|rerun)\b/g)) {
    counts[label.replace(/s$/, '')] = Number(n);
  }
  return { line, counts };
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function handleSuccess(clean, command) {
  if (isTestCommand(clean, command)) {
    const summary = pytestSummary(clean);
    if (summary && !summary.counts.failed && !summary.counts.error) {
      const passed = summary.counts.passed ?? 0;
      if (passed === 0) {
        console.log(`⚠ No tests ran: ${summary.line}`);
        return;
      }
      const notRun = ['skipped', 'deselected', 'xfailed', 'xpassed']
        .filter(label => summary.counts[label])
        .map(label => `${summary.counts[label]} ${label}`);
      const warnings = summary.counts.warning
        ? `; ${plural(summary.counts.warning, 'warning')} (rerun with --raw to read them)`
        : '';
      console.log(`✓ All tests passed (${plural(passed, 'test')}${notRun.length ? `; ${notRun.join(', ')}` : ''}${warnings})`);
      return;
    }
  }

  printCompact(clean, SUCCESS_LINES, console.log, '✓ Command completed successfully');
}

function handleFailure(clean, command, exitCode) {
  // pytest exits 5 when it collected no tests (a wrong path, or a -k filter that matches nothing).
  if (exitCode === 5 && isTestCommand(clean, command)) {
    const summary = pytestSummary(clean);
    console.error(`⚠ No tests ran: ${summary?.line ?? 'pytest collected no tests (exit code 5)'}`);
    return;
  }
  printCompact(clean, FAILURE_LINES, console.error, '✗ Command failed without output');
}

function printCompact(text, maxLines, print, emptyMessage) {
  const lines = dropNoise(text.split('\n'));
  if (lines.length === 0) {
    print(emptyMessage);
  } else if (lines.length > maxLines) {
    print(keepImportant(lines).join('\n'));
  } else {
    print(lines.join('\n'));
  }
}

// A traceback frame inside an installed package or the standard library: `File "...", line N`
// (a plain traceback) or `path:N: in name` (pytest --tb=long).
const LIBRARY_FRAME = /site-packages[\\/]|[\\/]lib[\\/]python3[\d.]*[\\/]|[\\/]Lib[\\/](?!site-packages)|<frozen /;
const PY_FRAME = /^\s*File ".*", line \d+/;
const PYTEST_FRAME = /^\S+\.py:\d+: in \S/;

// Drops only what never helps: traceback frames inside installed packages or the standard library
// (with the source line under them), repeats of the same frame, and runs of blank lines.
function dropNoise(lines) {
  const out = [];
  let repeats = 0;
  let skipSourceLine = false;
  for (const line of lines) {
    if (skipSourceLine) {
      skipSourceLine = false;
      if (/^\s{4,}\S/.test(line) && !PY_FRAME.test(line)) continue;
    }
    const isFrame = PY_FRAME.test(line) || PYTEST_FRAME.test(line);
    if (isFrame && LIBRARY_FRAME.test(line)) {
      skipSourceLine = PY_FRAME.test(line);
      continue;
    }
    if (isFrame && line === out[out.length - 1]) {
      repeats++;
      continue;
    }
    if (repeats > 0) {
      out.push(`    ... [same frame repeated ${repeats} more ${repeats === 1 ? 'time' : 'times'}]`);
      repeats = 0;
    }
    if (line.trim() === '' && (out.length === 0 || out[out.length - 1].trim() === '')) continue;
    out.push(line);
  }
  if (repeats > 0) out.push(`    ... [same frame repeated ${repeats} more ${repeats === 1 ? 'time' : 'times'}]`);
  while (out.length > 0 && out[out.length - 1].trim() === '') out.pop();
  return out;
}

// Lines kept on their own wherever they appear: failures, errors, warnings, assertion details,
// file locations and summaries.
const IMPORTANT = [
  /\b(?:FAILED|FAIL|ERROR|XPASS)\b/,
  /\b(?:fail(?:s|ed|ure|ures)?|errors?|warn(?:ing|ings)?)\b/i,
  /\w(?:Error|Exception|Warning)\b/,
  /^E(?:\s|$)/,                     // pytest assertion and exception detail
  /^>\s/,                           // pytest: the failing source line
  /^_{3,} .+ _{3,}$/,               // pytest: one failing test's header
  /^={3,} .* ={3,}$/,               // pytest: section headers and the summary
  /^Traceback \(most recent call last\)/,
  /^During handling of the above exception|^The above exception was the direct cause/,
  /[\w@./\\-]+\.pyi?(?::\d+|", line \d+)/,
  /^\s*-->\s/,                      // ruff (full format): the location under a rule header
  /^[A-Z]{1,4}\d{2,4}\b/,           // ruff (full format): the rule header, such as "F401 [*] ..."
  /^\s*(?:help|note):/,
  /^(?:Found \d+ errors?|Success: no issues|All checks passed|\d+ errors?, \d+ warnings?)/,
];

// Source excerpts that a location line already points to: ruff's and Python 3.11+'s code frames.
const CODE_FRAME = /^\s*\d*\s*\|(?: |$)|^\s*\^[\s^~]*$|^\s*[~^]+\s*$/;
// An error message runs from its header to the next frame or section, however many lines it has
// (a multi-line message, an ExceptionGroup's members).
const ERROR_HEADER = /^(?:E\s+)?(?:[\w.]+\.)?\w*(?:Error|Exception|Warning|Exit|Interrupt|ExceptionGroup)\b:?/;
const MESSAGE_END = /^\s*File "|^Traceback|^_{3,}|^={3,}|^-{3,} |^\S+\.py:\d+:/;
const ERROR_MESSAGE_LINES = 60;

// Keeps every important line and every line of an error message, and replaces each run of other
// lines with a count. Empty spacer lines are dropped; the separators still divide the failures.
function keepImportant(lines) {
  const keep = markKept(lines);
  const out = [];
  let run = 0;
  let omitted = 0;
  lines.forEach((line, i) => {
    if (line === '') return;
    if (keep[i]) {
      if (run > 0) out.push(`  ... [${plural(run, 'line')} omitted]`);
      run = 0;
      out.push(line);
    } else if (line.trim() !== '') {
      run++;
      omitted++;
    }
  });
  if (run > 0) out.push(`  ... [${plural(run, 'line')} omitted]`);
  const header = `[ai-exec: ${plural(lines.length, 'line')} of output; ${omitted} omitted where marked ` +
    '(captured output, source excerpts, and messages past ' +
    `${ERROR_MESSAGE_LINES} lines). Rerun with --raw for all of it.]`;
  return [header, ...out];
}

function markKept(lines) {
  const keep = lines.map(line => !CODE_FRAME.test(line) && IMPORTANT.some(pattern => pattern.test(line)));
  let messageLines = 0;
  lines.forEach((line, i) => {
    if (ERROR_HEADER.test(line) && !PY_FRAME.test(line)) {
      messageLines = ERROR_MESSAGE_LINES;
    } else if (messageLines > 0) {
      if (MESSAGE_END.test(line)) {
        messageLines = 0;
      } else if (!CODE_FRAME.test(line)) {
        keep[i] = true;
        messageLines--;
      }
    }
  });
  return keep;
}
