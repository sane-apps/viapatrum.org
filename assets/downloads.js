/* Downloads page (scripts/downloads_page.py): locked/unlocked state, shelf
   search over the writer groups, Lemon Squeezy checkout overlay, unlock right
   after purchase, and key entry. Without JS the page still works: Buy opens
   the hosted checkout, /dl/ links redirect here, and each writer group opens
   with a tap. */
(function () {
  var page = document.querySelector(".dl-page");
  if (!page) return;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var params = new URLSearchParams(location.search);
  var need = params.get("need");
  var thanks = params.get("thanks");

  function post(url, body) {
    return fetch(url, { method: "POST", headers: { "content-type": "application/json" }, credentials: "same-origin", body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { d._status = r.status; return d; }); });
  }

  function setState(unlocked, hint) {
    page.setAttribute("data-state", unlocked ? "unlocked" : "locked");
    $$("[data-key-hint]").forEach(function (el) { el.textContent = hint ? "(key " + hint + ")" : ""; });
    if (unlocked && need) startDownload(need);
  }

  function startDownload(path) {
    if (!/^(epub|pdf|word|audio|bundles)\/[a-z0-9][a-z0-9._-]*$/.test(path)) return;
    need = null;
    var a = document.createElement("a");
    a.href = "/dl/" + path;
    a.rel = "nofollow";
    document.body.appendChild(a);
    a.click();
    a.remove();
    history.replaceState(null, "", location.pathname + "#shelf");
  }

  fetch("/api/library/status", { credentials: "same-origin", cache: "no-store" })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      setState(Boolean(d.unlocked), d.key_hint);
      if (thanks && !d.unlocked) { keyDialog.showModal(); $("[data-key-err]").textContent = "Thank you. Paste the key from your receipt email to unlock this browser."; }
    })
    .catch(function () { setState(false); });

  if (need) $("[data-need]").hidden = false;

  /* Locked file buttons open the buy choice instead of a redirect round trip. */
  page.addEventListener("click", function (e) {
    var a = e.target.closest(".dl-f, a.dl-b");
    if (!a || page.getAttribute("data-state") === "unlocked") return;
    e.preventDefault();
    need = a.getAttribute("href").replace(/^\/dl\//, "");
    $("[data-need]").hidden = false;
    $(".dl-hero").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  /* Shelf: one group per writer. Groups start closed (short on a phone) and
     open on wide screens; a search opens every group with a match and hides
     the rest, and clearing it puts the groups back. */
  var q = $("#dl-q"), rows = $$(".dl-w"), filter = "", count = $("[data-count]"), empty = $(".dl-empty");
  var groups = $$(".dl-g"), eras = $$(".dl-era"), searching = false;
  var wide = window.matchMedia ? window.matchMedia("(min-width: 761px)") : { matches: true };
  function openDefault() { groups.forEach(function (g) { g.open = wide.matches; }); }
  openDefault();
  function apply() {
    var words = (q.value || "").toLowerCase().split(/\s+/).filter(Boolean), shown = 0;
    rows.forEach(function (li) {
      var hay = li.getAttribute("data-q");
      var ok = words.every(function (w) { return hay.indexOf(w) >= 0; }) && (!filter || li.hasAttribute("data-" + filter));
      li.hidden = !ok;
      if (ok) shown++;
    });
    groups.forEach(function (g) {
      var any = Boolean(g.querySelector(".dl-w:not([hidden])"));
      g.hidden = !any;
      if (words.length) g.open = any;
    });
    if (searching && !words.length) openDefault();
    searching = words.length > 0;
    eras.forEach(function (e) { e.hidden = !e.querySelector(".dl-g:not([hidden])"); });
    count.textContent = shown === rows.length ? rows.length + " works" : shown + " of " + rows.length + " works";
    empty.hidden = shown > 0;
  }
  if (q) {
    q.addEventListener("input", apply);
    $$(".dl-chip").forEach(function (c) {
      c.addEventListener("click", function () {
        filter = c.getAttribute("data-filter");
        $$(".dl-chip").forEach(function (o) { o.setAttribute("aria-pressed", String(o === c)); });
        apply();
      });
    });
    apply();
  }

  /* Key entry. */
  var keyDialog = $("#dl-key-dialog");
  $$("[data-open-key]").forEach(function (b) { b.addEventListener("click", function () { keyDialog.showModal(); $("#dl-key").focus(); }); });
  var form = $("[data-key-form]");
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var err = $("[data-key-err]"), btn = form.querySelector("button");
    err.textContent = "";
    btn.disabled = true;
    post("/api/library/unlock", { key: form.key.value }).then(function (d) {
      btn.disabled = false;
      if (!d.ok) { err.textContent = d.reason || "That key did not work."; return; }
      keyDialog.close();
      setState(true, d.key_hint);
    }).catch(function () { btn.disabled = false; err.textContent = "Network trouble. Please try again."; });
  });

  $$("[data-signout]").forEach(function (b) {
    b.addEventListener("click", function () { post("/api/library/signout").then(function () { setState(false); }); });
  });

  /* Checkout: Lemon.js overlay; on success, unlock with the new order. */
  var welcome = $("#dl-welcome");
  function claim(order, tries) {
    var a = (order && (order.attributes || (order.data && order.data.attributes))) || {};
    var id = order && (order.id || (order.data && order.data.id));
    return post("/api/library/claim", { order_id: String(id || ""), identifier: a.identifier || "" }).then(function (d) {
      if (d.ok) {
        setState(true, d.key_hint);
        $("[data-welcome-key]").textContent = d.key;
        $("[data-welcome-mail]").textContent = d.email ? "We also emailed it to " + d.email + "." : "It is also in your receipt email.";
        if (window.LemonSqueezy && LemonSqueezy.Url) { try { LemonSqueezy.Url.Close(); } catch (e) { /* overlay may be gone */ } }
        welcome.showModal();
        return;
      }
      if (d.pending && tries < 15) return new Promise(function (r) { setTimeout(r, 2000); }).then(function () { return claim(order, tries + 1); });
      keyDialog.showModal();
      $("[data-key-err]").textContent = "Payment received. Enter the key from your receipt email to unlock.";
    });
  }
  $$("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var t = $("[data-welcome-key]").textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () { b.textContent = "Copied"; }, function () { b.textContent = "Select and copy"; });
    });
  });
  welcome.addEventListener("close", function () { $("#shelf").scrollIntoView({ behavior: "smooth" }); });

  var buy = $("[data-buy]");
  if (buy) {
    var s = document.createElement("script");
    s.src = "https://app.lemonsqueezy.com/js/lemon.js";
    s.defer = true;
    s.onload = function () {
      if (window.createLemonSqueezy) window.createLemonSqueezy();
      if (window.LemonSqueezy) LemonSqueezy.Setup({ eventHandler: function (ev) {
        if (ev && ev.event === "Checkout.Success") claim(ev.data && (ev.data.order || ev.data), 0);
      } });
    };
    document.head.appendChild(s);
  }
})();
