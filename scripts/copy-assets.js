#!/usr/bin/env node
/**
 * Copies frontend dependency dist files from node_modules into static/vendor/.
 * Run after `npm install` to refresh vendored assets.
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const VENDOR = path.join(ROOT, "static", "vendor");

function cp(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
  console.log(`  ${path.relative(ROOT, src)} → ${path.relative(ROOT, dest)}`);
}

function cpDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      cpDir(srcPath, destPath);
    } else {
      cp(srcPath, destPath);
    }
  }
}

const nm = path.join(ROOT, "node_modules");

console.log("Copying Bootstrap CSS...");
cp(
  path.join(nm, "bootstrap", "dist", "css", "bootstrap.min.css"),
  path.join(VENDOR, "css", "bootstrap.min.css")
);

console.log("Copying Bootstrap JS...");
cp(
  path.join(nm, "bootstrap", "dist", "js", "bootstrap.bundle.min.js"),
  path.join(VENDOR, "js", "bootstrap.bundle.min.js")
);

console.log("Copying Bootstrap Icons...");
cp(
  path.join(nm, "bootstrap-icons", "font", "bootstrap-icons.min.css"),
  path.join(VENDOR, "css", "bootstrap-icons.min.css")
);
cpDir(
  path.join(nm, "bootstrap-icons", "font", "fonts"),
  path.join(VENDOR, "css", "fonts")
);

console.log("Copying HTMX...");
cp(
  path.join(nm, "htmx.org", "dist", "htmx.min.js"),
  path.join(VENDOR, "js", "htmx.min.js")
);

console.log("Done. Assets written to static/vendor/");
