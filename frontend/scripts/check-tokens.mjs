// F0 lint rule: platform components use design tokens only — no raw hex
// colors and no px font sizes in the new surfaces. (Legacy aurora-glass pages
// are exempt; they are being replaced screen by screen.)
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOTS = ["components", "app/dev", "app/i", "app/(org)"];
const HEX = /#[0-9a-fA-F]{3,8}\b/;
const PX_FONT = /fontSize:\s*["']?\d+px|text-\[\d+px\]/;

let failures = 0;

function walk(dir) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return;
  }
  for (const name of entries) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(tsx|ts)$/.test(name) && !name.endsWith(".test.ts")) {
      const src = readFileSync(p, "utf8");
      src.split("\n").forEach((line, i) => {
        if (HEX.test(line)) {
          console.error(`${p}:${i + 1} raw hex color: ${line.trim().slice(0, 80)}`);
          failures++;
        }
        if (PX_FONT.test(line)) {
          console.error(`${p}:${i + 1} px font size: ${line.trim().slice(0, 80)}`);
          failures++;
        }
      });
    }
  }
}

for (const root of ROOTS) walk(root);

if (failures > 0) {
  console.error(`\ntoken check FAILED: ${failures} violation(s)`);
  process.exit(1);
}
console.log("token check passed: no raw hex or px font sizes in platform surfaces");
