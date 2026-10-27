/* Human check before the first download (owner 2026-10-23). The first click
   on a /dl/ link opens a small box with Cloudflare Turnstile; once it passes,
   /api/human sets a two-hour cookie and the file starts. Later clicks go
   straight through. Without JS, /dl/ shows the same box on its own page. */
(function () {
  var SITEKEY = "0x4AAAAAAFjC_XeO0FeHn9dp";
  var passed = function () { return /(?:^|;\s*)vph_ok=1/.test(document.cookie); };
  var box, slot, msg, widget = null, pending = null, loading = null;

  function load() {
    if (window.turnstile) return Promise.resolve();
    if (loading) return loading;
    loading = new Promise(function (ok, fail) {
      window.vpTurnstileReady = ok;
      var s = document.createElement("script");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=vpTurnstileReady";
      s.async = true;
      s.onerror = function () { loading = null; fail(); };
      document.head.appendChild(s);
    });
    return loading;
  }

  function build() {
    box = document.createElement("dialog");
    box.className = "vp-human";
    box.setAttribute("aria-labelledby", "vp-human-h");
    box.innerHTML = '<h2 id="vp-human-h">Quick check</h2>' +
      '<p>Please confirm you are a person. This keeps bots from emptying the shelf. You only do this once every two hours.</p>' +
      '<div class="vp-human-slot"></div><p class="vp-human-msg" role="status" aria-live="polite"></p>' +
      '<button type="button" class="vp-human-x">Cancel</button>';
    document.body.appendChild(box);
    slot = box.querySelector(".vp-human-slot");
    msg = box.querySelector(".vp-human-msg");
    box.querySelector(".vp-human-x").addEventListener("click", function () { box.close(); });
    box.addEventListener("close", function () { pending = null; });
  }

  function passedWith(token) {
    msg.textContent = "Starting your download…";
    fetch("/api/human", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: token }) })
      .then(function (r) {
        if (!r.ok) throw 0;
        var href = pending;
        box.close();
        if (href) location.href = href;
      })
      .catch(function () {
        msg.textContent = "The check did not pass. Please try again.";
        if (widget !== null) window.turnstile.reset(widget);
      });
  }

  function ask(href) {
    if (!box) build();
    pending = href;
    msg.textContent = "";
    if (!box.open) box.showModal();
    load().then(function () {
      if (widget === null) {
        widget = window.turnstile.render(slot, { sitekey: SITEKEY, action: "download", callback: passedWith,
          "error-callback": function () { msg.textContent = "The check could not run. Please try again."; } });
      } else {
        window.turnstile.reset(widget);
      }
    }, function () {
      // Turnstile did not load (blocked or offline): the /dl/ page has its own box.
      box.close();
      location.href = href;
    });
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href^="/dl/"]');
    if (!a || passed() || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (typeof HTMLDialogElement === "undefined") return;
    e.preventDefault();
    ask(a.getAttribute("href"));
  });
})();
