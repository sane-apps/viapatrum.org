/* Listen bar on Scripture chapter pages (scripts/kjv_listen.py, owner sketch 2026-11-08).
 * Plays the KJV read aloud and lights the word being read. Only the KJV is ever
 * played or lit: Listen switches the text to the KJV first (site.js does the
 * switch and says so with a "bx:tr" event), and a verse is lit only while its
 * text on the page is the KJV text word for word. Picking another version
 * pauses the reading and drops the light.
 * Nothing is fetched at page load. The first Listen tap starts the audio inside
 * the tap (so iOS allows it) and fetches the word timings alongside:
 *   {dur, verses: [{v, s, e, w?: [start time per whitespace token]}]}
 * A verse without "w" lights as a whole; with no timings the audio still plays. */
(function () {
  "use strict";
  var bx = document.querySelector("[data-bx]");
  var box = bx && bx.querySelector(".bx-listen");
  if (!box) return;
  var text = bx.querySelector(".bx-text");
  var btn = box.querySelector(".bx-listen-play");
  var bar = box.querySelector(".rdl-bar");
  var fill = box.querySelector(".rdl-fill");
  var time = box.querySelector(".rdl-time");
  var rateBtn = box.querySelector(".bx-listen-rate");
  var note = bx.querySelector(".bx-listen-note");
  var RATES = [1, 1.25, 1.5, 0.75];
  var rateAt = 0;
  var dur = parseFloat(box.getAttribute("data-dur")) || 0;
  var media = null;
  var resumeAt = 0;      // where to start when the audio is not made yet
  var timings = null;    // promise of the listen JSON (null data on failure)
  var kjvRows = null;    // promise of the KJV chapter as shipped, [[v, text]]
  var items = [];        // lit targets in time order: {t, end, el, verse}
  var lit = null;
  var litVerse = null;
  var starting = 0;      // bumps on every Listen tap; a stale start gives up
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }
  function total() {
    return media && isFinite(media.duration) && media.duration > 0 ? media.duration : dur;
  }
  function showTime(pos) {
    var tot = total();
    pos = Math.min(Math.max(0, pos || 0), tot || 0);
    var pct = tot > 0 ? pos / tot * 100 : 0;
    fill.style.width = pct.toFixed(1) + "%";
    time.textContent = fmt(pos) + " / " + fmt(tot);
    bar.setAttribute("aria-valuenow", String(Math.round(pct)));
    bar.setAttribute("aria-valuetext", fmt(pos) + " of " + fmt(tot));
  }
  function say(msg) {
    if (!note) return;
    note.textContent = msg || "";
    note.hidden = !msg;
  }
  function label(playing) {
    btn.innerHTML = playing
      ? '<span aria-hidden="true">❚❚</span> Pause'
      : '<span aria-hidden="true">▶</span> Listen<span class="vh"> to the King James Version</span>';
  }

  function audio() {
    if (media) return media;
    media = new Audio();
    media.preload = "none";
    media.src = box.getAttribute("data-audio");
    media.playbackRate = RATES[rateAt];
    media.addEventListener("loadedmetadata", function () {
      if (resumeAt > 0) {
        try { media.currentTime = resumeAt; } catch (e) { /* the next tap tries again */ }
      }
      showTime(media.currentTime);
    });
    media.addEventListener("play", function () { label(true); });
    media.addEventListener("pause", function () { label(false); });
    media.addEventListener("timeupdate", function () { onTime(media.currentTime); });
    media.addEventListener("ended", function () {
      clearLight();
      resumeAt = 0;
      try { media.currentTime = 0; } catch (e) { /* ignore */ }
      showTime(0);
    });
    media.addEventListener("error", function () {
      label(false);
      say("The recording could not be loaded. Try again later.");
    });
    return media;
  }
  function play() {
    var p = audio().play();
    if (p && typeof p.catch === "function") p.catch(function () { /* blocked or replaced */ });
  }

  function getJSON(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    });
  }
  function loadTimings() {
    if (!timings) {
      timings = getJSON(box.getAttribute("data-listen")).catch(function () { return null; });
    }
    return timings;
  }
  function loadKjv() {
    if (!kjvRows) {
      kjvRows = getJSON("/data/bible/kjv/" + text.dataset.book + "/" + text.dataset.chap + ".json")
        .catch(function () { kjvRows = null; return null; });
    }
    return kjvRows;
  }

  // Resolve once the page shows the KJV; Listen asks site.js to switch to it.
  function toKjv() {
    if (bx.dataset.tr === "kjv" && !bx.dataset.loading) return Promise.resolve(false);
    var kjvBtn = bx.querySelector('button[data-tr="kjv"]');
    if (!kjvBtn) return Promise.reject(new Error("no kjv"));
    return new Promise(function (resolve, reject) {
      function on(e) {
        var d = e.detail || {};
        if (d.phase !== "done") return;
        bx.removeEventListener("bx:tr", on);
        if (d.key === "kjv") resolve(true);
        else reject(new Error("kjv not shown"));
      }
      bx.addEventListener("bx:tr", on);
      kjvBtn.click();
    });
  }

  // Wrap each word of the KJV verses in a span, in the same whitespace split
  // the build used (kjv_listen.tokens). A verse whose text is not the KJV
  // text as shipped is left alone and never lit.
  function wrap(data, rows) {
    clearLight();
    items = [];
    var kjv = {};
    (rows || []).forEach(function (r) { kjv[String(r[0])] = String(r[1]); });
    ((data && data.verses) || []).forEach(function (row) {
      var el = text.querySelector('.v[data-v="' + row.v + '"]');
      var vt = el && el.querySelector(".vt");
      if (!vt || kjv[String(row.v)] === undefined || vt.textContent !== kjv[String(row.v)]) return;
      var parts = vt.textContent.split(/(\s+)/);
      var words = parts.filter(function (p) { return p && !/^\s+$/.test(p); });
      if (row.w && row.w.length === words.length) {
        var frag = document.createDocumentFragment();
        var k = 0;
        parts.forEach(function (p) {
          if (!p) return;
          if (/^\s+$/.test(p)) { frag.appendChild(document.createTextNode(p)); return; }
          var sp = document.createElement("span");
          sp.className = "lw";
          sp.textContent = p;
          frag.appendChild(sp);
          items.push({ t: row.w[k], end: k + 1 < row.w.length ? row.w[k + 1] : row.e, el: sp, verse: el });
          k++;
        });
        vt.replaceChildren(frag);
      } else {
        items.push({ t: row.s, end: row.e, el: null, verse: el });
      }
    });
    items.sort(function (a, b) { return a.t - b.t; });
  }
  function unwrap() {
    clearLight();
    text.querySelectorAll(".vt").forEach(function (vt) {
      if (vt.querySelector(".lw")) vt.textContent = vt.textContent;
    });
    items = [];
  }

  function clearLight() {
    if (lit) lit.classList.remove("lw-on");
    if (litVerse) litVerse.classList.remove("lv-on");
    lit = litVerse = null;
  }
  function light(t) {
    // The last target that has started; lit while it is being read (plus a breath).
    var lo = 0, hi = items.length - 1, at = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (items[mid].t <= t) { at = mid; lo = mid + 1; } else hi = mid - 1;
    }
    var it = at >= 0 && t <= items[at].end + 0.6 ? items[at] : null;
    var el = it ? it.el : null, verse = it ? it.verse : null;
    if (el !== lit) {
      if (lit) lit.classList.remove("lw-on");
      if (el) el.classList.add("lw-on");
      lit = el;
    }
    if (verse !== litVerse) {
      if (litVerse) litVerse.classList.remove("lv-on");
      if (verse) {
        verse.classList.add("lv-on");
        var r = verse.getBoundingClientRect();
        if (r.top < 80 || r.bottom > window.innerHeight - 20) {
          verse.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
        }
      }
      litVerse = verse;
    }
  }
  function onTime(t) {
    showTime(t);
    if (items.length && bx.dataset.tr === "kjv") light(t);
  }

  function seekTo(pos) {
    pos = Math.min(Math.max(0, pos), total() || 0);
    if (media && media.readyState >= 1) {
      media.currentTime = pos;
    } else {
      resumeAt = pos;
    }
    showTime(pos);
    if (items.length) light(pos);
  }
  function position() {
    return media && media.readyState >= 1 ? media.currentTime : resumeAt;
  }

  btn.addEventListener("click", function () {
    var m = audio();
    if (!m.paused) { m.pause(); return; }
    var my = ++starting;
    var switching = bx.dataset.tr !== "kjv";
    say("");
    // Start inside the tap; the light follows once the KJV text is on the page.
    play();
    Promise.all([toKjv(), loadTimings(), loadKjv()]).then(function (got) {
      if (my !== starting) return;
      if (switching) say("Switched to the King James Version, the text being read.");
      if (!items.length) wrap(got[1], got[2]);
      if (!m.paused) light(m.currentTime);
    }).catch(function () {
      if (my !== starting) return;
      m.pause();
      say("The King James text could not be loaded, so the reading is paused.");
    });
  });

  // Another version on the page: stop reading and drop the light.
  bx.addEventListener("bx:tr", function (e) {
    var d = e.detail || {};
    if (d.key === "kjv") return;
    if (media && !media.paused) media.pause();
    starting++;
    unwrap();
    if (d.phase === "start") say("");
  });

  rateBtn.addEventListener("click", function () {
    rateAt = (rateAt + 1) % RATES.length;
    var r = RATES[rateAt];
    rateBtn.textContent = r + "×";
    rateBtn.setAttribute("aria-label", "Playback speed " + r + " times");
    if (media) media.playbackRate = r;
  });
  bar.addEventListener("click", function (ev) {
    var rect = bar.getBoundingClientRect();
    if (!rect.width) return;
    seekTo(Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width)) * total());
  });
  bar.addEventListener("keydown", function (ev) {
    var off = position();
    switch (ev.key) {
      case "ArrowLeft": case "ArrowDown": off -= 5; break;
      case "ArrowRight": case "ArrowUp": off += 5; break;
      case "PageDown": off -= 30; break;
      case "PageUp": off += 30; break;
      case "Home": off = 0; break;
      case "End": off = total(); break;
      default: return;
    }
    ev.preventDefault();
    seekTo(off);
  });
  label(false);
  showTime(0);
})();
