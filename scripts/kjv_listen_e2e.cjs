// Browser check of the Listen bar on a Scripture chapter (KJV read aloud).
//
//   node scripts/kjv_listen_e2e.cjs <dist-dir> <fixture-dir> <shots-dir>
//
// <dist-dir>: a build made with KJV_AUDIO_DIR set (John 1 must have a bar).
// <fixture-dir>: holds JHN/1.mp3, served in place of the R2 file (with byte
// ranges, as R2 does). The mp3 and any timing files there are test fixtures
// and never ship.
// Plays John 1 in headless Brave and checks: nothing loads before Listen; from
// another version Listen switches the text to the KJV; the lit word moves with
// the audio; Space and Enter on the button play and pause, with a visible focus
// ring; the seek bar takes keys; picking another version pauses and drops the
// light; no sideways scroll at 390 px. Screenshots: desktop and 390 px, light and dark.
const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const net = require("node:net");
const assert = require("node:assert/strict");

const [dist, fixtures, shots] = process.argv.slice(2);
if (!dist || !fixtures || !shots) {
  console.error("usage: kjv_listen_e2e.cjs <dist-dir> <fixture-dir> <shots-dir>");
  process.exit(2);
}
const MP3 = path.join(fixtures, "JHN", "1.mp3");
if (!fs.existsSync(MP3)) { console.error(`missing fixture ${MP3}`); process.exit(2); }
fs.mkdirSync(shots, { recursive: true });
const BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser";
const PAGE = "/scripture/john/1/";
const results = [];
const ok = (name) => { results.push(name); console.log("PASS", name); };

