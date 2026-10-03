// Plays a page's read-along player headless and checks the highlighted
// sentence follows the audio. Usage: node readalong_check.cjs <page-url> <png>
const path = require("path");
const { chromium } = require(path.join(process.env.HOME, "SaneApps/websites/fathers.saneapps.com/node_modules/playwright"));
(async () => {
  const [url, png] = process.argv.slice(2);
  const browser = await chromium.launch({ executablePath: "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", headless: true, args: ["--autoplay-policy=no-user-gesture-required"] });
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  page.on("console", (m) => m.type() === "error" && console.log("console error:", m.text()));
  await page.addInitScript(() => {
    const A = window.Audio;
    window.__audios = [];
    window.Audio = function (...a) { const x = new A(...a); window.__audios.push(x); return x; };
  });
  await page.goto(url, { waitUntil: "load" });
  await page.waitForFunction(() => window.__audios.length && window.__audios[0].src, null, { timeout: 15000 });
  const manifest = await page.evaluate(async () => (await fetch(document.querySelector(".rdl-player").dataset.manifest)).json());
  const S = manifest.sentences;
  console.log("audio src", await page.evaluate(() => window.__audios[0].src));
  await page.click(".rdl-play");
  await page.waitForTimeout(4000);
  let st = await page.evaluate(() => ({ t: window.__audios[0].currentTime, paused: window.__audios[0].paused, rs: window.__audios[0].readyState, on: document.querySelector(".rdl-on")?.dataset.i }));
  let want = S.findIndex((x) => st.t < x.e);
  console.log("after play:", JSON.stringify(st), "expected sentence", want);
  let ok = !st.paused && st.t > 1 && Number(st.on) === want;
  const target = Math.min(2, S.length - 1);
  await page.click(`.rdl[data-i="${target}"]`);
  await page.waitForTimeout(1500);
  st = await page.evaluate(() => ({ t: window.__audios[0].currentTime, paused: window.__audios[0].paused, on: document.querySelector(".rdl-on")?.dataset.i }));
  console.log("after clicking sentence", target, "(s=" + S[target].s + "):", JSON.stringify(st));
  ok = ok && Number(st.on) === target && st.t >= S[target].s && st.t < S[target].e;
  await page.screenshot({ path: png });
  await browser.close();
  console.log(ok ? "READALONG OK" : "READALONG FAIL");
  process.exit(ok ? 0 : 1);
})();
