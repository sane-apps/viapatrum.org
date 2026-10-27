// End-to-end check of the free downloads shelf (downloads page and /dl/).
//
//   node scripts/downloads_e2e.cjs <base-url> <out-dir>
//
// Safe on live: it reads pages and asks /dl/ for headers and the check box
// only, never a whole file. Checks the shelf lists works and its search
// works, the phone layout has no sideways scroll, HEAD /dl/<file> stays open
// (size checks), and a GET without the human-check cookie gets the Turnstile
// box (403), or the file when the check is switched off (no TURNSTILE_SECRET).
// The library pass and its unlock flow are retired (2026-10-22).
// Headless Brave (never Chrome/Safari); screenshots in <out-dir>.
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

const [base, out] = process.argv.slice(2);
if (!base || !out) { console.error("usage: downloads_e2e.cjs <base> <out-dir>"); process.exit(2); }
fs.mkdirSync(out, { recursive: true });
const results = [];
const ok = (name) => { results.push({ name, ok: true }); console.log("PASS", name); };

(async () => {
  const browser = await chromium.launch({ executablePath: "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", headless: true });
  const errors = [];
  try {
    const shot = async (page, name) => page.screenshot({ path: path.join(out, name), fullPage: false });
    const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, colorScheme: "dark" });
    const page = await ctx.newPage();
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(String(e)));

    await page.goto(base + "/downloads/", { waitUntil: "networkidle" });
    await shot(page, "01-hero-dark.png");
    const total = await page.locator(".dl-w").count();
    assert.ok(total > 50, "shelf lists works");
    assert.match(await page.locator("[data-count]").innerText(), new RegExp(`^${total} works`));
    assert.equal(await page.locator("[data-buy], .lemonsqueezy-button, [data-open-key]").count(), 0, "no checkout or key entry");
    ok(`shelf lists ${total} works, no checkout`);
    await page.fill("#dl-q", "polycarp");
    const shown = await page.locator(".dl-w:not([hidden])").count();
    assert.ok(shown >= 1 && shown < total);
    await page.fill("#dl-q", "zzzznotawork");
    assert.equal(await page.locator(".dl-empty").isVisible(), true);
    await page.fill("#dl-q", "");
    ok("shelf search filters and says when nothing matches");

    // The smallest file on the shelf, so a check-off GET costs next to nothing.
    const href = await page.locator('.dl-f[data-kind="epub"]').first().getAttribute("href");
    const probe = await page.evaluate(async (h) => {
      const head = await fetch(h, { method: "HEAD" });
      const ctl = new AbortController();
      const get = await fetch(h, { signal: ctl.signal, credentials: "omit" });
      const type = get.headers.get("content-type") || "";
      const text = type.startsWith("text/html") ? await get.text() : "";
      ctl.abort();
      return { head: head.status, len: head.headers.get("content-length"), get: get.status, box: /cf-turnstile/.test(text) };
    }, href);
    assert.equal(probe.head, 200);
    assert.ok(Number(probe.len) > 0, "HEAD names the size");
    ok(`HEAD ${href} is open (${probe.len} bytes)`);
    assert.ok((probe.get === 403 && probe.box) || probe.get === 200, `GET without the cookie: ${probe.get}`);
    ok(probe.get === 403 ? "GET without the cookie gets the Turnstile box" : "human check is off (no TURNSTILE_SECRET): the file serves");

    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: "light", deviceScaleFactor: 2 });
    const pp = await phone.newPage();
    await pp.goto(base + "/downloads/", { waitUntil: "networkidle" });
    const overflow = await pp.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    assert.equal(overflow, 0, "no sideways scroll on phone");
    await pp.screenshot({ path: path.join(out, "02-phone-light.png") });
    await pp.locator("#shelf").scrollIntoViewIfNeeded();
    await pp.screenshot({ path: path.join(out, "03-phone-shelf-light.png") });
    ok("phone layout, no horizontal overflow");
    await phone.close();

    assert.deepEqual(errors, [], "no console errors: " + errors.join(" | "));
    ok("no console errors");
  } catch (e) {
    results.push({ name: String(e && e.message || e), ok: false });
    console.error("FAIL", e);
    process.exitCode = 1;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(out, "results.json"), JSON.stringify(results, null, 1));
  }
})();
