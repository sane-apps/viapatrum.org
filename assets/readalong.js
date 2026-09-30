/* Read-along player: sentence tracking for audiobook works. No dependencies.
 * Pages carry: <div class="rdl-player" data-manifest="..." data-start=".." data-end="..">
 * plus body spans <span class="rdl" data-i="N">. Manifest: {sentences:[{t,s,e}]}.
 * Behavior: no highlight until the user presses play (or taps a sentence);
 * sentences are clickable; the side buttons skip a paragraph. */
(function () {
  "use strict";
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec));
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function initPlayer(box) {
    var audio = new Audio();
    audio.preload = "metadata";
    var btn = $(".rdl-play", box);
    var prev = $(".rdl-prev", box);
    var next = $(".rdl-next", box);
    var bar = $(".rdl-bar", box);
    var fill = $(".rdl-fill", box);
    var time = $(".rdl-time", box);
    var start = parseInt(box.getAttribute("data-start") || "0", 10);
    var end = parseInt(box.getAttribute("data-end") || "0", 10);
    var sentences = [];
    var spans = [];
    var paraStarts = [];
    var current = -1;
    var started = false;

    fetch(box.getAttribute("data-manifest")).then(function (r) { return r.json(); })
      .then(function (m) {
        sentences = m.sentences;
        audio.src = m.audio;
        if (!end) end = sentences.length - 1;
        spans = $all(".rdl", document);
        var lastP = null;
        spans.forEach(function (sp) {
          var p = sp.parentNode;
          if (p !== lastP) {
            lastP = p;
            var idx = parseInt(sp.getAttribute("data-i"), 10);
            if (idx >= start && idx <= end) paraStarts.push(idx);
          }
        });
        time.textContent = "0:00 / " + fmt(sentences[end].e - sentences[start].s);
        audio.addEventListener("loadedmetadata", function () {
          audio.currentTime = sentences[start].s;
        });
      })
      .catch(function () { box.style.display = "none"; });

    function setCurrent(i, scroll) {
      if (i === current || i < start || i > end) return;
      if (current >= 0 && spans[current - start]) spans[current - start].classList.remove("rdl-on");
      current = i;
      var span = spans[current - start];
      if (span) {
        span.classList.add("rdl-on");
        if (scroll !== false && typeof span.scrollIntoView === "function") {
          span.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
      }
    }

    function clearCurrent() {
      if (current >= 0 && spans[current - start]) spans[current - start].classList.remove("rdl-on");
      current = -1;
    }

    function locate(t) {
      for (var i = start; i <= end; i++) {
        if (t < sentences[i].e) return i;
      }
      return end;
    }

    function ready() { return sentences.length > 0; }

    function gotoSentence(i, autoplay) {
      if (!ready()) return;
      if (i < start) i = start;
      if (i > end) i = end;
      audio.currentTime = sentences[i].s + 0.01;
      if (autoplay !== false) {
        started = true;
        setCurrent(i, false);
        if (audio.paused) audio.play();
      } else if (started) {
        setCurrent(i, false);
      }
    }

    function currentPara() {
      var idx = locate(audio.currentTime || 0), p = 0;
      for (var k = 0; k < paraStarts.length; k++) {
        if (paraStarts[k] <= idx) p = k; else break;
      }
      return p;
    }

    function prevPara() {
      if (!ready() || !paraStarts.length) return;
      var p = currentPara();
      if (p > 0 && audio.currentTime - sentences[paraStarts[p]].s < 2) p--;
      gotoSentence(paraStarts[p]);
    }

    function nextPara() {
      if (!ready() || !paraStarts.length) return;
      var p = Math.min(paraStarts.length - 1, currentPara() + 1);
      gotoSentence(paraStarts[p]);
    }

    btn.addEventListener("click", function () {
      if (!ready()) return;
      if (audio.paused) {
        if (audio.currentTime < sentences[start].s || audio.currentTime >= sentences[end].e) {
          audio.currentTime = sentences[start].s;
        }
        audio.play();
      } else {
        audio.pause();
      }
    });
    if (prev) prev.addEventListener("click", prevPara);
    if (next) next.addEventListener("click", nextPara);
    audio.addEventListener("play", function () { started = true; btn.textContent = "❚❚ Pause"; });
    audio.addEventListener("pause", function () { btn.textContent = "▶ Play"; });
    audio.addEventListener("timeupdate", function () {
      if (!ready()) return;
      var t = audio.currentTime;
      if (t >= sentences[end].e) { audio.pause(); audio.currentTime = sentences[start].s; started = false; clearCurrent(); return; }
      if (t < sentences[start].s) return;
      if (started) setCurrent(locate(t));
      var frac = (t - sentences[start].s) / (sentences[end].e - sentences[start].s);
      fill.style.width = (frac * 100).toFixed(1) + "%";
      time.textContent = fmt(t - sentences[start].s) + " / " + fmt(sentences[end].e - sentences[start].s);
    });
    bar.addEventListener("click", function (ev) {
      if (!ready()) return;
      var rect = bar.getBoundingClientRect();
      var frac = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
      audio.currentTime = sentences[start].s + frac * (sentences[end].e - sentences[start].s);
    });
    document.addEventListener("click", function (ev) {
      var span = ev.target.closest ? ev.target.closest(".rdl") : null;
      if (!span || !ready()) return;
      var i = parseInt(span.getAttribute("data-i"), 10);
      if (i >= start && i <= end) gotoSentence(i);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    $all(".rdl-player").forEach(initPlayer);
  });
})();
