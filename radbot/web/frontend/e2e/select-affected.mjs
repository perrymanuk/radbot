#!/usr/bin/env node
// Selects which Playwright spec files to run based on git diff vs BASE_REF.
// - Reads coverage-map.json to map source globs -> spec files
// - If any change matches an `alwaysRun` glob, runs the full suite
// - If --exec flag passed, spawns playwright with the resolved arg list
//   (npm runs scripts in /bin/sh so command substitution + empty arg lists are fragile)

import { execSync, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import micromatch from "micromatch";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../../..");
const map = JSON.parse(readFileSync(resolve(here, "coverage-map.json"), "utf8"));

const baseRef = process.env.BASE_REF || "origin/main";
const shouldExec = process.argv.includes("--exec");

let changed;
try {
  const out = execSync(`git diff --name-only ${baseRef}...HEAD`, {
    cwd: repoRoot,
    encoding: "utf8",
  });
  changed = out.split("\n").map((s) => s.trim()).filter(Boolean);
} catch (err) {
  process.stderr.write(`select-affected: git diff failed (${err.message}); running full suite.\n`);
  changed = null;
}

function resolveSpecs() {
  if (!changed) return { mode: "full", specs: [] };
  if (changed.length === 0) return { mode: "none", specs: [] };

  if (micromatch(changed, map.alwaysRun).length > 0) {
    return { mode: "full", specs: [] };
  }

  const affected = new Set();
  for (const [spec, patterns] of Object.entries(map.specs)) {
    if (micromatch(changed, patterns).length > 0) {
      affected.add(spec);
    }
  }
  return { mode: affected.size > 0 ? "affected" : "none", specs: [...affected] };
}

const { mode, specs } = resolveSpecs();

if (!shouldExec) {
  // Print mode + specs for human/script consumption
  if (mode === "full") {
    process.stdout.write("");
  } else {
    process.stdout.write(specs.join(" "));
  }
  process.exit(0);
}

// --exec mode: run playwright with the resolved selection
process.stderr.write(`select-affected: mode=${mode}, base=${baseRef}, specs=[${specs.join(", ")}]\n`);

if (mode === "none") {
  process.stderr.write("select-affected: no specs affected by diff; skipping run.\n");
  process.exit(0);
}

const args = ["playwright", "test", ...specs];
const result = spawnSync("npx", args, { stdio: "inherit", cwd: here.replace(/\/e2e$/, "") });
process.exit(result.status ?? 1);
