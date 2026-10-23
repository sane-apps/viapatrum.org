/* Downloads page (scripts/downloads_page.py): shelf search over the writer
   groups. Every file is a free download (2026-10-22); /dl/ links serve it
   directly. Without JS each writer group opens with a tap. */
(function () {
  var page = document.querySelector(".dl-page");
  if (!page) return;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

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
})();
