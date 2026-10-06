// End-to-end check of the library pass (downloads page, /dl, unlock API).
//
//   node scripts/downloads_e2e.cjs <base-url> <out-dir> [--secret-file F] [--local-dir outputs/downloads]
//
// Without --secret-file it checks the locked experience only (safe on live).
// With the cookie secret of a LOCAL `wrangler pages dev` it also signs a test
// cookie to check the unlocked shelf, real downloads (bytes compared with the
// local files), byte ranges, auto-start after a redirect, and sign-out.
// Headless Brave (never Chrome/Safari); screenshots in <out-dir>.
const { chromium } = require("playwright");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

const [base, out] = process.argv.slice(2);
const opt = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };
const secretFile = opt("--secret-file");
const localDir = opt("--local-dir") || "outputs/downloads";
if (!base || !out) { console.error("usage: downloads_e2e.cjs <base> <out-dir> [--secret-file F]"); process.exit(2); }
fs.mkdirSync(out, { recursive: true });
const results = [];
const ok = (name) => { results.push({ name, ok: true }); console.log("PASS", name); };

const b64u = (b) => Buffer.from(b).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
function testCookie(secret) {
  const now = Math.floor(Date.now() / 1000);
  const body = b64u(JSON.stringify({ k: "e2e-test-key-0000", v: now, i: now }));
  const sig = b64u(crypto.createHmac("sha256", secret).update(body).digest());
  return `${body}.${sig}`;
}

