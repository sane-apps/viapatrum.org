// Browser check of /charts/fathers/ (the Fathers through time).
//
//   node scripts/charts_e2e.cjs <base-url> <out-dir>
//
// Headless Brave (never Chrome or Safari). Checks: the page loads with its
// bars, councils and list; Charts is in the menu on desktop and phone; no two
// labels overlap at any zoom; zoom in and out work and stop at the ends;
// Tab reaches the zoom buttons and the bars with a visible focus ring; a bar
// opens that Father's page; at 390 px the page itself never scrolls sideways
// while the chart scrolls inside its box. Screenshots, light and dark, desktop
// and 390 px, go to <out-dir>.
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

const [base, out] = process.argv.slice(2);
if (!base || !out) { console.error("usage: charts_e2e.cjs <base> <out-dir>"); process.exit(2); }
fs.mkdirSync(out, { recursive: true });
const URL_ = base.replace(/\/$/, "") + "/charts/fathers/";
let failed = 0;
const ok = (name) => console.log("PASS", name);

// Every pair of label boxes in one lane must not overlap.
const overlaps = () => [...document.querySelectorAll(".fc-lane")].flatMap((lane) => {
  const boxes = [...lane.querySelectorAll(".fc-bar, .fc-council")].map((el) => {
    const r = [...el.querySelectorAll(".fc-name, .fc-dates, .fc-line")].map((s) => s.getBoundingClientRect());
    return { name: el.querySelector(".fc-name").textContent, l: Math.min(...r.map((b) => b.left)), rt: Math.max(...r.map((b) => b.right)),
      t: Math.min(...r.map((b) => b.top)), b: Math.max(...r.map((b) => b.bottom)) };
  });
  const rows = lane.querySelector(".fc-rows").getBoundingClientRect();
  const bad = [];
  boxes.forEach((a, i) => {
    if (a.b > rows.bottom + 1) bad.push(`${a.name} spills out of its lane`);
    boxes.slice(i + 1).forEach((b) => {
      if (a.l < b.rt && b.l < a.rt && a.t < b.b && b.t < a.b) bad.push(`${a.name} / ${b.name}`);
    });
  });
  return bad;
});