const freePort = () => new Promise((resolve) => {
  const s = net.createServer();
  s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => resolve(p)); });
});
const waitFor = async (fn, ms, what) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timed out: ${what}`);
    await new Promise((r) => setTimeout(r, 100));
  }
};

// The R2 mp3, served from the fixture with byte ranges.
const mp3 = fs.readFileSync(MP3);
async function serveMp3(route) {
  const range = route.request().headers()["range"];
  const head = { "Content-Type": "audio/mpeg", "Accept-Ranges": "bytes", "Access-Control-Allow-Origin": "*" };
  const m = range && /bytes=(\d*)-(\d*)/.exec(range);
  if (!m) return route.fulfill({ status: 200, headers: { ...head, "Content-Length": String(mp3.length) }, body: mp3 });
  const start = m[1] ? Number(m[1]) : Math.max(0, mp3.length - Number(m[2]));
  const end = m[1] && m[2] ? Math.min(Number(m[2]), mp3.length - 1) : mp3.length - 1;
  return route.fulfill({
    status: 206,
    headers: { ...head, "Content-Range": `bytes ${start}-${end}/${mp3.length}`, "Content-Length": String(end - start + 1) },
    body: mp3.subarray(start, end + 1),
  });
}

(async () => {
  const port = await freePort();
  const server = spawn("python3", [path.join(__dirname, "serve_dist.py"), String(port), dist], { stdio: "ignore" });
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch({ executablePath: BRAVE, headless: true, args: ["--autoplay-policy=no-user-gesture-required"] });
  const errors = [];
  try {
    await waitFor(async () => { try { return (await fetch(base + PAGE)).ok; } catch { return false; } }, 10000, "server");
    const open = async (opts) => {
      const ctx = await browser.newContext(opts);
      const audioHits = [];
      await ctx.route(/^https:\/\/audio\.viapatrum\.org\/kjv\/JHN\/1\.[0-9a-f]{10}\.mp3/, (route) => { audioHits.push(route.request().url()); return serveMp3(route); });
      // Licensed versions are never fetched in this test: any YouVersion or bolls.life call fails.
      await ctx.route(/api\.youversion\.com|bolls\.life/, (route) => route.abort());
      const page = await ctx.newPage();
      // Failed loads are named by URL below, so the console's bare "Failed to load resource" is skipped.
      page.on("console", (m) => { if (m.type() === "error" && !/youversion|bolls|ERR_FAILED|Failed to load resource/.test(m.text())) errors.push(m.text()); });
      page.on("response", (r) => { if (r.status() >= 400 && r.url().startsWith(base)) errors.push(`${r.status()} ${r.url().slice(base.length)}`); });
      page.on("pageerror", (e) => errors.push(String(e)));
      await page.goto(base + PAGE, { waitUntil: "networkidle" });
      return { ctx, page, audioHits };
    };
    const state = (page) => page.evaluate(() => {
      const bx = document.querySelector("[data-bx]");
      const on = document.querySelector(".bx-text .lw-on");
      return {
        tr: bx.dataset.tr,
        kjvPressed: document.querySelector('button[data-tr="kjv"]').getAttribute("aria-pressed"),
        btn: document.querySelector(".bx-listen-play").textContent.trim(),
        time: document.querySelector(".bx-listen .rdl-time").textContent,
        note: (document.querySelector(".bx-listen-note") || {}).textContent || "",
        lit: on ? on.textContent : null,
        litVerse: on ? on.closest(".v").dataset.v : null,
        litIndex: on ? [...on.closest(".vt").querySelectorAll(".lw")].indexOf(on) : -1,
        words: document.querySelectorAll(".bx-text .lw").length,
        v1: document.querySelector('.v[data-v="1"] .vt').textContent,
      };
    });
    const kjv = JSON.parse(fs.readFileSync(path.join(dist, "data/bible/kjv/john/1.json"), "utf8"));
    const kjvText = Object.fromEntries(kjv.map(([v, t]) => [String(v), t]));

    // ---- Desktop, light ----
    let { ctx, page, audioHits } = await open({ viewport: { width: 1360, height: 900 }, colorScheme: "light" });
    const bar = page.locator(".bx-listen");
    assert.equal(await bar.count(), 1, "one Listen bar");
    assert.match(await page.locator(".bx-listen .rdl-time").innerText(), /^0:00 \/ 6:4\d$/);
    assert.match(await page.locator(".bx-listen-credit").innerText(), /King James Version read aloud, from Larry Sanger.s Deep Dive Bible \(public domain\)/);
    assert.equal(audioHits.length, 0, "no audio fetched before Listen");
    ok("bar shows 0:00 / 6:4x, credits Larry Sanger's Deep Dive Bible, loads nothing at rest");

    // Start on another version (NET, hosted here), then Listen from the keyboard.
    await page.click('button[data-tr="net"]');
    await waitFor(() => page.evaluate(() => document.querySelector("[data-bx]").dataset.tr === "net"), 5000, "NET shown");
    assert.notEqual((await state(page)).v1, kjvText["1"], "NET text differs from the KJV");
    await page.locator('button[data-tr="net"]').focus();
    let tabs = 0;
    while (!(await page.evaluate(() => document.activeElement && document.activeElement.classList.contains("bx-listen-play")))) {
      await page.keyboard.press("Tab");
      if (++tabs > 80) throw new Error("Listen button not reachable by Tab");
    }
    const ring = await page.evaluate(() => {
      const b = document.activeElement;
      const cs = getComputedStyle(b);
      return { fv: b.matches(":focus-visible"), style: cs.outlineStyle, width: parseFloat(cs.outlineWidth) };
    });
    assert.ok(ring.fv && ring.style !== "none" && ring.width >= 2, `focus ring on Listen: ${JSON.stringify(ring)}`);
    ok(`Listen reached by Tab (${tabs} presses) with a visible focus ring`);
    await page.keyboard.press("Space");
    await waitFor(async () => (await state(page)).lit, 15000, "a lit word");
    let s = await state(page);
    assert.equal(s.tr, "kjv");
    assert.equal(s.kjvPressed, "true");
    assert.equal(s.v1, kjvText["1"], "verse 1 shows the KJV");
    assert.match(s.note, /Switched to the King James Version/);
    assert.match(s.btn, /Pause/);
    assert.ok(audioHits.length > 0, "audio came from the R2 URL (fixture)");
    ok(`Space on Listen switched NET to the KJV and played; lit "${s.lit}" in verse ${s.litVerse}`);

    // The light moves with the audio and only ever sits on KJV words.
    const first = s;
    await page.waitForTimeout(2500);
    s = await state(page);
    assert.ok(s.lit && (s.litVerse !== first.litVerse || s.litIndex > first.litIndex), `light moved: ${JSON.stringify([first.litVerse, first.litIndex, s.litVerse, s.litIndex])}`);
    assert.equal(s.words, kjv.reduce((n, [, t]) => n + t.split(/\s+/).filter(Boolean).length, 0), "every KJV word wrapped");
    const allKjv = await page.evaluate(() => [...document.querySelectorAll(".bx-text .v")].map((v) => [v.dataset.v, v.querySelector(".vt").textContent]));
    assert.ok(allKjv.every(([v, t]) => t === kjvText[v]), "every verse on the page is the KJV text");
    ok(`light moved from "${first.lit}" (v${first.litVerse}#${first.litIndex}) to "${s.lit}" (v${s.litVerse}#${s.litIndex})`);
    await page.screenshot({ path: path.join(shots, "desktop-light-playing.png") });

    // Enter pauses; time holds.
    await page.locator(".bx-listen-play").focus();
    await page.keyboard.press("Enter");
    await waitFor(async () => /Listen/.test((await state(page)).btn), 3000, "paused");
    const held = (await state(page)).time;
    await page.waitForTimeout(1200);
    assert.equal((await state(page)).time, held, "time holds while paused");
    ok(`Enter paused at ${held}`);

    // Seek bar from the keyboard.
    await page.locator(".bx-listen .rdl-bar").focus();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    const after = (await state(page)).time;
    assert.notEqual(after, held, "arrows move the time");
    await page.keyboard.press("Home");
    assert.match((await state(page)).time, /^0:00 \//);
    ok(`seek bar: arrows moved ${held} -> ${after}, Home went to 0:00`);

    // Speed.
    await page.click(".bx-listen-rate");
    assert.equal((await page.locator(".bx-listen-rate").innerText()).trim(), "1.25×");
    ok("speed button steps 1× -> 1.25×");

    // Another version while playing: the reading pauses and the light goes.
    await page.locator(".bx-listen-play").click();
    await waitFor(async () => /Pause/.test((await state(page)).btn), 5000, "playing again");
    await page.click('button[data-tr="web"]');
    await waitFor(async () => { const x = await state(page); return x.tr === "web" && /Listen/.test(x.btn); }, 5000, "paused on WEB");
    s = await state(page);
    assert.equal(s.words, 0, "no word spans left on another version");
    assert.equal(s.lit, null);
    assert.equal(await page.locator(".bx-text .lv-on").count(), 0, "no lit verse");
    ok("picking WEB while playing paused the reading and removed the light");
    await ctx.close();

    // ---- The other three views; no sideways scroll at 390 px ----
    for (const [name, opts] of [
      ["desktop-dark", { viewport: { width: 1360, height: 900 }, colorScheme: "dark" }],
      ["phone-390-light", { viewport: { width: 390, height: 844 }, colorScheme: "light", isMobile: true, hasTouch: true, deviceScaleFactor: 2 }],
      ["phone-390-dark", { viewport: { width: 390, height: 844 }, colorScheme: "dark", isMobile: true, hasTouch: true, deviceScaleFactor: 2 }],
    ]) {
      ({ ctx, page } = await open(opts));
      await page.locator(".bx-listen-play").click();
      await waitFor(async () => (await state(page)).lit, 15000, `${name}: a lit word`);
      await page.waitForTimeout(1500);
      await page.locator(".bx-listen-play").click();
      await page.evaluate(() => document.querySelector(".bx-listen").scrollIntoView({ block: "start" }));
      await page.evaluate(() => window.scrollBy(0, -80));
      const wide = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth,
        barRight: document.querySelector(".bx-listen").getBoundingClientRect().right,
        rateRight: document.querySelector(".bx-listen-rate").getBoundingClientRect().right }));
      assert.ok(wide.sw <= wide.iw, `${name}: page ${wide.sw}px wide in a ${wide.iw}px window`);
      assert.ok(wide.rateRight <= wide.iw, `${name}: speed button on screen`);
      await page.screenshot({ path: path.join(shots, `${name}.png`) });
      ok(`${name}: no sideways scroll (${wide.sw}/${wide.iw} px); word lit; screenshot saved`);
      await ctx.close();
    }
    assert.deepEqual(errors, [], "no page errors");
    ok("no console or page errors");
  } catch (e) {
    console.error("FAIL", e && e.message ? e.message : e);
    if (errors.length) console.error("page errors:", errors);
    process.exitCode = 1;
  } finally {
    await browser.close();
    server.kill();
  }
  console.log(`${results.length} checks passed${process.exitCode ? ", then a failure" : ""}`);
})();
