/* Ask page (scripts/ask_page.py): sends the question to /api/ask and draws the
   answer, the writers' own sentences, then the passages. States: empty (no
   question), loading, answer, thin (the library is thin here), nothing found,
   error (the API is down: link to the library search instead), and paused
   (the server's AI_OFF switch: the same link, with a note that it is paused). */
(function () {
  var page = document.querySelector(".ask-page");
  if (!page) return;
  var form = page.querySelector(".ask-form");
  var input = page.querySelector("#ask-q");
  var button = form.querySelector('button[type="submit"]');
  var out = page.querySelector("#ask-out");
  var status = page.querySelector("#ask-status");
  var empty = out.innerHTML;
  var seq = 0;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function libraryLink(q, label) {
    return '<p class="ask-more"><a href="/works/?q=' + encodeURIComponent(q) + '">' + esc(label) + "</a></p>";
  }
  // Passage links are site paths only.
  function href(h) { h = String(h || ""); return h.charAt(0) === "/" && h.charAt(1) !== "/" ? esc(h) : "/works/"; }
  function year(y) { return y < 0 ? -y + " BC" : y + " AD"; }
  function span(answer) {
    var ys = answer.map(function (a) { return a.year; }).filter(function (y) { return typeof y === "number"; });
    if (!ys.length) return "";
    var lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
    if (lo === hi) return "c. " + year(lo);
    return lo < 0 && hi > 0 ? "c. " + year(lo) + "–" + year(hi) : "c. " + Math.abs(lo) + "–" + year(hi);
  }

  function quotes(data) {
    var n = data.passages.length;
    var from = span(data.answer);
    var items = data.answer.map(function (a) {
      var ref = parseInt(a.ref, 10) || 1;
      var who = esc(a.author) + (a.author_dates ? " (" + esc(a.author_dates) + ")" : "");
      return '<li><blockquote class="ask-quote"><p>“' + esc(a.text) + '”</p></blockquote>' +
        '<p class="ask-cite">— <a href="' + href(a.href) + '">' + who + ", " + esc(a.cite || a.title) + "</a>" +
        ' <a class="ask-ref" href="#ask-p-' + ref + '" aria-label="Passage ' + ref + ' below">[' + ref + "]</a></p></li>";
    }).join("");
    return '<section class="ask-answer" aria-labelledby="ask-say">' +
      '<h2 id="ask-say" class="vp-section-label" tabindex="-1">What the writers say</h2>' +
      '<p class="ask-from">From ' + n + " passage" + (n === 1 ? "" : "s") + (from ? ", " + from : "") + "</p>" +
      '<ol class="ask-quotes">' + items + "</ol></section>";
  }

  function passageList(data) {
    var rows = data.passages.map(function (p, i) {
      return '<li id="ask-p-' + (i + 1) + '"><span class="ask-n">[' + (i + 1) + "]</span>" +
        '<a href="' + href(p.href) + '"><strong>' + esc(p.title) + "</strong><span class=\"ask-by\">" + esc(p.author) + "</span>" +
        '<em class="meaning-snippet">' + esc(p.snippet) + '</em><span class="go">Read →</span></a></li>';
    }).join("");
    return '<section class="ask-passages" aria-labelledby="ask-pass"><h2 id="ask-pass" class="vp-section-label" tabindex="-1">Passages</h2>' +
      '<ol class="ask-plist">' + rows + "</ol></section>";
  }

  // Timeline topics and History articles that match the question (from
  // /api/ask): shown first, above the answer and the passages.
  function topicsBlock(data) {
    var ts = data.topics || [];
    if (!ts.length) return "";
    var items = ts.map(function (t) {
      var kind = t.kind === "article" ? "History article \u2192" : "Timeline topic \u2192";
      return '<li><a href="' + href(t.href) + '"><strong>' + esc(t.question) + '</strong><span class="go">' + kind + "</span></a></li>";
    }).join("");
    return '<section class="ask-topics" aria-labelledby="ask-tl"><h2 id="ask-tl" class="vp-section-label" tabindex="-1">On the Timeline</h2>' +
      '<ul class="ask-tlist">' + items + "</ul></section>";
  }

  function render(q, data) {
    var p = data.passages || [];
    data.passages = p;
    data.answer = data.answer || [];
    var topics = topicsBlock(data);
    if (!p.length) {
      if (topics) {
        out.innerHTML = topics + '<section class="ask-none"><p class="ask-note">We found no passages for that question yet. Try other words, or search the whole library.</p>' +
          libraryLink(q, "Search the library for \u201c" + q + "\u201d \u2192") + "</section>";
        return "Timeline topic found. No passages found yet.";
      }
      out.innerHTML = '<section class="ask-none"><p class="ask-note">We found no passages for that question yet. Try other words, or search the whole library.</p>' +
        libraryLink(q, "Search the library for “" + q + "” →") + "</section>";
      return "No passages found yet.";
    }
    var html = topics;
    if (data.mode === "answer" && data.answer.length) {
      html += quotes(data);
    } else {
      html += '<p class="ask-note ask-thin">' + esc(data.note || "Our library does not cover this well yet. These are the closest passages; more works are being translated.") + "</p>";
    }
    html += passageList(data) + libraryLink(q, "See every match in the library →");
    out.innerHTML = html;
    return data.mode === "answer" && data.answer.length
      ? "Answer ready: " + data.answer.length + " sentences from " + p.length + " passages."
      : "The library is thin on this. Showing the " + p.length + " closest passages.";
  }

  // Loading state (2026-10-30): a spinner, a labelled line, skeleton rows
  // where the passages will land, and the Ask button disabled with an
  // "Asking…" label. The old state was one quiet italic line, which read
  // as nothing happening. settle() runs on every exit path of ask().
  function showLoading() {
    if (button) { button.disabled = true; button.textContent = "Asking\u2026"; }
    out.setAttribute("aria-busy", "true");
    out.innerHTML = '<div class="ask-loading" role="presentation">' +
      '<p class="ask-loading-line"><span class="ask-spinner" aria-hidden="true"></span>Finding what the writers say\u2026</p>' +
      '<div class="ask-skel" aria-hidden="true"><span></span><span></span><span></span></div></div>';
    status.textContent = "Finding what the writers say.";
  }
  function settle() {
    out.setAttribute("aria-busy", "false");
    if (button) { button.disabled = false; button.textContent = "Ask"; }
  }

  function ask(q, moveFocus) {
    var mine = ++seq;
    q = String(q || "").trim().slice(0, 300);
    input.value = q;
    if (!q) {
      out.innerHTML = empty;
      settle();
      status.textContent = "";
      document.title = "Ask the Fathers · Via Patrum";
      return;
    }
    document.title = q + " · Ask the Fathers · Via Patrum";
    showLoading();
    fetch("/api/ask?q=" + encodeURIComponent(q))
      .then(function (r) {
        if (r.status === 503) return r.json().catch(function () { return {}; }).then(function (d) { if (d && d.paused) throw "paused"; throw new Error("HTTP 503"); });
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (mine !== seq) return;
        if (!data || data.error) throw new Error((data && data.error) || "no answer");
        status.textContent = render(q, data);
        settle();
        var head = out.querySelector("h2[tabindex]");
        if (moveFocus && head) head.focus({ preventScroll: false });
      })
      .catch(function (e) {
        if (mine !== seq) return;
        // AI_OFF on the server: say it is paused, not broken.
        var note = e === "paused" ? "Ask is paused for now. The library search still works." : "Ask is not answering right now. The library search still works.";
        out.innerHTML = '<section class="ask-error"><p class="ask-note">' + note + "</p>" +
          libraryLink(q, "Search the library for “" + q + "” →") + "</section>";
        settle();
        status.textContent = (e === "paused" ? "Ask is paused for now." : "Ask is not answering right now.") + " A link to the library search is shown.";
      });
  }

  function fromUrl(moveFocus) {
    ask(new URLSearchParams(location.search).get("q") || "", moveFocus);
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (!q) { input.focus(); return; }
    history.pushState(null, "", "/ask/?q=" + encodeURIComponent(q));
    ask(q, true);
  });
  window.addEventListener("popstate", function () { fromUrl(false); });
  fromUrl(false);
})();
