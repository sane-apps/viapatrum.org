// Reuse a passed browser receipt when the site chrome is unchanged.
// A new translation does not retake screenshots. CSS, JS, or this checker's
// sibling script check_catalogue_ui.cjs still require one fresh browser run.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {artifact, REQUIRED_SHOTS, REQUIRED_CHECKS} = require("./check_catalogue_ui.cjs");

function verifyChrome(root = process.cwd(), out = path.join(root, "outputs/ui-review"), dist = path.join(root, "dist")) {
  const r = JSON.parse(fs.readFileSync(path.join(out, "browser-receipt.json"), "utf8"));
  assert.equal(r.schema, 2, "Old browser receipt schema");
  assert.equal(r.status, "passed", "Browser checks did not pass");
  assert.deepEqual([...r.completed_checks].sort(), [...REQUIRED_CHECKS].sort(), "Incomplete browser checks");
  assert.equal(r.errors.length, 0, "Browser exceptions recorded");
  assert.deepEqual([...r.screenshots.map(s => s.path)].sort(), [...REQUIRED_SHOTS].sort(), "Missing/duplicate visual states");
  const now = artifact(root, dist);
  assert.equal(r.artifact.css, now.css, "Site CSS changed; run browser checks once");
  assert.equal(r.artifact.js, now.js, "Site JS changed; run browser checks once");
  assert.equal(r.artifact.runner, now.runner, "Browser checker changed; run browser checks once");
  for (const s of r.screenshots) {
    assert.equal(s.geometry.failures.length, 0, "Layout errors: " + s.path);
  }
  return r;
}

if (require.main === module) {
  try {
    const dist = process.argv[2] || path.join(process.cwd(), "dist");
    const r = verifyChrome(process.cwd(), path.join(process.cwd(), "outputs/ui-review"), dist);
    console.log("Proven chrome, screenshots not repeated " + r.artifact.css.slice(0, 12));
  } catch (error) {
    console.error("BLOCKED: " + error.message);
    process.exitCode = 1;
  }
}

module.exports = {verifyChrome};
