/* Ask page (scripts/ask_page.py): sends the question to /api/ask and draws the
   answer, the writers' own sentences, then the passages. States: empty (no
   question), loading, answer, thin (the library is thin here), nothing found,
   and error (the API is down: link to the library search instead). */
(function () {
  var page = document.querySelector(".ask-page");
  if (!page) return;
  var form = page.querySelector(".ask-form");
  var input = page.querySelector("#ask-q");
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

  function render(q, data) {
    var p = data.passages || [];
    data.passages = p;
    data.answer = data.answer || [];
    if (!p.length) {
      out.innerHTML = '<section class="ask-none"><p class="ask-note">We found no passages for that question yet. Try other words, or search the whole library.</p>' +
        libraryLink(q, "Search the library for “" + q + "” →") + "</section>";
      return "No passages found yet.";
    }
    var html = "";
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

  function ask(q, moveFocus) {
    var mine = ++seq;
    q = String(q || "").trim().slice(0, 300);
    input.value = q;
    if (!q) {
      out.innerHTML = empty;
      out.setAttribute("aria-busy", "false");
      status.textContent = "";
      document.title = "Ask the Fathers · Via Patrum";
      return;
    }
    document.title = q + " · Ask the Fathers · Via Patrum";
    out.setAttribute("aria-busy", "true");
    out.innerHTML = '<p class="ask-loading">Finding what the writers say…</p>';
    status.textContent = "Finding what the writers say.";
    fetch("/api/ask?q=" + encodeURIComponent(q))
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (data) {
        if (mine !== seq) return;
        if (!data || data.error) throw new Error((data && data.error) || "no answer");
        status.textContent = render(q, data);
        out.setAttribute("aria-busy", "false");
        var head = out.querySelector("h2[tabindex]");
        if (moveFocus && head) head.focus({ preventScroll: false });
      })
      .catch(function () {
        if (mine !== seq) return;
        out.innerHTML = '<section class="ask-error"><p class="ask-note">Ask is not answering right now. The library search still works.</p>' +
          libraryLink(q, "Search the library for “" + q + "” →") + "</section>";
        out.setAttribute("aria-busy", "false");
        status.textContent = "Ask is not answering right now. A link to the library search is shown.";
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