(async () => {
  const browser = await chromium.launch({ executablePath: "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", headless: true });
  const errors = [];
  const watch = (page) => {
    // A missing file is reported by its address (the console line has none).
    page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("response", (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
  };
  try {
    for (const scheme of ["light", "dark"]) {
      const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, colorScheme: scheme });
      const page = await ctx.newPage();
      watch(page);
      await page.goto(URL_, { waitUntil: "networkidle" });
      if (scheme === "light") {
        assert.match(await page.title(), /^The Fathers through time · Via Patrum$/);
        const bars = await page.locator(".fc-bar").count();
        assert.ok(bars >= 40, `bars on the chart: ${bars}`);
        assert.equal(await page.locator(".fc-council").count(), 7, "seven councils");
        assert.equal(await page.locator("#fc-list li a[href^='/authors/']").count(), bars, "the list names every Father on the chart");
        assert.equal(await page.locator('.site-nav a[href="/charts/"][aria-current="page"]').count(), 1, "Charts is in the menu and marked current");
        ok(`page loads: ${bars} Fathers, 7 councils, list and menu entry`);

        // Zoom: every step re-packs with no overlapping labels, and the ends stop.
        const zin = page.getByRole("button", { name: "Zoom in" });
        const zout = page.getByRole("button", { name: "Zoom out" });
        await zin.waitFor();
        const width = () => page.locator(".fc-canvas").evaluate((el) => el.getBoundingClientRect().width);
        const w0 = await width();
        assert.deepEqual(await page.evaluate(overlaps), [], "no overlaps at the first zoom");
        await zin.click();
        const w1 = await width();
        assert.ok(w1 > w0 * 1.2, `zoom in widens the chart (${w0} -> ${w1})`);
        assert.deepEqual(await page.evaluate(overlaps), [], "no overlaps after zoom in");
        while (await zin.isEnabled()) await zin.click();
        assert.deepEqual(await page.evaluate(overlaps), [], "no overlaps at the largest zoom");
        while (await zout.isEnabled()) await zout.click();
        assert.ok((await width()) < w0, "zoom out narrows the chart below the first view");
        assert.deepEqual(await page.evaluate(overlaps), [], "no overlaps at the smallest zoom");
        assert.equal(await zout.isDisabled(), true, "zoom out stops at the smallest step");
        ok("zoom in and out work, stop at the ends, and no label overlaps at any step");

        // Keyboard: Tab from the zoom-out button reaches zoom in, the chart box, then the first bar.
        await page.reload({ waitUntil: "networkidle" });
        await page.getByRole("button", { name: "Zoom out" }).focus();
        await page.keyboard.press("Tab");
        assert.equal(await page.evaluate(() => document.activeElement.getAttribute("aria-label")), "Zoom in");
        await page.keyboard.press("Enter");
        assert.equal(await page.locator(".fc-chart").getAttribute("data-zoom"), "3", "Enter on Zoom in zooms");
        await page.keyboard.press("Tab");
        assert.equal(await page.evaluate(() => document.activeElement.classList.contains("fc-scroll")), true, "the chart box takes focus");
        await page.keyboard.press("-");
        assert.equal(await page.locator(".fc-chart").getAttribute("data-zoom"), "2", "- in the chart box zooms out");
        await page.keyboard.press("Tab");
        const first = await page.evaluate(() => {
          const a = document.activeElement;
          const st = getComputedStyle(a);
          return { cls: a.className, href: a.getAttribute("href"), outline: st.outlineStyle, ow: parseFloat(st.outlineWidth) };
        });
        assert.match(first.cls, /fc-council|fc-bar/, `Tab reaches the chart marks (${first.cls})`);
        assert.ok(first.outline !== "none" && first.ow >= 2, `visible focus ring (${first.outline} ${first.ow})`);
        let reachedBar = first.cls.includes("fc-bar");
        for (let i = 0; i < 10 && !reachedBar; i++) {
          await page.keyboard.press("Tab");
          reachedBar = await page.evaluate(() => document.activeElement.classList.contains("fc-bar"));
        }
        assert.ok(reachedBar, "Tab reaches a Father's bar");
        await page.screenshot({ path: path.join(out, "desktop-light-focus.png") });
        ok("keyboard: zoom buttons, chart box (+/-) and bars, with a visible focus ring");

        // A bar opens that Father's page.
        await page.locator('.fc-bar[href="/authors/polycarp-of-smyrna/"]').click();
        await page.waitForURL(/\/authors\/polycarp-of-smyrna\/$/);
        assert.match(await page.locator("h1").first().innerText(), /Polycarp/);
        ok("a bar opens that Father's page (Polycarp of Smyrna)");
        await page.goto(URL_, { waitUntil: "networkidle" });
      }
      await page.screenshot({ path: path.join(out, `desktop-${scheme}.png`) });
      await page.screenshot({ path: path.join(out, `desktop-${scheme}-full.png`), fullPage: true });
      await ctx.close();

      const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, colorScheme: scheme });
      const p = await phone.newPage();
      watch(p);
      await p.goto(URL_, { waitUntil: "networkidle" });
      const m = await p.evaluate(() => ({
        page: document.documentElement.scrollWidth, view: document.documentElement.clientWidth,
        box: document.querySelector(".fc-scroll").clientWidth, inner: document.querySelector(".fc-scroll").scrollWidth,
      }));
      assert.ok(m.page <= m.view, `no page-level sideways scroll at 390 px (${m.page} > ${m.view})`);
      assert.ok(m.inner > m.box, "the chart scrolls sideways inside its box");
      assert.deepEqual(await p.evaluate(overlaps), [], "no overlaps on the phone");
      await p.screenshot({ path: path.join(out, `phone-${scheme}.png`) });
      await p.locator(".fc-scroll").scrollIntoViewIfNeeded();
      await p.locator(".fc-scroll").evaluate((el) => { el.scrollLeft = 300; });
      await p.screenshot({ path: path.join(out, `phone-${scheme}-chart.png`) });
      if (scheme === "light") {
        await p.evaluate(() => window.scrollTo(0, 0));
        await p.getByRole("button", { name: "Menu" }).click();
        assert.equal(await p.locator('#site-nav a[href="/charts/"]').isVisible(), true, "Charts is in the phone menu");
        await p.screenshot({ path: path.join(out, "phone-light-menu.png") });
        ok("phone menu lists Charts");
      }
      await p.screenshot({ path: path.join(out, `phone-${scheme}-full.png`), fullPage: true });
      await phone.close();
      ok(`390 px ${scheme}: page does not scroll sideways, chart does, no overlaps`);
    }
    // The narrowest desktop header (just over the 800 px Menu switch) keeps every link on one row.
    const mid = await browser.newContext({ viewport: { width: 820, height: 700 } });
    const mp = await mid.newPage();
    watch(mp);
    await mp.goto(URL_, { waitUntil: "networkidle" });
    const nav = await mp.evaluate(() => [...document.querySelectorAll("#site-nav a")].filter((a) => a.offsetParent)
      .map((a) => Math.round(a.getBoundingClientRect().top)));
    assert.ok(nav.length >= 8, `desktop menu shows its links (${nav.length})`);
    assert.equal(new Set(nav).size, 1, `desktop menu stays on one row at 820 px (${nav})`);
    await mp.screenshot({ path: path.join(out, "desktop-820-light.png") });
    await mid.close();
    ok("desktop menu with Charts fits one row at 820 px");

    const idx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
    const ip = await idx.newPage();
    watch(ip);
    await ip.goto(base.replace(/\/$/, "") + "/charts/", { waitUntil: "networkidle" });
    await ip.locator('a.fc-card[href="/charts/fathers/"]').click();
    await ip.waitForURL(/\/charts\/fathers\/$/);
    await idx.close();
    ok("/charts/ lists the chart and links to it");
    assert.deepEqual(errors.filter((e) => !/favicon|og\//.test(e)), [], "no console errors");
    ok("no console errors");
  } catch (e) {
    failed = 1;
    console.error("FAIL", e.message);
  } finally {
    await browser.close();
  }
  process.exit(failed);
})();
