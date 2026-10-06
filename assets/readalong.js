/* Read-along player: sentence tracking for audiobook works. No dependencies.
 * Pages carry: <div class="rdl-player" data-manifest="..." data-start=".." data-end=".."
 *   data-audio="<mp3 url>" data-t0="<passage start in the mp3, s>" data-dur="<length, s>">
 * plus body spans <span class="rdl" data-i="N">. Manifest: {audio, sentences:[{t,s,e}]}.
 * Nothing is fetched at page load (2026-10-06 audit: a long reader made 155
 * manifest and 155 mp3 requests before anyone pressed Play). The first Play,
 * sentence tap or skip starts the audio inside that tap, so iOS allows it, and
 * fetches the sentence timings alongside. One audio element serves every
 * player on the page, so auto-advance to the next passage keeps working on iOS.
 * No highlight until the user presses play (or taps a sentence); the side
 * buttons skip a paragraph; the seek bar works with arrows, Home and End. */
(function () {
  "use strict";
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec));
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  var media = null;       // the page's one audio element
  var owner = null;       // the player bound to it
  var pendingSeek = null; // a seek asked for before the mp3's length is known
  var players = [];

  function el() {
    if (media) return media;
    media = new Audio();
    media.preload = "none";
    media.addEventListener("loadedmetadata", function () {
      if (pendingSeek !== null) {
        var t = pendingSeek;
        pendingSeek = null;
        try { media.currentTime = t; } catch (e) { /* ignore */ }
      }
    });
    media.addEventListener("play", function () { if (owner) owner.onPlay(); });
    media.addEventListener("pause", function () { if (owner) owner.onPause(); });
    media.addEventListener("timeupdate", function () { if (owner) owner.onTime(media.currentTime); });
    media.addEventListener("error", function () { if (owner) owner.onError(); });
    return media;
  }

  function seek(t) {
    var m = el();
    if (m.readyState >= 1) {
      pendingSeek = null;
      m.currentTime = t;
    } else {
      pendingSeek = t;
    }
  }

  function play() {
    var p = el().play();
    if (p && typeof p.catch === "function") p.catch(function () { /* blocked or replaced */ });
  }

  function initPlayer(box) {
    var api = {};
    var btn = $(".rdl-play", box);
    // One passage on the continuous reader is wrapped in .rdl-scope.
    // A cite page has a single player and no scope, so it uses the document.
    var scope = box.closest(".rdl-scope") || document;
    var prev = $(".rdl-prev", box);
    var next = $(".rdl-next", box);
    var bar = $(".rdl-bar", box);
    var fill = $(".rdl-fill", box);
    var time = $(".rdl-time", box);
    var start = parseInt(box.getAttribute("data-start") || "0", 10);
    // data-end="0" is the first sentence, not "missing". Only a missing
    // attribute means the whole manifest.
    var endRaw = box.getAttribute("data-end");
    var end = endRaw === null || endRaw === "" ? NaN : parseInt(endRaw, 10);
    var src = box.getAttribute("data-audio") || "";
    var t0 = parseFloat(box.getAttribute("data-t0"));
    var dur = parseFloat(box.getAttribute("data-dur"));
    var sentences = [];
    var byIdx = {};
    var paraStarts = [];
    var current = -1;
    var started = false;
    var loading = null;
    var resumeAt = null; // mp3 time to start from when this passage next takes the audio

    function ready() { return sentences.length > 0; }
    function base() { return ready() ? sentences[start].s : (isNaN(t0) ? 0 : t0); }
    function total() {
      if (ready()) return sentences[end].e - sentences[start].s;
      return isNaN(dur) ? 0 : dur;
    }

    function showTime(pos) {
      var tot = total();
      pos = Math.min(Math.max(0, pos), tot);
      var pct = tot > 0 ? pos / tot * 100 : 0;
      fill.style.width = pct.toFixed(1) + "%";
      time.textContent = fmt(pos) + " / " + fmt(tot);
      bar.setAttribute("aria-valuenow", String(Math.round(pct)));
      bar.setAttribute("aria-valuetext", fmt(pos) + " of " + fmt(tot));
    }
    if (!isNaN(dur)) showTime(0);

    function load() {
      if (loading) return loading;
      loading = fetch(box.getAttribute("data-manifest"))
        .then(function (r) {
          if (!r.ok) throw new Error("manifest " + r.status);
          return r.json();
        })
        .then(function (m) {
          if (!m.sentences || !m.sentences.length) throw new Error("empty manifest");
          sentences = m.sentences;
          if (!src) src = m.audio;
          if (isNaN(end) || end >= sentences.length) end = sentences.length - 1;
          var lastP = null;
          $all(".rdl", scope).forEach(function (sp) {
            var idx = parseInt(sp.getAttribute("data-i"), 10);
            if (!(idx >= start && idx <= end)) return;
            byIdx[idx] = sp;
            if (sp.parentNode !== lastP) {
              lastP = sp.parentNode;
              paraStarts.push(idx);
            }
          });
          if (owner !== api) showTime(resumeAt !== null ? resumeAt - base() : 0);
          return true;
        })
        .catch(function () {
          box.style.display = "none";
          if (owner === api) {
            el().pause();
            el().muted = false;
          }
          return false;
        });
      return loading;
    }

    // A recorded row that is only punctuation shares the span before it.
    function spanFor(i) {
      for (var k = i; k >= start; k--) if (byIdx[k]) return byIdx[k];
      return null;
    }

    function setCurrent(i, scroll) {
      if (i === current || i < start || i > end) return;
      var old = current >= 0 ? spanFor(current) : null;
      var span = spanFor(i);
      current = i;
      if (old === span) return;
      if (old) old.classList.remove("rdl-on");
      if (span) {
        span.classList.add("rdl-on");
        if (scroll !== false && typeof span.scrollIntoView === "function") {
          span.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
      }
    }

    function clearCurrent() {
      var span = current >= 0 ? spanFor(current) : null;
      if (span) span.classList.remove("rdl-on");
      current = -1;
    }

    function locate(t) {
      for (var i = start; i <= end; i++) {
        if (t < sentences[i].e) return i;
      }
      return end;
    }

    function bind() {
      // Point the page's audio at this passage's mp3, starting where it should.
      var m = el();
      var want = resumeAt !== null ? resumeAt : base();
      resumeAt = null;
      m.src = src + "#t=" + want.toFixed(2);
      seek(want);
      api.bound = true;
    }

    function take() {
      var m = el();
      if (owner === api) return m;
      if (owner) owner.release();
      owner = api;
      m.muted = false;
      api.bound = false;
      if (src) bind();
      return m;
    }

    api.release = function () {
      // Another passage takes the audio: remember where this one stopped.
      if (ready() && api.bound && pendingSeek === null) {
        var t = el().currentTime;
        resumeAt = (t > sentences[start].s && t < sentences[end].e) ? t : null;
      }
      api.bound = false;
      started = false;
      clearCurrent();
      btn.textContent = "▶ Play";
    };

    function resolve(target) {
      if (target === "next") return paraStarts.length > 1 ? paraStarts[1] : start;
      if (target === "prev") return start;
      return target;
    }

    function begin(target) {
      // target: a sentence index, "prev"/"next", or null for the start
      // (or wherever this passage stopped).
      var m = take();
      if (ready() && api.bound) {
        if (target !== null) gotoSentence(resolve(target));
        else play();
        return;
      }
      // First use: start the audio inside the tap and fetch the timings
      // alongside. A sentence or skip tap stays muted until we know where
      // that sentence starts.
      if (src && api.bound) {
        if (target !== null) m.muted = true;
        play();
      }
      load().then(function (ok) {
        if (!ok || owner !== api) {
          if (owner === api) m.muted = false;
          return;
        }
        if (!api.bound) bind(); // a page without data-audio
        if (target !== null) {
          gotoSentence(resolve(target));
        } else if (pendingSeek === null) {
          var t = m.currentTime;
          if (t < sentences[start].s || t >= sentences[end].e) seek(sentences[start].s);
        }
        m.muted = false;
        if (m.paused) play();
      });
    }

    function gotoSentence(i) {
      if (i < start) i = start;
      if (i > end) i = end;
      seek(sentences[i].s + 0.01);
      started = true;
      setCurrent(i, false);
      if (el().paused) play();
    }

    function playing() { return owner === api && ready() && api.bound; }

    function currentPara() {
      var idx = locate(el().currentTime || 0), p = 0;
      for (var k = 0; k < paraStarts.length; k++) {
        if (paraStarts[k] <= idx) p = k; else break;
      }
      return p;
    }

    function prevPara() {
      if (!playing()) { begin("prev"); return; }
      if (!paraStarts.length) return;
      var p = currentPara();
      if (p > 0 && el().currentTime - sentences[paraStarts[p]].s < 2) p--;
      gotoSentence(paraStarts[p]);
    }

    function nextPara() {
      if (!playing()) { begin("next"); return; }
      if (!paraStarts.length) return;
      var p = Math.min(paraStarts.length - 1, currentPara() + 1);
      gotoSentence(paraStarts[p]);
    }

    function position() {
      if (playing()) return (pendingSeek !== null ? pendingSeek : el().currentTime) - sentences[start].s;
      return resumeAt !== null ? resumeAt - base() : 0;
    }

    function seekPassage(off) {
      off = Math.min(Math.max(0, off), total());
      if (playing()) {
        seek(sentences[start].s + off);
        if (started) setCurrent(locate(sentences[start].s + off), false);
      } else {
        // Not loaded yet: keep the spot for when Play is pressed. No network.
        resumeAt = base() + off;
      }
      showTime(off);
    }

    function finish() {
      var m = el();
      m.pause();
      started = false;
      clearCurrent();
      resumeAt = null;
      seek(sentences[start].s);
      showTime(0);
      var at = players.indexOf(api);
      if (at >= 0 && players[at + 1]) players[at + 1].advance();
    }

    api.advance = function () { begin(null); };
    api.prefetch = function () { if (src) load(); };
    api.onPlay = function () {
      started = true;
      btn.textContent = "❚❚ Pause";
      var at = players.indexOf(api);
      // Fetch the next passage's timings (not its audio) so the hand-over is quick.
      if (at >= 0 && players[at + 1]) players[at + 1].prefetch();
    };
    api.onPause = function () { btn.textContent = "▶ Play"; };
    api.onError = function () {
      el().muted = false;
      btn.textContent = "▶ Play";
    };
    api.onTime = function (t) {
      if (!ready() || pendingSeek !== null) return;
      if (t >= sentences[end].e) { finish(); return; }
      if (t < sentences[start].s) return;
      if (started) setCurrent(locate(t));
      showTime(t - sentences[start].s);
    };

    btn.addEventListener("click", function () {
      var m = el();
      if (owner === api && !m.paused) { m.pause(); return; }
      if (playing()) {
        var t = m.currentTime;
        if (pendingSeek === null && (t < sentences[start].s || t >= sentences[end].e)) {
          seek(sentences[start].s);
        }
        play();
        return;
      }
      begin(null);
    });
    if (prev) prev.addEventListener("click", prevPara);
    if (next) next.addEventListener("click", nextPara);
    bar.addEventListener("click", function (ev) {
      var rect = bar.getBoundingClientRect();
      if (!rect.width) return;
      var frac = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
      seekPassage(frac * total());
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
      seekPassage(off);
    });
    scope.addEventListener("click", function (ev) {
      var span = ev.target.closest ? ev.target.closest(".rdl") : null;
      if (!span) return;
      if (scope !== document && !scope.contains(span)) return;
      var i = parseInt(span.getAttribute("data-i"), 10);
      if (!(i >= start && (isNaN(end) || i <= end))) return;
      if (playing()) gotoSentence(i);
      else begin(i);
    });
    return api;
  }

  document.addEventListener("DOMContentLoaded", function () {
    players = $all(".rdl-player").map(initPlayer);
  });
})();
