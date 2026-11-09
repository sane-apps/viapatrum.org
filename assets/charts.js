/* Charts (/charts/fathers/): zoom, and re-packing the rows so no label
   overlaps another at the chosen zoom. Without this script the chart still
   shows at its first zoom, packed by the build (scripts/charts_page.py). */
(function () {
  var chart = document.querySelector(".fc-chart");
  if (!chart) return;
  var scroller = chart.querySelector(".fc-scroll");
  var zooms = (chart.getAttribute("data-zooms") || "2.4").split(",").map(Number);
  var level = Number(chart.getAttribute("data-zoom")) || 0;
  var y0 = Number(getComputedStyle(chart).getPropertyValue("--y0")) || 50;
  var GAP = 12; // px between neighbours in a row

  var status = document.createElement("p");
  status.className = "vh";
  status.setAttribute("aria-live", "polite");
  chart.appendChild(status);

  // Label widths do not change with zoom: measure once.
  var lanes = Array.prototype.map.call(chart.querySelectorAll(".fc-lane"), function (lane) {
    var items = Array.prototype.map.call(lane.querySelectorAll(".fc-bar, .fc-council"), function (el) {
      var st = el.style;
      var label = 0;
      el.querySelectorAll(".fc-name, .fc-dates").forEach(function (s) { label = Math.max(label, s.getBoundingClientRect().width); });
      return {
        el: el,
        s: Number(st.getPropertyValue("--s")),
        e: Number(st.getPropertyValue("--e")),
        x0: Number(el.getAttribute("data-x0")),
        label: label
      };
    });
    items.sort(function (a, b) { return a.x0 - b.x0 || a.e - b.e; });
    return { el: lane, items: items };
  });

  function pack(px) {
    lanes.forEach(function (lane) {
      var ends = [];
      lane.items.forEach(function (it) {
        var left = (it.x0 - y0) * px;
        var right = Math.max((it.e - y0) * px, (it.s - y0) * px + it.label) + GAP;
        var row = 0;
        while (row < ends.length && left < ends[row]) row++;
        ends[row] = right;
        it.el.style.setProperty("--r", row);
      });
      lane.el.style.setProperty("--rows", Math.max(1, ends.length));
    });
  }

  var out = chart.querySelector('[data-zoom-step="-1"]');
  var inn = chart.querySelector('[data-zoom-step="1"]');

  function apply(next, announce) {
    var oldPx = zooms[level];
    // Keep the year in the middle of the box in the middle after the zoom.
    var mid = (scroller.scrollLeft + scroller.clientWidth / 2) / oldPx;
    level = Math.max(0, Math.min(zooms.length - 1, next));
    var px = zooms[level];
    chart.style.setProperty("--px", px + "px");
    chart.setAttribute("data-zoom", level);
    pack(px);
    scroller.scrollLeft = Math.max(0, mid * px - scroller.clientWidth / 2);
    out.disabled = level === 0;
    inn.disabled = level === zooms.length - 1;
    if (announce) status.textContent = "Zoom " + (level + 1) + " of " + zooms.length;
  }

  chart.querySelector(".fc-zoom").hidden = false;
  out.addEventListener("click", function () { apply(level - 1, true); });
  inn.addEventListener("click", function () { apply(level + 1, true); });
  // + and - zoom while the chart box has the focus.
  scroller.addEventListener("keydown", function (ev) {
    if (ev.target !== scroller || ev.altKey || ev.ctrlKey || ev.metaKey) return;
    if (ev.key === "+" || ev.key === "=") { apply(level + 1, true); ev.preventDefault(); }
    else if (ev.key === "-" || ev.key === "_") { apply(level - 1, true); ev.preventDefault(); }
  });
  // A phone starts one step further out, so a few centuries fit at once.
  if (scroller.clientWidth < 600 && level > 1) level = 1;
  apply(level, false);

  // "Read the chart as a list" opens the list it points to.
  function openList() {
    if (location.hash === "#fc-list") {
      var d = document.querySelector("#fc-list details");
      if (d) d.open = true;
    }
  }
  window.addEventListener("hashchange", openList);
  openList();
})();
