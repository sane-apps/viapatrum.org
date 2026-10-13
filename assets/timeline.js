/* Timeline (/explore/). The pages are static HTML (scripts/timeline_page.py);
   this adds search on the index, and on a question page the answer filter, the
   original-language toggle, the chart rail and the scroll-synced marks. */
(function () {
  var COLORS = ['var(--a1)', 'var(--a2)', 'var(--a3)', 'var(--a4)'];
  var SEG = [[30, 500, 0, .62], [500, 1500, .62, .75], [1500, 2030, .75, 1]];
  function T(y) { y = Math.max(30, Math.min(2030, y)); for (var i = 0; i < SEG.length; i++) { var s = SEG[i]; if (y <= s[1]) return s[2] + (y - s[0]) / (s[1] - s[0]) * (s[3] - s[2]); } return 1; }
  var ERAS = [[30, 150], [150, 325], [325, 451], [451, 1054], [1054, 1500], [1500, 1700], [1700, 2030]];
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function norm(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  var STOP = ['the', 'did', 'do', 'does', 'is', 'are', 'was', 'of', 'and', 'or', 'to', 'in', 'what', 'who', 'how', 'early', 'church', 'a', 'an', 'christians', 'believe', 'about', 'on', 'for', 'they', 'it', 'when', 'why'];

  /* ---------- index: search ---------- */
  function wireSearch() {
    var input = document.getElementById('q'), box = document.getElementById('results');
    if (!input || !box) return;
    var S = null, loading = null;
    function load() {
      if (S || loading) return loading;
      loading = fetch('/data/timeline-search.json').then(function (r) { return r.json(); }).then(function (j) { S = j; return j; });
      return loading;
    }
    function score(text, words) { var t = norm(text), s = 0; words.forEach(function (w) { if (t.indexOf(w) >= 0) s += w.length > 3 ? 2 : 1; }); return s; }
    function results(term) {
      var words = norm(term).split(/[^a-z0-9Ͱ-Ͽ]+/).filter(function (w) { return w.length > 1 && STOP.indexOf(w) < 0; });
      // Everyday words readers type, mapped to the words the questions use.
      var SYN = { babies: 'infant', baby: 'infant', kids: 'infant', children: 'infant', newborns: 'infant', communion: 'eucharist', mass: 'eucharist', bible: 'scripture', pope: 'rome', virgin: 'mary' };
      words = words.map(function (w) { return SYN[w] || w; });
      if (!words.length) return '';
      var qs = S.questions.map(function (q) { return { q: q, s: score(q.q + ' ' + q.s + ' ' + q.k, words) }; })
        .filter(function (x) { return x.s > 1; }).sort(function (a, b) { return b.s - a.s; }).slice(0, 7);
      var quotes = S.quotes.map(function (x) { return { x: x, s: score(x.who + ' ' + x.w + ' ' + x.e, words) }; })
        .filter(function (y) { return y.s > 0; }).sort(function (a, b) { return b.s - a.s; }).slice(0, 40).map(function (y) { return y.x; });
      var h = '';
      if (qs.length) h += '<h3>Questions</h3>' + qs.map(function (x, i) {
        return '<a class="r-q" role="option" href="/explore/' + esc(x.q.id) + '/"' + (i === 0 ? ' aria-selected="true"' : '') + '><span class="num">' + x.q.n + '</span><span class="t">' + esc(x.q.q) + '</span></a>';
      }).join('');
      if (quotes.length) {
        var short = {}; S.questions.forEach(function (q) { short[q.id] = q.s; });
        h += '<h3>Your words in the sources, over time</h3><div class="r-strip">' +
          [100, 300, 500, 1500, 2000].map(function (y) { return '<span class="tick" style="left:' + (T(y) * 100) + '%">' + y + '</span>'; }).join('') +
          quotes.map(function (x) { return '<a style="position:absolute;top:24px;width:12px;height:12px;margin-left:-6px;border-radius:50%;border:2px solid var(--leaf);left:' + (T(x.y) * 100) + '%;background:' + COLORS[x.a] + '" href="/explore/' + esc(x.q) + '/#w-' + esc(x.id) + '" title="' + esc(x.who + ', ' + x.y) + '" aria-label="' + esc(x.who + ', ' + x.y) + '"></a>'; }).join('') + '</div>' +
          quotes.slice(0, 5).map(function (x) { return '<a class="r-quote" href="/explore/' + esc(x.q) + '/#w-' + esc(x.id) + '"><b>' + esc(x.who) + '</b>, ' + (x.y < 1000 ? 'c. ' : '') + x.y + ' · ' + esc(short[x.q] || '') + '<br><i>' + esc(x.e.slice(0, 160)) + (x.e.length > 160 ? '…' : '') + '</i></a>'; }).join('');
      }
      return h || '<h3>Nothing yet</h3><p style="margin:.3rem .6rem">No question matches. Try a word such as baptism, Eucharist, canon, Mary, or a writer\'s name.</p>';
    }
    function show() {
      var t = input.value.trim(); if (!t) { box.hidden = true; return; }
      var p = load(); var run = function () { box.innerHTML = results(t); box.hidden = false; };
      if (S) run(); else if (p) p.then(run);
    }
    input.addEventListener('input', show);
    input.addEventListener('focus', function () { load(); show(); });
    input.addEventListener('keydown', function (e) {
      var opts = box.querySelectorAll('.r-q'), cur = box.querySelector('.r-q[aria-selected="true"]'), i = Array.prototype.indexOf.call(opts, cur);
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && opts.length) {
        e.preventDefault(); if (cur) cur.removeAttribute('aria-selected');
        i = (i + (e.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length; opts[i].setAttribute('aria-selected', 'true'); opts[i].scrollIntoView({ block: 'nearest' });
      }
      if (e.key === 'Enter' && cur) { e.preventDefault(); location.href = cur.getAttribute('href'); }
      if (e.key === 'Escape') { box.hidden = true; input.blur(); }
    });
    document.addEventListener('click', function (e) { if (!document.getElementById('searchbox').contains(e.target)) box.hidden = true; });
    document.addEventListener('keydown', function (e) { if (e.key === '/' && !(e.target.matches && e.target.matches('input,textarea'))) { e.preventDefault(); input.focus(); } });
  }

  /* ---------- question page ---------- */
  function wireQuestion() {
    var el = document.getElementById('tl-data'); if (!el) return;
    var D = JSON.parse(el.textContent), RAIL = null, filter = null;
    var byId = {}; D.quotes.forEach(function (q) { byId[q.id] = q; });
    var cards = Array.prototype.slice.call(document.querySelectorAll('.tl .card'));
    function drawRail() {
      var box = document.getElementById('railbox'); if (!box || !box.offsetParent) return;
      var W = Math.max(180, box.clientWidth), H = Math.max(320, box.parentNode.clientHeight - 28), top = 26, bot = 14;
      function Y(y) { return top + T(y) * (H - top - bot); }
      RAIL = { Y: Y };
      var parts = [], lanes = D.answers.length, left = 44, laneW = (W - left - 4) / lanes;
      ERAS.forEach(function (e, i) { if (i % 2 === 0) parts.push('<rect class="eb" x="' + (left - 4) + '" y="' + Y(e[0]) + '" width="' + (W - left + 4) + '" height="' + (Y(e[1]) - Y(e[0])) + '"/>'); });
      parts.push('<line class="ax" x1="' + (left - 4) + '" x2="' + (left - 4) + '" y1="' + top + '" y2="' + (H - bot) + '"/>');
      [100, 200, 300, 400, 500, 1000, 1500, 1800, 2000].forEach(function (y) { parts.push('<text class="yt" x="' + (left - 9) + '" y="' + (Y(y) + 3.5) + '" text-anchor="end">' + y + '</text>'); });
      D.tags.forEach(function (t, i) { parts.push('<text class="rname" x="' + (left + laneW * i + laneW / 2) + '" y="12" text-anchor="middle">' + esc(t) + '</text>'); });
      var placed = [], life = {};
      D.quotes.forEach(function (q) {
        var cy = Y(q.y), cx = left + laneW * q.a + laneW / 2, k = 0, tries = [0, 9, -9, 18, -18, 27, -27];
        while (k < tries.length && placed.some(function (p) { return Math.abs(p[0] - (cx + tries[k])) < 10 && Math.abs(p[1] - cy) < 10; })) k++;
        cx += tries[Math.min(k, tries.length - 1)]; placed.push([cx, cy]);
        if (q.x && q.b && !life[q.who]) { life[q.who] = 1; parts.push('<line class="life" x1="' + (cx - 8) + '" x2="' + (cx - 8) + '" y1="' + Y(q.b) + '" y2="' + Y(q.x) + '"><title>' + esc(q.who + ', ' + q.b + '–' + q.x) + '</title></line>'); }
        var c = COLORS[q.a], cls = 'rdot' + (q.ind ? ' ind' : ''), t = '<title>' + esc(q.who + ', ' + q.d) + '</title>';
        parts.push(q.conf ? '<rect class="' + cls + '" data-jump="' + esc(q.id) + '" x="' + (cx - 5) + '" y="' + (cy - 5) + '" width="10" height="10" transform="rotate(45 ' + cx + ' ' + cy + ')" style="fill:' + c + '">' + t + '</rect>'
          : '<circle class="' + cls + '" data-jump="' + esc(q.id) + '" cx="' + cx + '" cy="' + cy + '" r="5.5" style="fill:' + c + (q.ind ? ';stroke:' + c : '') + '">' + t + '</circle>');
      });
      parts.push('<rect class="view" id="rview" x="' + (left - 2) + '" y="0" width="' + (W - left + 2) + '" height="0" rx="4"/>');
      box.innerHTML = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Chart of every witness by year and answer">' + parts.join('') + '</svg>';
      if (filter) applyFilter();
    }
    function setActive(id) {
      document.querySelectorAll('.tl .g-dot.on, .tl .rdot.on, .tl .card.on').forEach(function (e) { e.classList.remove('on'); });
      document.querySelectorAll('.tl [data-jump="' + id + '"]').forEach(function (e) { if (e.classList.contains('g-dot') || e.classList.contains('rdot')) e.classList.add('on'); });
      var c = document.getElementById('w-' + id); if (c) c.classList.add('on');
    }
    function jump(id) { var c = document.getElementById('w-' + id); if (c) { if (c.classList.contains('hide')) { filter = null; applyFilter(); } c.scrollIntoView({ block: 'start' }); setActive(id); history.replaceState(null, '', '#w-' + id); } }
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) setActive(e.target.id.slice(2)); }); }, { rootMargin: '-40% 0px -55% 0px' });
      cards.forEach(function (c) { io.observe(c); });
    }
    function viewBand() {
      var vis = cards.filter(function (c) { if (c.classList.contains('hide')) return false; var r = c.getBoundingClientRect(); return r.bottom > 110 && r.top < window.innerHeight; });
      var gv = document.getElementById('gview'), rv = document.getElementById('rview');
      if (!vis.length) { if (gv) gv.style.width = '0'; if (rv) rv.setAttribute('height', 0); return; }
      var y0 = +vis[0].getAttribute('data-y'), y1 = +vis[vis.length - 1].getAttribute('data-y');
      if (gv) { var a = T(y0), b = T(y1); gv.style.left = 'calc(' + (a * 100) + '% - 9px)'; gv.style.width = 'calc(' + ((b - a) * 100) + '% + 18px)'; }
      if (rv && RAIL) { var t = RAIL.Y(y0) - 9, bo = RAIL.Y(y1) + 9; rv.setAttribute('y', t); rv.setAttribute('height', Math.max(18, bo - t)); }
    }
    function applyFilter() {
      document.querySelectorAll('.tl .ans').forEach(function (b) { var on = b.getAttribute('data-ans') === filter; b.setAttribute('aria-pressed', String(on)); b.classList.toggle('dim', !!filter && !on); });
      cards.forEach(function (c) { c.classList.toggle('hide', !!filter && c.getAttribute('data-a') !== filter); });
      var fi = filter ? D.answers.indexOf(filter) : -1;
      document.querySelectorAll('.tl .g-dot, .tl .rdot').forEach(function (dot) { var q = byId[dot.getAttribute('data-jump')]; dot.classList.toggle('hide', fi >= 0 && q && q.a !== fi); });
      viewBand();
    }
    var raf = 0;
    window.addEventListener('scroll', function () { if (!raf) raf = requestAnimationFrame(function () { raf = 0; viewBand(); }); }, { passive: true });
    window.addEventListener('resize', function () { drawRail(); viewBand(); });
    document.addEventListener('click', function (e) {
      var j = e.target.closest('[data-jump]'); if (j) { e.preventDefault(); jump(j.getAttribute('data-jump')); return; }
      var o = e.target.closest('[data-orig]');
      if (o) { var box = document.getElementById('o-' + o.getAttribute('data-orig')), open = box.hidden; box.hidden = !open; o.setAttribute('aria-expanded', String(open)); o.textContent = (open ? 'Hide' : 'Show') + o.textContent.slice(4); return; }
      var a = e.target.closest('[data-ans]'); if (a) { var id = a.getAttribute('data-ans'); filter = filter === id ? null : id; applyFilter(); }
    });
    document.addEventListener('keydown', function (e) {
      if (e.target.matches && e.target.matches('input,textarea') || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key !== 'j' && e.key !== 'k') return;
      var vis = cards.filter(function (c) { return !c.classList.contains('hide'); }); if (!vis.length) return;
      var cur = document.querySelector('.tl .card.on'), i = vis.indexOf(cur);
      jump(vis[Math.max(0, Math.min(vis.length - 1, i + (e.key === 'j' ? 1 : -1)))].id.slice(2)); e.preventDefault();
    });
    drawRail(); viewBand();
    var h = location.hash.slice(1); if (h.indexOf('w-') === 0) setTimeout(function () { jump(h.slice(2)); }, 60);
  }

  /* The chart strip sticks just under the site header when that header stays on screen. */
  function headerTop() {
    var h = document.querySelector('body > header, header.site-header, .site-header'); var top = 0;
    if (h) { var cs = getComputedStyle(h); if (cs.position === 'sticky' || cs.position === 'fixed') top = h.getBoundingClientRect().height; }
    document.documentElement.style.setProperty('--tl-top', top + 'px');
  }
  headerTop(); window.addEventListener('resize', headerTop);
  if (document.getElementById('tl-index')) wireSearch();
  if (document.getElementById('tl-q')) wireQuestion();
})();
