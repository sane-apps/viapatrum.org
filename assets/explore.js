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
    summary: root.querySelector("#explore-summary"),
    q: root.querySelector("#explore-q"),
    viewTimeline: root.querySelector("#view-timeline"),
    viewTable: root.querySelector("#view-table"),
    viewConsensus: root.querySelector("#view-consensus"),
    scaleSeg: root.querySelector("#explore-scale-seg"),
    legend: root.querySelector("#explore-legend"),
    zoomCentury: root.querySelector("#zoom-century"),
    zoomYear: root.querySelector("#zoom-year"),
    canvas: root.querySelector("#explore-canvas"),
    tip: root.querySelector("#explore-tip"),
    tipBody: root.querySelector("#explore-tip-body"),
    tipToggle: root.querySelector("#explore-tip-toggle"),
    drawer: root.querySelector("#explore-drawer"),
    tooltip: root.querySelector("#explore-tooltip"),
  };

  let data = null;
  let zoom = "year";
  let view = "timeline"; // timeline | table | consensus
  let query = "";
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

  // Stance is the core meaning: a mark in a row either teaches the row's claim
  // or rejects it. Every surface states this in plain words.
  const VERDICT = { affirms: "AFFIRMS", denies: "DENIES", qualified: "PARTLY AGREES" };
  const VERDICT_SENTENCE = {
    affirms: (a) => `${a} teaches this.`,
    denies: (a) => `${a} rejects this — they teach the opposite.`,
    qualified: (a) => `${a} partly agrees, with qualifications.`,
  };
  const CELL_LABEL = { yes: "Yes", no: "No", partly: "Partly", mixed: "Mixed", none: "—" };

  function cellVerdict(pts) {
    if (!pts.length) return "none";
    const s = new Set(pts.map((p) => p.stance));
    // Mixed means passages on genuinely opposite sides. Affirms plus
    // qualified is still agreement, so it reads Yes.
    if (s.has("denies") && (s.has("affirms") || s.has("qualified"))) return "mixed";
    if (s.has("affirms")) return "yes";
    if (s.has("denies")) return "no";
    return "partly";
  }

  fetch("/data/explore-index.json")
    .then((r) => { if (!r.ok) throw new Error("Explore unavailable"); return r.json(); })
    .then((json) => {
      data = json;
      fillFilters();
      const params = new URLSearchParams(location.search);
      if (params.get("topic") && [...els.topic.options].some((o) => o.value === params.get("topic"))) {
        els.topic.value = params.get("topic");
      }
      if ([...els.author.options].some(o => o.value === params.get("author"))) {
        els.author.value = params.get("author");
      }
      if ([...els.era.options].some(o => o.value === params.get("era"))) els.era.value = params.get("era");
      if (params.get("zoom") === "century") zoom = "century";
      if (["timeline", "table", "consensus"].includes(params.get("view"))) view = params.get("view");
      query = (params.get("q") || "").trim().toLowerCase();
      if (els.q) els.q.value = params.get("q") || "";
      const cmp = (params.get("compare") || "").split(",").filter(Boolean);
      compare = [...new Set(cmp)].filter(slug => data.authors.some(a => a.slug === slug)).slice(0, 3);
      syncZoom();
      syncView();
      fillCompareAdd();
      renderChips();
      render();
      showEmptyDrawer();
    })
    .catch(() => {
      els.drawer.innerHTML = "<p class='empty'>Explore index unavailable.</p>";
    });

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

  function authorDates(slug) {
    const a = (data.authors || []).find((x) => x.slug === slug);
    return (a && a.dates) || "";
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
    const words = query.split(/\s+/).filter(Boolean);
    return data.points.filter((p) => {
      if (p.topic !== topic) return false;
      if (era !== "all" && p.era_band !== era) return false;
      if (compare.length) {
        if (!compare.includes(p.author_slug)) return false;
      } else if (author !== "all" && p.author_slug !== author) return false;
      if (words.length) {
        const hay = [p.author, p.title, p.citation, p.summary, p.snippet, p.note, p.period]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!words.every((w) => hay.includes(w))) return false;
      }
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

  function syncView() {
    const map = { timeline: els.viewTimeline, table: els.viewTable, consensus: els.viewConsensus };
    for (const [k, b] of Object.entries(map)) {
      if (!b) continue;
      b.setAttribute("aria-pressed", String(view === k));
      b.classList.toggle("is-active", view === k);
    }
    if (els.scaleSeg) els.scaleSeg.hidden = view !== "timeline";
    if (els.legend) els.legend.hidden = view !== "timeline";
    els.canvas.classList.toggle("is-scroll", view === "table");
  }

  // Point ids repeat: one excerpt appears once per claim it speaks to. Render
  // keys must include the claim or same-id marks steal each other's spot.
  function pointKey(p) {
    return p.kind === "bucket" ? p.id : `${p.id}|${p.claim_id}|${p.kind}`;
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
    const head = root.querySelector(".explore-head");
    const chrome = root.querySelector(".explore-chrome");
    const tip = els.tip;
    const legend = els.legend;
    const used =
      (header ? header.getBoundingClientRect().height : 56) +
      (head ? head.getBoundingClientRect().height : 0) +
      (chrome ? chrome.getBoundingClientRect().height : 56) +
      (legend && !legend.hidden ? legend.getBoundingClientRect().height : 0) +
      (tip && !tip.hidden ? tip.getBoundingClientRect().height : 0);
    const stage = root.querySelector(".explore-stage");
    if (stage) stage.style.height = `${Math.max(280, window.innerHeight - used)}px`;
  }

  function renderSummary(points) {
    if (!els.summary) return;
    if (!points.length) {
      els.summary.textContent = "No positions under these filters.";
      return;
    }
    const authors = new Set(points.map((p) => p.author_slug));
    const years = points.map((p) => p.year).filter((y) => typeof y === "number");
    const span =
      years.length > 1
        ? `${Math.min(...years)}\u2013${Math.max(...years)}`
        : `${years[0] || "undated"}`;
    const n = (s) => points.filter((p) => p.stance === s).length;
    els.summary.textContent =
      `${points.length} positions \u00b7 ${authors.size} writers \u00b7 ${span} \u00b7 ` +
      `affirms ${n("affirms")} \u00b7 denies ${n("denies")} \u00b7 qualified ${n("qualified")}`;
  }

  function clearCanvas() {
    els.canvas.querySelectorAll("svg,.verdict-wrap,.canvas-empty").forEach((n) => n.remove());
  }

  function render(updateTip = true) {
    const topic = topicMeta();
    const points = filteredPoints();
    pointsCache = points;
    if (activeId && !points.some((p) => p.id === activeId)) { activeId = null; showEmptyDrawer(); }

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
    renderSummary(points);
    syncView();
    clearCanvas();
    if (view === "table") {
      displayCache = points;
      drawTable(topic, points);
    } else if (view === "consensus") {
      displayCache = points;
      drawConsensus(topic, points);
    } else {
      const display = zoom === "century" ? aggregateByCentury(points) : points;
      displayCache = display;
      drawSvg(topic, display, points);
    }
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
      pos.set(pointKey(p), { x, y: laneY(p.claim_id) + off, rad });
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
    html += `<text x="${W - padR}" y="${H - 16}" text-anchor="end" font-size="11" fill="var(--ink)" opacity="0.55" font-family="Source Sans 3, system-ui, sans-serif">years AD</text>`;

    if (ruptureYear) {
      const rx = xScale(ruptureYear);
      html += `<line x1="${rx}" x2="${rx}" y1="${padT - 8}" y2="${H - padB + 4}" stroke="#8a6a2f" stroke-width="2" stroke-dasharray="5 6" stroke-opacity="0.85"/>`;
      html += `<text x="${Math.min(rx + 6, W - padR)}" text-anchor="${rx > W - 100 ? "end" : "start"}" y="${padT - 14}" font-size="${compact ? 10 : 11}" fill="#6b5224" font-weight="650" font-family="Source Sans 3, system-ui, sans-serif">${compact ? "break →" : "later break →"}</text>`;
    }

    // Soft river through the first claim lane: passages that teach it (not denials).
    if (claims.length) {
      const mainClaim = claims[0].id;
      const river = display
        .filter((p) => p.claim_id === mainClaim && p.kind !== "bucket" && p.stance !== "denies")
        .sort((a, b) => (a.year || 0) - (b.year || 0));
      if (river.length >= 2) {
        const pts = river.map((p) => [xScale(p.year), laneY(p.claim_id)]);
        let d = `M ${pts[0][0]} ${pts[0][1]}`;
        for (let i = 1; i < pts.length; i++) {
          const [x0, yy0] = pts[i - 1];
          const [x1, yy1] = pts[i];
          const mx = (x0 + x1) / 2;
          d += ` C ${mx} ${yy0}, ${mx} ${yy1}, ${x1} ${yy1}`;
        }
        html += `<path d="${d}" fill="none" stroke="${LANE[0]}" stroke-opacity="0.35" stroke-width="3" stroke-linecap="round"/>`;
      }
    }

    // Shape carries stance: filled dot affirms the row, half dot partly agrees,
    // X denies it. Color still carries the writer.
    display.forEach((p, idx) => {
      const placed = pos.get(pointKey(p)) || { x: xScale(p.year), y: laneY(p.claim_id), rad: rDot };
      const x = placed.x;
      const y = placed.y;
      const ci = claimIndex[p.claim_id] ?? 0;
      const color = p.kind === "contrast" ? "#8a6a2f" : aColors[p.author_slug] || LANE[ci % LANE.length];
      const stance = p.stance || "affirms";
      const isContrast = p.kind === "contrast";
      const isBucket = p.kind === "bucket";
      const isDeny = !isContrast && !isBucket && stance === "denies";
      const isPartly = !isContrast && !isBucket && stance === "qualified";
      const dim = compare.length > 0 && !compare.includes(p.author_slug) && p.kind !== "bucket";
      const active = activeId === p.id;
      const cls = `explore-point${active ? " is-active" : ""}${dim ? " is-dim" : ""}${isContrast ? " is-pulse" : ""}`;
      const dates = authorDates(p.author_slug);
      const label = isBucket ? `${p.author} (${p.count})` : dates ? `${p.author} (${dates})` : `${p.author}`;
      const sub = isBucket
        ? `${p.count} texts · ${p.century}s`
        : isContrast
          ? (p.title || "Contrast")
          : `${VERDICT[stance] || stance} \u201c${claimLabel(topic, p.claim_id)}\u201d \u00b7 ${p.period || p.year || ""}`;
      const delay = Math.min(idx * 0.03, 0.6);
      const animStyle = animateNextDraw && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? `animation: fadeUp 0.5s ease ${delay}s both` : "";
      const hit = `<circle cx="${x}" cy="${y}" r="${placed.rad + (compact ? 9 : 6)}" fill="transparent" stroke="none"/>`;
      const head = `<g class="${cls}" tabindex="0" data-id="${escAttr(pointKey(p))}" data-stance="${escAttr(isContrast || isBucket ? p.kind : stance)}" data-label="${escAttr(label)}" data-sub="${escAttr(sub)}" role="button" aria-label="${escAttr(label + ": " + (p.title || p.stance || "passages"))}" style="${animStyle}">${hit}`;
      if (isContrast) {
        const s = placed.rad;
        html += `${head}
          <rect class="diamond" x="${x - s}" y="${y - s}" width="${s * 2}" height="${s * 2}" transform="rotate(45 ${x} ${y})" fill="${color}" stroke="#fff" stroke-width="${dotStroke}" filter="url(#soft)"/>
        </g>`;
      } else if (isBucket) {
        const r = placed.rad;
        html += `${head}
          <circle cx="${x}" cy="${y}" r="${r}" fill="${color}" stroke="#fff" stroke-width="2" filter="url(#soft)"/>
          <text x="${x}" y="${y + 4}" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">${p.count}</text>
        </g>`;
      } else if (isDeny) {
        const s = placed.rad + 1;
        const w = dotStroke + 1.5;
        html += `${head}
          <circle cx="${x}" cy="${y}" r="${placed.rad}" fill="none" stroke="${color}" stroke-opacity="0.45" stroke-width="1.5"/>
          <line x1="${x - s}" y1="${y - s}" x2="${x + s}" y2="${y + s}" stroke="${color}" stroke-width="${w}" stroke-linecap="round"/>
          <line x1="${x - s}" y1="${y + s}" x2="${x + s}" y2="${y - s}" stroke="${color}" stroke-width="${w}" stroke-linecap="round"/>
        </g>`;
      } else if (isPartly) {
        html += `${head}
          <circle cx="${x}" cy="${y}" r="${placed.rad}" fill="${color}" fill-opacity="0.35" stroke="#fff" stroke-width="${dotStroke}" filter="url(#soft)"/>
        </g>`;
      } else {
        html += `${head}
          <circle cx="${x}" cy="${y}" r="${placed.rad}" fill="${color}" stroke="#fff" stroke-width="${dotStroke}" filter="url(#soft)"/>
        </g>`;
      }
    });

    html += `</svg>`;
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
      els.canvas.insertAdjacentHTML("afterbegin", "<p class='canvas-empty'>Nothing on this filter yet. Pick another topic, era, or clear the search.</p>");
      els.drawer.innerHTML =
        "<p class='empty'>Nothing on this filter yet. Pick another topic, era, or clear the search.</p>";
    }
    animateNextDraw = false;
  }

  // Verdict table: one row per writer, one column per claim. Each cell answers
  // "did this writer teach this claim?" with Yes / No / Partly / Mixed.
  function drawTable(topic, points) {
    const claims = topic.claims || [];
    const use = points.filter((p) => p.kind !== "contrast");
    const seen = new Map();
    for (const p of use) {
      const y = p.year || 9999;
      if (!seen.has(p.author_slug) || y < seen.get(p.author_slug).year) {
        seen.set(p.author_slug, { name: p.author, year: y });
      }
    }
    const authors = [...seen.entries()].sort((a, b) => a[1].year - b[1].year);
    if (!authors.length || !claims.length) {
      els.canvas.insertAdjacentHTML("afterbegin", "<p class='canvas-empty'>Nothing on this filter yet. Pick another topic, era, or clear the search.</p>");
      els.drawer.innerHTML =
        "<p class='empty'>Nothing on this filter yet. Pick another topic, era, or clear the search.</p>";
      return;
    }
    const head = claims
      .map((c) => `<th scope="col" title="${escAttr(c.label)}">${esc(shortClaim(c))}</th>`)
      .join("");
    const rows = authors
      .map(([slug, a]) => {
        const dates = authorDates(slug);
        const cells = claims
          .map((c) => {
            const pts = use.filter((p) => p.author_slug === slug && p.claim_id === c.id);
            const v = cellVerdict(pts);
            if (v === "none") {
              return `<td><span class="verdict is-none" title="No passages from this writer on this claim yet">—</span></td>`;
            }
            const refs = pts.map((p) => p.title || p.citation || p.id).join("; ");
            return `<td><button type="button" class="verdict is-${v}" data-author="${escAttr(slug)}" data-claim="${escAttr(c.id)}" title="${escAttr(refs)}">${CELL_LABEL[v]} · ${pts.length}</button></td>`;
          })
          .join("");
        return `<tr><th scope="row"><span class="v-author">${esc(a.name)}</span>${dates ? ` <span class="v-dates">${esc(dates)}</span>` : ""}</th>${cells}</tr>`;
      })
      .join("");
    els.canvas.insertAdjacentHTML(
      "afterbegin",
      `<div class="verdict-wrap"><table class="verdict-table">` +
        `<caption>${authors.length} writers \u00b7 ${use.length} passages \u00b7 click a verdict to read the passages</caption>` +
        `<thead><tr><th scope="col">Writer</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>`
    );
    els.canvas.querySelectorAll(".verdict[data-author]").forEach((b) => {
      b.addEventListener("click", () => selectCell(b.getAttribute("data-author"), b.getAttribute("data-claim")));
    });
    animateNextDraw = false;
  }

  // Consensus: share of passages agreeing with each claim, per 50 years.
  function drawConsensus(topic, points) {
    const claims = topic.claims || [];
    const scoreOf = { affirms: 1, qualified: 0.5, denies: 0 };
    const use = points.filter((p) => p.kind !== "contrast" && typeof p.year === "number" && p.stance in scoreOf);
    const byClaim = new Map();
    for (const p of use) {
      const b = Math.floor(p.year / 50) * 50;
      if (!byClaim.has(p.claim_id)) byClaim.set(p.claim_id, new Map());
      const m = byClaim.get(p.claim_id);
      const e = m.get(b) || { sum: 0, n: 0 };
      e.sum += scoreOf[p.stance];
      e.n += 1;
      m.set(b, e);
    }
    const buckets = [...new Set(use.map((p) => Math.floor(p.year / 50) * 50))].sort((a, b) => a - b);
    if (!buckets.length) {
      els.canvas.insertAdjacentHTML("afterbegin", "<p class='canvas-empty'>No dated passages under these filters.</p>");
      els.drawer.innerHTML = "<p class='empty'>No dated passages under these filters.</p>";
      return;
    }
    const rect = els.canvas.getBoundingClientRect();
    const W = Math.max(320, Math.floor(rect.width) || 900);
    const H = Math.max(280, Math.min(Math.floor(rect.height) || 420, window.innerHeight));
    const perRow = W < 560 ? 1 : W < 900 ? 2 : 4;
    const rowsLegend = Math.ceil(claims.length / perRow);
    const padL = 112;
    const padR = 28;
    const padT = 14 + rowsLegend * 20;
    const padB = 44;
    const b0 = buckets[0];
    const b1 = buckets[buckets.length - 1] + 50;
    const x = (b) => padL + ((b + 25 - b0) / ((b1 - b0) || 1)) * (W - padL - padR);
    const y = (s) => padT + (1 - s) * (H - padT - padB);

    let html = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Agreement over time">`;
    [["100% agree", 1], ["50% \u2014 split", 0.5], ["0% \u2014 all reject", 0]].forEach(([lab, s]) => {
      html += `<line x1="${padL}" x2="${W - padR}" y1="${y(s)}" y2="${y(s)}" stroke="#d5cbb6" stroke-opacity="${s === 0.5 ? 0.5 : 0.9}" stroke-dasharray="${s === 0.5 ? "3 5" : "0"}"/>`;
      html += `<text x="${padL - 8}" y="${y(s) + 4}" text-anchor="end" font-size="11" fill="var(--ink)" font-family="Source Sans 3, system-ui, sans-serif">${esc(lab)}</text>`;
    });
    const step = buckets.length > 12 ? 2 : 1;
    buckets.forEach((b, i) => {
      if (i % step && i !== buckets.length - 1) return;
      html += `<text x="${x(b)}" y="${H - 16}" text-anchor="middle" font-size="12" fill="var(--ink)" font-family="Source Sans 3, system-ui, sans-serif">${b}s</text>`;
    });
    html += `<text x="${W - padR}" y="${H - 16}" text-anchor="end" font-size="11" fill="var(--ink)" opacity="0.55" font-family="Source Sans 3, system-ui, sans-serif">years AD</text>`;
    claims.forEach((c, i) => {
      const color = LANE[i % LANE.length];
      const lx = padL + (i % perRow) * Math.floor((W - padL - padR) / perRow);
      const ly = 14 + Math.floor(i / perRow) * 20;
      html += `<line x1="${lx}" x2="${lx + 22}" y1="${ly}" y2="${ly}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>`;
      html += `<text x="${lx + 28}" y="${ly + 4}" font-size="12" font-weight="650" fill="${color}" font-family="Source Sans 3, system-ui, sans-serif">${esc(shortClaim(c))}</text>`;
    });
    claims.forEach((c, i) => {
      const m = byClaim.get(c.id);
      if (!m) return;
      const color = LANE[i % LANE.length];
      const pts = [...m.entries()].sort((a, b) => a[0] - b[0]);
      html += `<g class="consensus-line" data-claim="${escAttr(c.id)}">`;
      if (pts.length > 1) {
        html += `<polyline points="${pts.map(([b, e]) => `${x(b).toFixed(1)},${y(e.sum / e.n).toFixed(1)}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
      }
      pts.forEach(([b, e]) => {
        const pct = Math.round((e.sum / e.n) * 100);
        html += `<circle cx="${x(b)}" cy="${y(e.sum / e.n)}" r="5" fill="${color}" stroke="#fff" stroke-width="2"><title>${esc(shortClaim(c))} \u00b7 ${b}s: ${pct}% agree (${e.n} passage${e.n === 1 ? "" : "s"})</title></circle>`;
      });
      html += `</g>`;
    });
    html += `</svg>`;
    els.canvas.insertAdjacentHTML("afterbegin", html);
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
      .map(([slug, name]) => {
        const dates = authorDates(slug);
        return `<li><i style="background:${aColors[slug] || LANE[0]}"></i><span>${esc(name)}${dates ? ` (${esc(dates)})` : ""}</span></li>`;
      })
      .join("");
    const claimKeys = (topic.claims || [])
      .map(
        (c, i) =>
          `<li><i class="lane-swatch" style="background:${LANE[i % LANE.length]}"></i><span><strong>${esc(shortClaim(c))}</strong> — ${esc(c.label)}</span></li>`
      )
      .join("");
    const hint = view === "table"
      ? "Click a verdict to read the passages behind it."
      : view === "consensus"
        ? "Each line tracks one claim's agreement over fifty-year spans."
        : "Click a mark to read the passage.";
    els.drawer.innerHTML = `
      <p class="empty">Three views, one question — what did each writer teach? Timeline shows every passage in time, Table gives each writer's verdict, Consensus charts agreement. ${hint}</p>
      <div class="lane-key"><h3 class="drawer-label">Marks</h3><ul>
      <li><i class="mark-affirms">\u25cf</i><span><strong>Affirms the row</strong> — the writer teaches this claim</span></li>
      <li><i class="mark-partly">\u25d0</i><span><strong>Partly</strong> — agrees with qualifications</span></li>
      <li><i class="mark-denies">\u2715</i><span><strong>Denies the row</strong> — the writer teaches the opposite</span></li>
      </ul></div>
      <div class="lane-key"><h3 class="drawer-label">Writers, earliest first</h3><ul>${authorKeys}</ul></div>
      <div class="lane-key"><h3 class="drawer-label">Rows (claims)</h3><ul>${claimKeys}
      <li><i class="diamond" style="background:#8a6a2f"></i><span>Diamond — contrast card (full works forthcoming)</span></li>
      </ul></div>`;
  }

  function selectPoint(id) {
    activeId = id;
    const topic = topicMeta();
    const point =
      displayCache.find((x) => pointKey(x) === id) || pointsCache.find((x) => pointKey(x) === id);
    if (!point) return;

    els.canvas.querySelectorAll(".explore-point").forEach((g) => {
      g.classList.toggle("is-active", g.getAttribute("data-id") === id);
    });

    if (point.kind === "bucket") {
      const kids = point.children
        .map(
          (c) =>
            `<li><a href="${escAttr(c.href || "#")}">${esc(c.title || c.citation || c.id)}</a>
            <span class="meta">${esc(c.author)} · ${esc(VERDICT[c.stance] || c.stance)}</span></li>`
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
    const verdictWord = point.kind === "contrast" ? "" : (VERDICT[point.stance] || point.stance || "");
    const sentence = point.kind === "contrast" ? "" : (VERDICT_SENTENCE[point.stance] ? VERDICT_SENTENCE[point.stance](point.author) : "");
    els.drawer.innerHTML = `
      <p class="badge-kind">${esc(kindBadge)}</p>
      <h2>${esc(point.title || point.citation || point.id)}</h2>
      <p class="meta">${esc(point.author)} · ${esc(point.period || String(point.year || ""))} · ${esc(point.era_band || "")}</p>
      ${verdictWord ? `<p class="stance-pill"><span>${esc(verdictWord)} \u2014 ${esc(claimLabel(topic, point.claim_id))}</span></p>` : ""}
      ${sentence ? `<p class="meta verdict-line">${esc(sentence)}</p>` : ""}
      ${previewBlock}
      ${noteBlock}
      ${disclaimerBlock}
      ${link}`;
  }

  function selectCell(slug, claimId) {
    const topic = topicMeta();
    const pts = pointsCache.filter((p) => p.author_slug === slug && p.claim_id === claimId && p.kind !== "contrast");
    if (!pts.length) return;
    const claim = (topic.claims || []).find((c) => c.id === claimId) || { label: claimId };
    const name = pts[0].author;
    const v = cellVerdict(pts);
    const sentence = {
      yes: `${name} teaches YES \u2014 ${claim.label}.`,
      no: `${name} teaches NO \u2014 they reject \u201c${claim.label}\u201d.`,
      partly: `${name} PARTLY agrees \u2014 ${claim.label}, with qualifications.`,
      mixed: `${name} has passages on both sides of \u201c${claim.label}\u201d \u2014 read each one.`,
      none: "",
    }[v];
    const dates = authorDates(slug);
    const kids = pts
      .map(
        (c) =>
          `<li><a href="${escAttr(c.href || "#")}">${esc(c.title || c.citation || c.id)}</a>
          <span class="meta">${esc(VERDICT[c.stance] || c.stance)} · ${esc(c.period || String(c.year || ""))}</span></li>`
      )
      .join("");
    els.canvas.querySelectorAll(".verdict[data-author]").forEach((b) => {
      b.classList.toggle("is-active", b.getAttribute("data-author") === slug && b.getAttribute("data-claim") === claimId);
    });
    els.drawer.innerHTML = `
      <p class="badge-kind">Writer verdict</p>
      <h2>${esc(name)}${dates ? ` <span class="meta">(${esc(dates)})</span>` : ""}</h2>
      <p class="meta">${esc(claim.label)} · ${pts.length} passage${pts.length === 1 ? "" : "s"}</p>
      ${sentence ? `<p class="meta verdict-line">${esc(sentence)}</p>` : ""}
      <ul class="card-list">${kids}</ul>`;
  }

  function claimLabel(topic, claimId) {
    const c = (topic.claims || []).find((x) => x.id === claimId);
    return c ? shortClaim(c) : claimId;
  }

  function syncFiltersToggle() {
    if (!els.filtersToggle) return;
    const active = els.era.value !== "all" || els.author.value !== "all" || compare.length > 0 || query !== "";
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
    if (view !== "timeline") url.searchParams.set("view", view);
    else url.searchParams.delete("view");
    if (query) url.searchParams.set("q", els.q ? els.q.value.trim() : query);
    else url.searchParams.delete("q");
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
  els.viewTimeline?.addEventListener("click", () => setView("timeline"));
  els.viewTable?.addEventListener("click", () => setView("table"));
  els.viewConsensus?.addEventListener("click", () => setView("consensus"));
  function setView(v) {
    if (view === v) return;
    view = v;
    activeId = null;
    animateNextDraw = true;
    render();
    showEmptyDrawer();
  }
  els.q?.addEventListener("input", () => {
    query = els.q.value.trim().toLowerCase();
    activeId = null;
    animateNextDraw = true;
    render(false);
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
