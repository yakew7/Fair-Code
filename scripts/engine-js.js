#!/usr/bin/env node
// Single entry point for running assets/profiler-engine.js from Node, used
// by tests/test_js_parity.py to check it against the Python CLI. Replaces
// the four near-identical bridge scripts this repo used to have
// (profile-js.js, compare-js.js, profile-json-js.js, profile-xlsx-js.js) -
// see #170.
//
// Usage:
//   node scripts/engine-js.js profile <dataset.csv>
//   node scripts/engine-js.js profile-json <dataset.json>
//   node scripts/engine-js.js profile-xlsx <dataset.xlsx>
//   node scripts/engine-js.js compare <a.csv> <b.csv>

const fs = require("fs");
const os = require("os");
const path = require("path");

const XLSX_CDN_URL = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js";
const NO_NETWORK_EXIT_CODE = 3;

function usageError() {
  console.error(
    "Usage:\n" +
    "  node scripts/engine-js.js profile <dataset.csv>\n" +
    "  node scripts/engine-js.js profile-json <dataset.json>\n" +
    "  node scripts/engine-js.js profile-xlsx <dataset.xlsx>\n" +
    "  node scripts/engine-js.js compare <a.csv> <b.csv>"
  );
  process.exit(1);
}

// Loads the engine and returns it. Deferred so profile-xlsx's CDN fetch
// (which needs to happen first) doesn't race with this synchronous require.
function loadEngine() {
  require(path.join(__dirname, "..", "assets", "profiler-engine.js"));
  return globalThis.FairCodeProfiler;
}

async function fetchXLSXLibrary() {
  const cachePath = path.join(os.tmpdir(), "fair-code-xlsx-0.18.5.min.js");
  if (!fs.existsSync(cachePath)) {
    let source;
    try {
      const res = await fetch(XLSX_CDN_URL);
      if (!res.ok) throw new Error("HTTP " + res.status);
      source = await res.text();
    } catch (err) {
      console.error("Could not fetch SheetJS from the CDN (" + err.message + ") - skipping.");
      process.exit(NO_NETWORK_EXIT_CODE);
    }
    fs.writeFileSync(cachePath, source);
  }
  global.XLSX = require(cachePath);
}

async function main() {
  const [command, ...args] = process.argv.slice(2);

  if (command === "profile" && args.length === 1) {
    const E = loadEngine();
    const table = E.parseCSV(fs.readFileSync(args[0], "utf8"));
    process.stdout.write(JSON.stringify(E.profile(table)));
    return;
  }

  if (command === "profile-json" && args.length === 1) {
    const E = loadEngine();
    const table = E.parseJSON(fs.readFileSync(args[0], "utf8"));
    process.stdout.write(JSON.stringify(E.profile(table)));
    return;
  }

  if (command === "profile-xlsx" && args.length === 1) {
    await fetchXLSXLibrary();
    const E = loadEngine();
    const buf = fs.readFileSync(args[0]);
    const arrayBuffer = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
    process.stdout.write(JSON.stringify(E.profile(E.parseXLSX(arrayBuffer))));
    return;
  }

  if (command === "compare" && args.length === 2) {
    const E = loadEngine();
    const [pathA, pathB] = args;
    const resultA = E.profile(E.parseCSV(fs.readFileSync(pathA, "utf8")));
    const resultB = E.profile(E.parseCSV(fs.readFileSync(pathB, "utf8")));
    const cmp = E.compare(resultA, resultB, path.basename(pathA), path.basename(pathB));
    process.stdout.write(JSON.stringify(cmp));
    return;
  }

  usageError();
}

main();