(async () => {
  const browser = await chromium.launch({ executablePath: "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", headless: true });
  const errors = [];
  try {
    const host = new URL(base).hostname;
    const shot = async (page, name) => page.screenshot({ path: path.join(out, name), fullPage: false });
    const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, colorScheme: "dark", acceptDownloads: true });
    const page = await ctx.newPage();
    page.on("console", (m) => { if (m.type() === "error" && !/lemonsqueezy|lemon\.js/i.test(m.text())) errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(String(e)));

    // Locked
    await page.goto(base + "/downloads/", { waitUntil: "networkidle" });
    await page.waitForSelector('.dl-page[data-state="locked"]', { timeout: 10000 });
    ok("locked state on load");
    await shot(page, "01-locked-hero-dark.png");
    const total = await page.locator(".dl-w").count();
    assert.ok(total > 50, "shelf lists works");
    assert.match(await page.locator("[data-count]").innerText(), new RegExp(`^${total} works`));
    const buy = await page.locator("[data-buy]").getAttribute("href");
    assert.match(buy, /^https:\/\/saneapps\.lemonsqueezy\.com\/checkout\/buy\//);
    ok(`shelf lists ${total} works; buy button points at Lemon Squeezy`);
    await page.fill("#dl-q", "polycarp");
    const shown = await page.locator(".dl-w:not([hidden])").count();
    assert.ok(shown >= 1 && shown < total);
    await page.fill("#dl-q", "zzzznotawork");
    assert.equal(await page.locator(".dl-empty").isVisible(), true);
    await page.fill("#dl-q", "");
    ok(`search filters (${shown} for "polycarp", empty state shows)`);
    const hasAudio = await page.locator(".dl-w[data-audio]").count();
    await page.click('.dl-chip[data-filter="audio"]');
    assert.equal(await page.locator(".dl-w:not([hidden])").count(), hasAudio);
    await page.click('.dl-chip[data-filter=""]');
    ok(`"With audiobook" filter (${hasAudio})`);
    await page.locator("#shelf").scrollIntoViewIfNeeded();
    await shot(page, "02-locked-shelf-dark.png");
    const firstFile = page.locator(".dl-f").first();
    const want = (await firstFile.getAttribute("href")).replace(/^\/dl\//, "");
    await firstFile.click();
    await page.waitForSelector("[data-need]:not([hidden])");
    assert.equal(new URL(page.url()).pathname, "/downloads/");
    ok("locked file button shows the pass banner instead of leaving the page");
    await page.click("[data-open-key]");
    await page.fill("#dl-key", "38b1460a-5104-4067-a91d-77b872934d51");
    await page.click('[data-key-form] button[type="submit"]');
    await page.waitForFunction(() => document.querySelector("[data-key-err]").textContent.length > 0, null, { timeout: 15000 });
    await shot(page, "03-key-dialog-error-dark.png");
    assert.match(await page.locator("[data-key-err]").innerText(), /could not find|does not look|different product/i);
    await page.keyboard.press("Escape");
    ok("unknown key is refused with a plain message");

    const r = await page.goto(base + "/dl/" + want, { waitUntil: "networkidle" });
    assert.equal(new URL(page.url()).pathname, "/downloads/");
    assert.equal(new URL(page.url()).searchParams.get("need"), want);
    assert.equal(await page.locator("[data-need]").isVisible(), true);
    ok("direct /dl/ link while locked lands on /downloads/?need= with the banner");

    // Work page
    const slug = want.split("/")[1].replace(/\.[a-z0-9]+$/, "");
    await page.goto(`${base}/works/${slug}/`, { waitUntil: "networkidle" });
    assert.equal(await page.locator(".keep .keep-f").count() > 0, true);
    await page.locator(".keep").scrollIntoViewIfNeeded();
    await shot(page, "04-work-keep-block-dark.png");
    ok("work page shows Keep this book");

    // Phone + light theme, locked
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: "light", deviceScaleFactor: 2 });
    const pp = await phone.newPage();
    await pp.goto(base + "/downloads/", { waitUntil: "networkidle" });
    await pp.waitForSelector('.dl-page[data-state="locked"]');
    const overflow = await pp.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    assert.equal(overflow, 0, "no sideways scroll on phone");
    await pp.screenshot({ path: path.join(out, "05-phone-locked-light.png") });
    await pp.locator("#shelf").scrollIntoViewIfNeeded();
    await pp.screenshot({ path: path.join(out, "06-phone-shelf-light.png") });
    ok("phone layout, no horizontal overflow");
    await phone.close();

    if (secretFile) {
      const secret = fs.readFileSync(secretFile, "utf8").trim();
      await ctx.addCookies([{ name: "vpl", value: testCookie(secret), domain: host, path: "/", httpOnly: true, secure: false, sameSite: "Lax" }]);
      await page.goto(base + "/downloads/", { waitUntil: "networkidle" });
      await page.waitForSelector('.dl-page[data-state="unlocked"]', { timeout: 10000 });
      assert.match(await page.locator(".dl-hero [data-key-hint]").innerText(), /0000/);
      await shot(page, "07-unlocked-hero-dark.png");
      ok("signed cookie unlocks; key hint shows");

      const link = page.locator(".dl-f").first();
      const href = await link.getAttribute("href");
      const [dl] = await Promise.all([page.waitForEvent("download"), link.click()]);
      const saved = path.join(out, "dl-" + dl.suggestedFilename());
      await dl.saveAs(saved);
      const local = path.join(localDir, href.replace(/^\/dl\//, ""));
      assert.equal(fs.statSync(saved).size, fs.statSync(local).size);
      assert.equal(crypto.createHash("sha256").update(fs.readFileSync(saved)).digest("hex"),
        crypto.createHash("sha256").update(fs.readFileSync(local)).digest("hex"));
      assert.match(dl.suggestedFilename(), /\.(zip|epub|pdf|m4b)$/);
      ok(`download matches the local file byte for byte (${dl.suggestedFilename()})`);
      fs.unlinkSync(saved);

      const range = await page.evaluate(async (h) => {
        const r = await fetch(h, { headers: { range: "bytes=0-99" } });
        const b = await r.arrayBuffer();
        return { status: r.status, len: b.byteLength, cr: r.headers.get("content-range") };
      }, href);
      assert.equal(range.status, 206);
      assert.equal(range.len, 100);
      assert.match(range.cr, /^bytes 0-99\/\d+$/);
      ok(`byte ranges work (${range.cr})`);

      const bundle = page.locator("a.dl-b").first();
      if (await bundle.count()) {
        const bh = await bundle.getAttribute("href");
        const head = await page.evaluate(async (h) => { const r = await fetch(h, { method: "HEAD" }); return { s: r.status, n: r.headers.get("content-length"), d: r.headers.get("content-disposition") }; }, bh);
        assert.equal(head.s, 200);
        assert.equal(Number(head.n), fs.statSync(path.join(localDir, bh.replace(/^\/dl\//, ""))).size);
        assert.match(head.d, /attachment/);
        ok(`bundle served (${bh}, ${head.n} bytes)`);
      }

      const [auto] = await Promise.all([page.waitForEvent("download", { timeout: 15000 }), page.goto(`${base}/downloads/?need=${encodeURIComponent(want)}`, { waitUntil: "commit" })]);
      assert.ok(auto.suggestedFilename());
      await auto.cancel();
      ok("after unlocking, ?need= starts the wanted download");

      await page.goto(base + "/downloads/", { waitUntil: "networkidle" });
      await page.locator("#shelf").scrollIntoViewIfNeeded();
      await shot(page, "08-unlocked-shelf-dark.png");
      const light = await browser.newContext({ viewport: { width: 1360, height: 900 }, colorScheme: "light" });
      await light.addCookies([{ name: "vpl", value: testCookie(secret), domain: host, path: "/", httpOnly: true, secure: false, sameSite: "Lax" }]);
      const lp = await light.newPage();
      await lp.goto(base + "/downloads/", { waitUntil: "networkidle" });
      await lp.waitForSelector('.dl-page[data-state="unlocked"]');
      await lp.screenshot({ path: path.join(out, "09-unlocked-hero-light.png") });
      await lp.locator("#shelf").scrollIntoViewIfNeeded();
      await lp.screenshot({ path: path.join(out, "10-unlocked-shelf-light.png") });
      await light.close();

      await page.locator("[data-signout]").click();
      await page.waitForSelector('.dl-page[data-state="locked"]', { timeout: 10000 });
      const st = await page.evaluate(async () => (await fetch("/api/library/status")).json());
      assert.equal(st.unlocked, false);
      ok("sign-out locks the browser again");
    }
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
