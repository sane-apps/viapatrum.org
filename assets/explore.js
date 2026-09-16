(() => {
  const root = document.querySelector("[data-explore]");
  if (!root) return;
  document.body.classList.add("explore-mode");

  const els = {
    chrome: root.querySelector(".explore-chrome"),
    filtersToggle: root.querySelector("#explore-filters-toggle"),
    topic: root.querySelector("#explore-topic"),
    era: root.querySelector("#explore-era"),
    author: root.querySelector("#explore-author"),
    compareAdd: root.querySelector("#explore-compare-add"),
    chips: root.querySelector("#explore-chips"),
    zoomCentury: root.querySelector("#zoom-century"),
    zoomYear: root.querySelector("#zoom-year"),
    canvas: root.querySelector("#explore-canvas"),
    tip: root.querySelector("#explore-tip"),
    tipBody: root.querySelector("#explore-tip-body"),
    tipToggle: root.querySelector("#explore-tip-toggle"),
    drawer: root.querySelector("#explore-drawer"),
    tooltip: root.querySelector("#explore-tooltip"),
    pathGrid: root.querySelector("#explore-path-grid"),
  };

  let data = null;
  let zoom = "year";
  let activeId = null;
  let compare = [];
  let displayCache = [];
  let pointsCache = [];
  let animateNextDraw = true; // entrance animation only on data/filter changes, not resizes

  const LANE = ["#1f5c45", "#9a6b2f", "#4a5568", "#6b3a4a"];

  // One color per writer. Dark, saturated inks that stay distinct on the cream
  // stage; ordered so writers close in time get strongly different hues.
  const AUTHOR_COLORS = [
    "#146650", // deep green
    "#a63d2f", // brick
    "#2f5b9e", // cobalt
    "#b4690e", // ochre
    "#7b4397", // violet
    "#17707f", // teal
    "#a83a72", // magenta
    "#5a6b21", // olive
    "#545299", // indigo
    "#8a2d4f", // raspberry
    "#3e7d3a", // leaf green
    "#7d4a2f", // sienna
    "#266a93", // steel blue
    "#b13d51", // rose
    "#6e4f0f", // dark mustard
    "#41586b", // slate
    "#8c5a86", // plum
  ];
  let authorColorCache = { topic: null, map: {} };

  function authorColors(topicId) {
    if (authorColorCache.topic === topicId) return authorColorCache.map;
    const first = new Map();
    for (const p of data.points) {
      if (p.topic !== topicId) continue;
      const y = p.year || 0;
      if (!first.has(p.author_slug) || y < first.get(p.author_slug)) first.set(p.author_slug, y);
    }
    const ordered = [...first.entries()].sort((a, b) => a[1] - b[1]).map(([s]) => s);
    const map = {};
    ordered.forEach((s, i) => (map[s] = AUTHOR_COLORS[i % AUTHOR_COLORS.length]));
    authorColorCache = { topic: topicId, map };
    return map;
  }

  fetch("/data/explore-index.json")
    .then((r) => { if (!r.ok) throw new Error("Explore unavailable"); return r.json(); })
    .then((json) => {
      data = json;
      // Prefer short labels from source claims if rebuild hasn't landed yet
      fillFilters();
      renderPaths();
      const params = new URLSearchParams(location.search);
      if (params.get("topic") && [...els.topic.options].some((o) => o.value === params.get("topic"))) {
        els.topic.value = params.get("topic");
      }
      if ([...els.author.options].some(o => o.value === params.get("author"))) {
        els.author.value = params.get("author");
      }
      if ([...els.era.options].some(o => o.value === params.get("era"))) els.era.value = params.get("era");
      if (params.get("zoom") === "century") zoom = "century";
      const cmp = (params.get("compare") || "").split(",").filter(Boolean);
      compare = [...new Set(cmp)].filter(slug => data.authors.some(a => a.slug === slug)).slice(0, 3);
      syncZoom();
      fillCompareAdd();
      renderChips();
      render();
      showEmptyDrawer();
    })
    .catch(() => {
      els.drawer.innerHTML = "<p class='empty'>Explore index unavailable.</p>";
      if (els.pathGrid) els.pathGrid.innerHTML = "<p class='empty'>Paths unavailable.</p>";
    });

  const PATH_KIND = {
    doctrine: "Doctrine",
    controversy: "Controversy",
    scripture: "Scripture",
    era: "Era bands",
    rupture: "First appearance",
    reading: "Reading path",
  };

  function renderPaths() {
    if (!els.pathGrid) return;
    const paths = Array.isArray(data.paths) ? data.paths : [];
    if (!paths.length) {
      els.pathGrid.innerHTML = "<p class='empty'>No curated paths yet.</p>";
      return;
    }
    const order = ["doctrine", "controversy", "scripture", "era", "rupture", "reading"];
    const sorted = [...paths].sort((a, b) => {
      const ka = order.indexOf(a.kind);
      const kb = order.indexOf(b.kind);
      return (ka < 0 ? 99 : ka) - (kb < 0 ? 99 : kb) || String(a.title || "").localeCompare(String(b.title || ""), undefined, { sensitivity: "base" });
    });
    els.pathGrid.innerHTML = sorted
      .map((p) => {
        const status = p.status || "live";
        const statusLabel =
          status === "live" ? "In corpus" : status === "partial" ? "Partial — corpus thin" : "Stub — backlog";
        const links = (p.links || [])
          .slice(0, 3)
          .map((l) => `<li><a href="${escAttr(l.href)}">${esc(l.label)}</a></li>`)
          .join("");
        const backlog = p.backlog_note
          ? `<p class="path-summary">${esc(p.backlog_note)}</p>`
          : "";
        return `<article class="explore-path-card" data-status="${escAttr(status)}" data-path="${escAttr(p.id)}" data-topic="${escAttr(p.explore_topic || "")}" tabindex="0" role="button">
          <span class="path-kind">${esc(PATH_KIND[p.kind] || p.kind || "Path")}</span>
          <h3 class="path-title">${esc(p.title)}</h3>
          <p class="path-summary">${esc(p.summary || "")}</p>
          ${backlog}
          <span class="path-status">${esc(statusLabel)}</span>
          <ul class="path-links">${links}</ul>
        </article>`;
      })
      .join("");

    els.pathGrid.querySelectorAll(".explore-path-card").forEach((card) => {
      const activate = (ev) => {
        if (ev.target.closest("a")) return;
        const topic = card.getAttribute("data-topic");
        if (topic && els.topic && [...els.topic.options].some((o) => o.value === topic)) {
          els.topic.value = topic;
          fillCompareAdd();
          renderChips();
          animateNextDraw = true;
          render();
          showEmptyDrawer();
          els.chrome?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
        } else {
          const first = card.querySelector(".path-links a");
          if (first) first.click();
        }
      };
      card.addEventListener("click", activate);
      card.addEventListener("keydown", (ev) => {
        if (ev.target !== card) return;
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          activate(ev);
        }
      });
    });
  }

  const ro = new ResizeObserver(() => {
    if (data) render(false);
  });
  ro.observe(els.canvas);

  function fillFilters() {
    els.topic.innerHTML = data.topics
      .map((t) => `<option value="${escAttr(t.id)}">${esc(t.title)}</option>`)
      .join("");
    els.era.innerHTML = ["all", ...data.eras]
      .map((e) => `<option value="${escAttr(e)}">${e === "all" ? "All eras" : esc(e)}</option>`)
      .join("");
    els.author.innerHTML = [{ slug: "all", name: "All authors", dates: "" }, ...data.authors]
      .map((a) => {
        const label = a.dates ? `${a.name} (${a.dates})` : a.name;
        return `<option value="${escAttr(a.slug)}">${esc(label)}</option>`;
      })
      .join("");
  }

  function fillCompareAdd() {
    const topic = els.topic.value;
    const onTopic = new Map();
    for (const p of data.points) {
      if (p.topic === topic) onTopic.set(p.author_slug, p.author);
    }
    const opts = [...onTopic.entries()]
      .sort((a, b) => a[1].localeCompare(b[1]))
      .filter(([slug]) => !compare.includes(slug));
    els.compareAdd.innerHTML =
      `<option value="">Compare…</option>` +
      opts.map(([slug, name]) => `<option value="${escAttr(slug)}">${esc(name)}</option>`).join("");
  }

  function renderChips() {
    const aColors = authorColors(els.topic.value);
    els.chips.innerHTML = compare
      .map((slug) => {
        const a = data.authors.find((x) => x.slug === slug);
        const name = a ? a.name : slug;
        const dates = a && a.dates ? a.dates : "";
        const label = dates ? `${name} (${dates})` : name;
        const c = aColors[slug] || "#1f5c45";
        return `<span class="explore-chip" style="color:${c};border-color:color-mix(in srgb, ${c} 45%, transparent);background:color-mix(in srgb, ${c} 10%, #fff)">${esc(label)} <button type="button" data-remove="${escAttr(slug)}" aria-label="Remove ${escAttr(name)}">×</button></span>`;
      })
      .join("");
  }

  function filteredPoints() {
    const topic = els.topic.value;
    const era = els.era.value;
    const author = els.author.value;
    return data.points.filter((p) => {
      if (p.topic !== topic) return false;
      if (era !== "all" && p.era_band !== era) return false;
      if (compare.length) return compare.includes(p.author_slug);
      if (author !== "all" && p.author_slug !== author) return false;
      return true;
    });
  }

  function topicMeta() {
    return data.topics.find((t) => t.id === els.topic.value) || data.topics[0];
  }

  function shortClaim(c) {
    return c.short || c.label.split(/[—–-]/)[0].trim().slice(0, 22);
  }

  function syncZoom() {
    els.zoomCentury.setAttribute("aria-pressed", String(zoom === "century"));
    els.zoomYear.setAttribute("aria-pressed", String(zoom === "year"));
    els.zoomCentury.classList.toggle("is-active", zoom === "century");
    els.zoomYear.classList.toggle("is-active", zoom === "year");
  }

  function aggregateByCentury(points) {
    const buckets = new Map();
    for (const p of points) {
      const c = p.century || Math.floor((p.year || 0) / 100) * 100;
      const key = `${c}|${p.claim_id}|${p.author_slug}|${p.kind}`;
      if (!buckets.has(key)) {
        buckets.set(key, {
          id: `bucket-${key}`,
          kind: "bucket",
          century: c,
          year: c + 50,
          claim_id: p.claim_id,
          stance: p.stance,
          author: p.author,
          author_slug: p.author_slug,
          topic: p.topic,
          title: `${p.author} · ${c}s`,
          count: 0,
          children: [],
          href: null,
        });
      }
      const b = buckets.get(key);
      b.count += 1;
      b.children.push(p);
    }
    return [...buckets.values()];
  }

  function fitStage() {
    const header = document.querySelector(".site-header");
    const chrome = root.querySelector(".explore-chrome");
    const tip = els.tip;
    const used =
      (header ? header.getBoundingClientRect().height : 56) +
      (chrome ? chrome.getBoundingClientRect().height : 56) +
      (!tip.hidden ? tip.getBoundingClientRect().height : 0);
    const stage = root.querySelector(".explore-stage");
    if (stage) stage.style.height = `${Math.max(280, window.innerHeight - used)}px`;
  }

  function render(updateTip = true) {
    const topic = topicMeta();
    const points = filteredPoints();
    pointsCache = points;
    const mode = zoom === "century" ? "century" : "year";
    const display = mode === "century" && points.length > 14 ? aggregateByCentury(points) : mode === "century" ? aggregateByCentury(points) : points;
    displayCache = display;
    if (activeId && !display.some(p => p.id === activeId)) { activeId = null; showEmptyDrawer(); }

    if (updateTip) {
      const rupture = (data.ruptures || []).find((r) => r.topic === topic.id);
      if (rupture) {
        els.tip.hidden = false;
        els.tip.querySelector(".tip-title").textContent = rupture.title;
        els.tipBody.textContent = rupture.body;
      } else {
        els.tip.hidden = true;
      }
    }
    fitStage();
    drawSvg(topic, display, points);
    updateUrl();
  }

  function drawSvg(topic, display, rawPoints) {
    const claims = topic.claims || [];
    const claimIndex = Object.fromEntries(claims.map((c, i) => [c.id, i]));
    const rect = els.canvas.getBoundingClientRect();
    const W = Math.max(320, Math.floor(rect.width) || 900);
    const H = Math.max(280, Math.min(Math.floor(rect.height) || 420, window.innerHeight));
    const padL = 16;
    const padR = 28;
    const padT = 52;
    const padB = 44;
    const laneH = (H - padT - padB) / Math.max(claims.length, 1);
    const compact = W < 640;
    const rDot = compact ? 7 : 10;
    const dotStroke = compact ? 1.8 : 2.5;
    // Reserve room at the top of each lane for its label so dots never cover it.
    let labelZone = compact ? 18 : 26;
    if (laneH - labelZone < 24) labelZone = Math.max(0, laneH - 24);

    const years = display.map((p) => p.year).filter(Boolean);
    let y0 = years.length ? Math.min(...years) : 100;
    let y1 = years.length ? Math.max(...years) : 450;
    const padY = Math.max(40, (y1 - y0) * 0.08);
    y0 -= padY;
    y1 += padY;

    const xScale = (y) => padL + ((y - y0) / (y1 - y0 || 1)) * (W - padL - padR);
    const laneY = (claimId) => {
      const i = claimIndex[claimId] ?? 0;
      return padT + laneH * i + labelZone + (laneH - labelZone) / 2;
    };

    const ticks = [];
    for (let c = Math.ceil(y0 / 50) * 50; c <= y1; c += 50) ticks.push(c);

    // Rupture marker: first contrast or post-Nicene point year
    const ruptureYear = rawPoints
      .filter((p) => p.kind === "contrast" || (p.year && p.year >= 390))
      .map((p) => p.year)
      .sort((a, b) => a - b)[0];

    const aColors = authorColors(topic.id);

    // Resolve overlaps: nudge same-lane neighbors vertically (mini beeswarm).
    const maxOff = Math.max(0, (laneH - labelZone) / 2 - rDot - 3);
    const lanesPlaced = new Map();
    const pos = new Map();
    const orderedPts = [...display].sort((a, b) => (a.year || 0) - (b.year || 0));
    for (const p of orderedPts) {
      const x = xScale(p.year);
      const rad =
        p.kind === "bucket"
          ? Math.min(compact ? 14 : 18, 8 + p.count * 1.5)
          : p.kind === "contrast"
            ? (compact ? 9 : 12)
            : rDot;
      if (!lanesPlaced.has(p.claim_id)) lanesPlaced.set(p.claim_id, []);
      const placed = lanesPlaced.get(p.claim_id);
      let off = 0;
      for (const cand of [0, ...Array.from({length: Math.floor(maxOff)}, (_, i) => i + 1).flatMap(n => [n, -n])]) {
        const collides = placed.some(
          (q) => Math.hypot(q.x - x, q.off - cand) < q.rad + rad + 2
        );
        off = cand;
        if (!collides) break;
      }
      placed.push({ x, off, rad });
      pos.set(p.id, { x, y: laneY(p.claim_id) + off, rad });
    }

    let html = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Topic timeline">`;
    html += `<defs>
      <filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="1.2" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>`;

    claims.forEach((c, i) => {
      const top = padT + laneH * i;
      const color = LANE[i % LANE.length];
      const midY = top + labelZone + (laneH - labelZone) / 2;
      html += `<rect x="0" y="${top}" width="${W}" height="${laneH}" fill="${color}" fill-opacity="${i % 2 ? 0.06 : 0.09}"/>`;
      html += `<text x="${padL + 8}" y="${top + (compact ? 14 : 19)}" font-family="Fraunces, Georgia, serif" font-size="${compact ? 12.5 : 15}" font-weight="650" fill="${color}" stroke="var(--stage)" stroke-width="3.5" paint-order="stroke" stroke-linejoin="round">${esc(shortClaim(c))}</text>`;
      html += `<line x1="${padL}" x2="${W - padR}" y1="${midY}" y2="${midY}" stroke="${color}" stroke-opacity="0.25" stroke-width="1.5"/>`;
    });

    ticks.forEach((t) => {
      const x = xScale(t);
      const major = t % 100 === 0;
      html += `<line x1="${x}" x2="${x}" y1="${padT}" y2="${H - padB}" stroke="#d5cbb6" stroke-opacity="${major ? 0.9 : 0.35}" stroke-dasharray="${major ? "0" : "3 5"}"/>`;
      if (major || (y1 - y0 < 220 && t % 50 === 0)) {
        html += `<text x="${x}" y="${H - 16}" text-anchor="middle" font-size="12" fill="var(--ink)" font-family="Source Sans 3, system-ui, sans-serif">${t}</text>`;
      }
    });

    if (ruptureYear) {
      const rx = xScale(ruptureYear);
      html += `<line x1="${rx}" x2="${rx}" y1="${padT - 8}" y2="${H - padB + 4}" stroke="#8a6a2f" stroke-width="2" stroke-dasharray="5 6" stroke-opacity="0.85"/>`;
      html += `<text x="${Math.min(rx + 6, W - padR)}" text-anchor="${rx > W - 100 ? "end" : "start"}" y="${padT - 14}" font-size="${compact ? 10 : 11}" fill="#6b5224" font-weight="650" font-family="Source Sans 3, system-ui, sans-serif">${compact ? "break →" : "later break →"}</text>`;
    }

    // Soft river through the first claim lane (earlier consensus)
    if (claims.length) {
      const mainClaim = claims[0].id;
      const river = display
        .filter((p) => p.claim_id === mainClaim && p.kind !== "bucket")
        .sort((a, b) => (a.year || 0) - (b.year || 0));
      if (river.length >= 2) {
        const pts = river.map((p) => [xScale(p.year), laneY(p.claim_id)]);
        let d = `M ${pts[0][0]} ${pts[0][1]}`;
        for (let i = 1; i < pts.length; i++) {
          const [x0, y0] = pts[i - 1];
          const [x1, y1] = pts[i];
          const mx = (x0 + x1) / 2;
          d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
        }
        html += `<path d="${d}" fill="none" stroke="${LANE[0]}" stroke-opacity="0.35" stroke-width="3" stroke-linecap="round"/>`;
      }
    }

    display.forEach((p, idx) => {
      const placed = pos.get(p.id) || { x: xScale(p.year), y: laneY(p.claim_id), rad: rDot };
      const x = placed.x;
      const y = placed.y;
      const ci = claimIndex[p.claim_id] ?? 0;
      const color = p.kind === "contrast" ? "#8a6a2f" : aColors[p.author_slug] || LANE[ci % LANE.length];
      const isContrast = p.kind === "contrast";
      const isBucket = p.kind === "bucket";
      const dim = compare.length > 0 && !compare.includes(p.author_slug) && p.kind !== "bucket";
      const active = activeId === p.id;
      const cls = `explore-point${active ? " is-active" : ""}${dim ? " is-dim" : ""}${isContrast ? " is-pulse" : ""}`;
      const label = isBucket ? `${p.author} (${p.count})` : `${p.author}`;
      const delay = Math.min(idx * 0.03, 0.6);
      const animStyle = animateNextDraw && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? `animation: fadeUp 0.5s ease ${delay}s both` : "";
      const hit = `<circle cx="${x}" cy="${y}" r="${placed.rad + (compact ? 9 : 6)}" fill="transparent" stroke="none"/>`;
      if (isContrast) {
        const s = placed.rad;
        html += `<g class="${cls}" tabindex="0" data-id="${escAttr(p.id)}" data-label="${escAttr(label)}" data-sub="${escAttr(p.title || "Contrast")}" role="button" aria-label="${escAttr(label + ": " + (p.title || p.stance || "passages"))}" style="${animStyle}">
          ${hit}
          <rect class="diamond" x="${x - s}" y="${y - s}" width="${s * 2}" height="${s * 2}" transform="rotate(45 ${x} ${y})" fill="${color}" stroke="#fff" stroke-width="${dotStroke}" filter="url(#soft)"/>
        </g>`;
      } else if (isBucket) {
        const r = placed.rad;
        html += `<g class="${cls}" tabindex="0" data-id="${escAttr(p.id)}" data-label="${escAttr(label)}" data-sub="${escAttr(p.count + " texts")}" role="button" aria-label="${escAttr(label + ": " + (p.title || p.stance || "passages"))}" style="${animStyle}">
          ${hit}
          <circle cx="${x}" cy="${y}" r="${r}" fill="${color}" stroke="#fff" stroke-width="2" filter="url(#soft)"/>
          <text x="${x}" y="${y + 4}" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">${p.count}</text>
        </g>`;
      } else {
        html += `<g class="${cls}" tabindex="0" data-id="${escAttr(p.id)}" data-label="${escAttr(label)}" data-sub="${escAttr((p.year || "") + " · " + (p.stance || ""))}" role="button" aria-label="${escAttr(label + ": " + (p.title || p.stance || "passages"))}" style="${animStyle}">
          ${hit}
          <circle cx="${x}" cy="${y}" r="${placed.rad}" fill="${color}" stroke="#fff" stroke-width="${dotStroke}" filter="url(#soft)"/>
        </g>`;
      }
    });

    html += `</svg>`;
    // Keep tooltip node
    const tip = els.tooltip;
    els.canvas.querySelectorAll("svg").forEach((n) => n.remove());
    els.canvas.insertAdjacentHTML("afterbegin", html);

    els.canvas.querySelectorAll(".explore-point").forEach((g) => {
      const open = () => { hideTip(); selectPoint(g.getAttribute("data-id")); };
      g.addEventListener("click", open);
      g.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });
      g.addEventListener("pointerenter", (e) => showTip(e, g));
      g.addEventListener("pointermove", (e) => moveTip(e));
      g.addEventListener("pointerleave", hideTip);
    });

    if (!display.length) {
      els.drawer.innerHTML =
        "<p class='empty'>Nothing on this filter yet. Pick another topic, era, or clear compare chips.</p>";
    }
    animateNextDraw = false;
  }

  function showTip(e, g) {
    if (e.pointerType === "touch") return;
    els.tooltip.innerHTML = `${esc(g.getAttribute("data-label") || "")}<small>${esc(g.getAttribute("data-sub") || "")}</small>`;
    els.tooltip.classList.add("is-on");
    moveTip(e);
  }
  function moveTip(e) {
    const box = els.canvas.getBoundingClientRect();
    const x = e.clientX - box.left + 12;
    const y = e.clientY - box.top + 12;
    const tip = els.tooltip.getBoundingClientRect();
    els.tooltip.style.left = `${Math.max(8, Math.min(x, box.width - tip.width - 8))}px`;
    els.tooltip.style.top = `${Math.max(8, Math.min(y, box.height - tip.height - 8))}px`;
  }
  function hideTip() {
    els.tooltip.classList.remove("is-on");
  }

  function showEmptyDrawer() {
    const topic = topicMeta();
    const aColors = authorColors(topic.id);
    const seen = new Map();
    filteredPoints()
      .filter((p) => p.kind !== "contrast")
      .sort((a, b) => (a.year || 0) - (b.year || 0))
      .forEach((p) => {
        if (!seen.has(p.author_slug)) seen.set(p.author_slug, p.author);
      });
    const authorKeys = [...seen]
      .map(
        ([slug, name]) =>
          `<li><i style="background:${aColors[slug] || LANE[0]}"></i><span>${esc(name)}</span></li>`
      )
      .join("");
    const claimKeys = (topic.claims || [])
      .map(
        (c, i) =>
          `<li><i class="lane-swatch" style="background:${LANE[i % LANE.length]}"></i><span><strong>${esc(shortClaim(c))}</strong> — ${esc(c.label)}</span></li>`
      )
      .join("");
    els.drawer.innerHTML = `
      <p class="empty">Each color is one writer. Tap or hover a point for the name; click to read the passage.</p>
      <div class="lane-key"><h3 class="drawer-label">Writers, earliest first</h3><ul>${authorKeys}</ul></div>
      <div class="lane-key"><h3 class="drawer-label">Rows (claims)</h3><ul>${claimKeys}
      <li><i class="diamond" style="background:#8a6a2f"></i><span>Diamond — contrast card (full works forthcoming)</span></li>
      </ul></div>`;
  }

  function selectPoint(id) {
    activeId = id;
    const topic = topicMeta();
    const point =
      displayCache.find((x) => x.id === id) || pointsCache.find((x) => x.id === id);
    if (!point) return;

    els.canvas.querySelectorAll(".explore-point").forEach((g) => {
      g.classList.toggle("is-active", g.getAttribute("data-id") === id);
    });

    if (point.kind === "bucket") {
      const kids = point.children
        .map(
          (c) =>
            `<li><a href="${escAttr(c.href || "#")}">${esc(c.title || c.citation || c.id)}</a>
            <span class="meta">${esc(c.author)} · ${esc(c.stance)}</span></li>`
        )
        .join("");
      els.drawer.innerHTML = `
        <p class="badge-kind">Century · ${point.century}s</p>
        <h2>${esc(point.author)}</h2>
        <p class="meta">${point.count} texts · ${esc(claimLabel(topic, point.claim_id))}</p>
        <ul class="card-list">${kids}</ul>
        <p><button type="button" class="btn" id="expand-years">Expand to years</button></p>`;
      els.drawer.querySelector("#expand-years")?.addEventListener("click", () => {
        zoom = "year";
        syncZoom();
        render();
      });
      return;
    }

    const kindBadge =
      point.kind === "contrast" ? "Contrast card" : point.kind === "work" ? "Work section" : "Topic excerpt";
    const link = point.href
      ? `<div class="drawer-actions"><a class="btn primary" href="${escAttr(point.href)}">Open full text →</a></div>`
      : "";
    const preview = point.summary || point.snippet || "";
    const previewLabel = point.kind === "contrast" ? "Summary" : "Excerpt preview";
    const previewBlock = preview
      ? `<section class="drawer-block">
          <h3 class="drawer-label">${esc(previewLabel)}</h3>
          <p class="drawer-excerpt">${esc(preview)}</p>
        </section>`
      : "";
    const noteBlock = point.note
      ? `<section class="drawer-block drawer-note">
          <h3 class="drawer-label">Editorial note</h3>
          <p>${esc(point.note)}</p>
        </section>`
      : "";
    const disclaimerBlock = point.disclaimer
      ? `<section class="drawer-block drawer-disclaimer">
          <h3 class="drawer-label">About this card</h3>
          <p>${esc(point.disclaimer)}</p>
        </section>`
      : "";
    els.drawer.innerHTML = `
      <p class="badge-kind">${esc(kindBadge)}</p>
      <h2>${esc(point.title || point.citation || point.id)}</h2>
      <p class="meta">${esc(point.author)} · ${esc(point.period || String(point.year || ""))} · ${esc(point.era_band || "")}</p>
      <p class="stance-pill"><span>${esc(point.stance)}</span><span>${esc(claimLabel(topic, point.claim_id))}</span></p>
      ${previewBlock}
      ${noteBlock}
      ${disclaimerBlock}
      ${link}`;
  }

  function claimLabel(topic, claimId) {
    const c = (topic.claims || []).find((x) => x.id === claimId);
    return c ? shortClaim(c) : claimId;
  }

  function syncFiltersToggle() {
    if (!els.filtersToggle) return;
    const active = els.era.value !== "all" || els.author.value !== "all" || compare.length > 0;
    els.filtersToggle.classList.toggle("has-active", active);
  }

  function updateUrl() {
    syncFiltersToggle();
    const url = new URL(location.href);
    url.searchParams.set("topic", els.topic.value);
    if (els.era.value !== "all") url.searchParams.set("era", els.era.value);
    else url.searchParams.delete("era");
    if (els.author.value !== "all") url.searchParams.set("author", els.author.value);
    else url.searchParams.delete("author");
    url.searchParams.set("zoom", zoom);
    if (compare.length) url.searchParams.set("compare", compare.join(","));
    else url.searchParams.delete("compare");
    history.replaceState(null, "", url);
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escAttr(s) {
    return esc(s).replace(/'/g, "&#39;");
  }

  // inject keyframes once
  const style = document.createElement("style");
  style.textContent = `@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}`;
  document.head.appendChild(style);

  els.topic.addEventListener("change", () => {
    activeId = null;
    animateNextDraw = true;
    compare = [];
    renderChips();
    fillCompareAdd();
    render();
    showEmptyDrawer();
  });
  els.era.addEventListener("change", () => {
    animateNextDraw = true;
    render();
  });
  els.author.addEventListener("change", () => {
    animateNextDraw = true;
    compare = [];
    renderChips();
    fillCompareAdd();
    render();
  });
  els.compareAdd.addEventListener("change", () => {
    const v = els.compareAdd.value;
    if (!v) return;
    if (!compare.includes(v) && compare.length < 3) compare.push(v);
    els.compareAdd.value = "";
    renderChips();
    fillCompareAdd();
    render();
  });
  els.chips.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove]");
    if (!btn) return;
    compare = compare.filter((s) => s !== btn.getAttribute("data-remove"));
    renderChips();
    fillCompareAdd();
    render();
  });
  els.zoomCentury.addEventListener("click", () => {
    zoom = "century";
    syncZoom();
    render();
  });
  els.zoomYear.addEventListener("click", () => {
    zoom = "year";
    syncZoom();
    render();
  });
  els.filtersToggle?.addEventListener("click", () => {
    const open = els.chrome.classList.toggle("filters-open");
    els.filtersToggle.setAttribute("aria-expanded", open ? "true" : "false");
    fitStage();
    render(false);
  });
  els.tipToggle?.addEventListener("click", () => {
    const open = els.tip.getAttribute("data-open") !== "0";
    els.tip.setAttribute("data-open", open ? "0" : "1");
    els.tipToggle.textContent = open ? "Show note" : "Hide note";
    fitStage();
    render(false);
  });
  window.addEventListener("resize", () => {
    fitStage();
    if (data) render(false);
  });
})();
