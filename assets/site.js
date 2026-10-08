(() => {
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector("#site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Night reading: follow the system until the reader picks; remember the pick.
  const themeBtn = document.querySelector(".theme-toggle");
  if (themeBtn) {
    const root = document.documentElement;
    const isDark = () =>
      root.dataset.theme === "dark" ||
      (!root.dataset.theme && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    // Browser bar colour follows a manual pick (the page ships one meta per system theme).
    const PAPER = { light: "#f8f6f0", dark: "#15120e" };
    const barColour = () => {
      const picked = root.dataset.theme;
      if (picked !== "light" && picked !== "dark") return;
      document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", PAPER[picked]));
    };
    const paint = () => {
      const dark = isDark();
      themeBtn.textContent = dark ? "☀" : "☾";
      themeBtn.removeAttribute("aria-pressed");
      themeBtn.setAttribute("aria-label", dark ? "Use light reading" : "Use dark reading");
      themeBtn.setAttribute("title", dark ? "Use light reading" : "Use dark reading");
      barColour();
    };
    themeBtn.addEventListener("click", () => {
      const next = isDark() ? "light" : "dark";
      root.dataset.theme = next;
      try {
        localStorage.setItem("vp-theme", next);
      } catch {
        /* private mode: the choice lasts for this page only */
      }
      paint();
    });
    if (window.matchMedia) {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      if (mq.addEventListener) mq.addEventListener("change", paint);
    }
    paint();
  }

  // Home: the day's passage. The page ships one at rest; swap in today's.
  const dailyCard = document.querySelector("[data-daily]");
  if (dailyCard) {
    fetch("/data/daily.json").then((r) => (r.ok ? r.json() : [])).then((rows) => {
      if (rows.length) {
        const now = new Date();
        const day = Math.floor(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / 86400000);
        const r = rows[day % rows.length];
        const set = (sel, text) => {
          const el = dailyCard.querySelector(sel);
          if (el) el.textContent = text;
        };
        set(".vp-daily-q", r.q);
        set(".vp-daily-a", r.a);
        set(".vp-daily-d", r.d);
        set(".vp-daily-c", r.c);
        set(".vp-daily-topic", r.t);
        dailyCard.querySelectorAll(".vp-daily-topic, .vp-daily-th").forEach((a) => a.setAttribute("href", r.th));
        const read = dailyCard.querySelector(".vp-daily-h");
        if (read) read.setAttribute("href", r.h);
      }
    }).catch(() => {
      /* keep the passage the page shipped with */
    });
  }

  // Scripture reader: select a verse to open what the Fathers said about it.
  const bx = document.querySelector("[data-bx]");
  if (bx) {
    const desk = bx.querySelector(".bx-desk");
    const home = desk && desk.querySelector('[data-for="chapter"]');
    const sections = desk ? Array.from(desk.querySelectorAll(".desk-verse")) : [];
    const text = bx.querySelector(".bx-text");
    const show = (v, opts = {}) => {
      if (!desk) return;
      const target = v ? sections.find((sec) => sec.dataset.for === String(v)) : null;
      sections.forEach((sec) => (sec.hidden = sec !== target));
      if (home) home.hidden = !!target;
      desk.classList.toggle("is-verse", !!target);
      bx.querySelectorAll(".v.is-on").forEach((el) => el.classList.remove("is-on"));
      if (target) {
        const verse = bx.querySelector(`.v[data-v="${v}"]`);
        if (verse) verse.classList.add("is-on");
        desk.scrollTop = 0;
        if (opts.push !== false) history.replaceState(null, "", `#v${v}`);
        if (opts.focus) target.querySelector("h2")?.setAttribute("tabindex", "-1"), target.querySelector("h2")?.focus({ preventScroll: true });
      } else if (opts.push !== false) {
        history.replaceState(null, "", location.pathname + location.search);
      }
    };
    bx.addEventListener("click", (e) => {
      const verse = e.target.closest(".v.cited");
      if (verse) return show(verse.dataset.v);
      const jump = e.target.closest(".desk-jump");
      if (jump) {
        const el = bx.querySelector(`.v[data-v="${jump.dataset.v}"]`);
        if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
        return show(jump.dataset.v);
      }
      if (e.target.closest(".desk-back, .desk-close")) show(null);
    });
    bx.addEventListener("keydown", (e) => {
      const verse = e.target.closest(".v.cited");
      if (verse && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        show(verse.dataset.v, { focus: true });
      }
      if (e.key === "Escape") show(null);
    });
    const fromHash = () => {
      const m = location.hash.match(/^#v(\d+)/);
      if (m) show(m[1], { push: false });
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);

    // Translation switch: BSB ships in the page; others load per chapter.
    const trButtons = Array.from(bx.querySelectorAll("[data-tr]"));
    const original = text ? Array.from(text.querySelectorAll(".v")).map((el) => [el.dataset.v, el.querySelector(".vt").textContent]) : [];
    const originalMap = new Map(original);
    // Start from the BSB each time so no verse keeps a third version's words.
    const paint = (rows) => {
      const map = new Map(rows.map(([v, t]) => [String(v), t]));
      text.querySelectorAll(".v").forEach((el) => {
        const t = map.get(el.dataset.v) || originalMap.get(el.dataset.v);
        if (t) el.querySelector(".vt").textContent = t;
      });
    };
    // Latest click wins: a slow earlier fetch must not repaint over a later pick.
    let trSeq = 0;
    const credit = bx.querySelector(".bx-tr-credit");
    // A failed load is said next to the pills, where the reader is looking.
    let trNote = null;
    const noteTr = (msg) => {
      if (!trNote && msg) {
        const tools = bx.querySelector(".bx-tools") || (trButtons[0] && trButtons[0].parentElement);
        if (!tools) return;
        trNote = document.createElement("p");
        trNote.className = "bx-tr-credit bx-tr-note";
        trNote.setAttribute("role", "status");
        tools.insertAdjacentElement("afterend", trNote);
      }
      if (trNote) {
        trNote.textContent = msg || "";
        trNote.hidden = !msg;
      }
    };
    const press = (key) => trButtons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.tr === key ? "true" : "false"));
    const useTr = async (key) => {
      if (!text) return;
      const my = ++trSeq;
      const btn = trButtons.find((b) => b.dataset.tr === key);
      press(key);
      noteTr("");
      if (key === "bsb") delete bx.dataset.loading;
      else bx.dataset.loading = key;
      try {
        if (key === "bsb") paint(original);
        else if (btn && btn.dataset.remote) {
          const r = await fetch(`https://bolls.life/get-text/${btn.dataset.remote}/${text.dataset.booknum}/${text.dataset.chap}/`);
          if (my !== trSeq) return;
          if (!r.ok) throw new Error("missing");
          const rows = await r.json();
          if (my !== trSeq) return;
          paint(
            rows.map((x) => [
              x.verse,
              String(x.text || "")
                .replace(/<sup>[\s\S]*?<\/sup>/g, "")
                .replace(/<[^>]+>/g, "")
                .replace(/[\u24d0-\u24e9]/g, "")
                .replace(/\s+/g, " ")
                .trim(),
            ])
          );
        } else {
          const r = await fetch(`/data/bible/${key}/${text.dataset.book}/${text.dataset.chap}.json`);
          if (my !== trSeq) return;
          if (!r.ok) throw new Error("missing");
          const rows = await r.json();
          if (my !== trSeq) return;
          paint(rows);
        }
        delete bx.dataset.loading;
        if (credit) {
          // Hosted versions are credited in the note below; loaded ones need their own notice.
          credit.textContent = (btn && btn.dataset.remote && btn.dataset.credit) || "";
          credit.hidden = !credit.textContent;
        }
        try {
          localStorage.setItem("vp-bible", key);
        } catch {
          /* remembered for this page only */
        }
      } catch {
        if (my !== trSeq) return;
        delete bx.dataset.loading;
        paint(original);
        press("bsb");
        if (credit) {
          credit.textContent = "";
          credit.hidden = true;
        }
        noteTr(`Could not load ${(btn && btn.textContent.trim()) || key.toUpperCase()}. Showing BSB.`);
      }
    };
    trButtons.forEach((b) => b.addEventListener("click", () => useTr(b.dataset.tr)));
    try {
      const saved = localStorage.getItem("vp-bible");
      if (saved && saved !== "bsb" && trButtons.some((b) => b.dataset.tr === saved)) useTr(saved);
    } catch {
      /* default translation */
    }
  }

  // Reader source panels: Greek/Latin load when opened (one file per work).
  const srcCache = new Map();
  document.addEventListener(
    "toggle",
    async (e) => {
      const d = e.target;
      if (!(d instanceof HTMLDetailsElement) || !d.open || !d.classList.contains("src-lazy") || d.dataset.loaded) return;
      const body = d.querySelector(".src-body");
      try {
        const url = d.dataset.src;
        if (!srcCache.has(url)) srcCache.set(url, fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(r.status))));
        const data = await srcCache.get(url);
        const kind = d.dataset.kind;
        const pairs = (d.dataset.secs || "").split(",").filter(Boolean).map((x) => x.split("|"));
        const frag = document.createDocumentFragment();
        for (const [sid, shown] of pairs) {
          const paras = (data[sid] && data[sid][kind]) || [];
          if (!paras.length) continue;
          if (pairs.length > 1) {
            const m = document.createElement("p");
            m.className = "src-sec";
            m.textContent = "\u00a7" + shown;
            frag.appendChild(m);
          }
          for (const t of paras) {
            const p = document.createElement("p");
            p.className = "src";
            p.textContent = t;
            frag.appendChild(p);
          }
        }
        body.replaceChildren(frag);
        d.dataset.loaded = "1";
      } catch {
        /* keep the links to each section page */
      }
    },
    true
  );

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = document.querySelector(btn.getAttribute("data-copy") || "");
      if (!el) return;
      try {
        await navigator.clipboard.writeText(el.innerText);
        const old = btn.textContent;
        btn.textContent = "Copied";
        window.setTimeout(() => {
          btn.textContent = old;
        }, 1500);
      } catch {
        btn.textContent = "Select the prompt and copy";
      }
    });
  });

  // Compact /works/ author catalog: sort, filter, find.
  const browse = document.querySelector("[data-works-browse]");
  if (browse) {
    const list = browse.querySelector("#works-list");
    const status = browse.querySelector("#works-status");
    const q = browse.querySelector("#works-q");
    const empty = browse.querySelector("#works-empty");
    const emptyHtml = empty ? empty.innerHTML : "";
    const passageHits = browse.querySelector("#passage-hits");
    const passageResults = browse.querySelector("#passage-results");
    const meaningHits = browse.querySelector("#meaning-hits");
    const meaningResults = browse.querySelector("#meaning-results");
    // Search results run: Matching works, By meaning, Passages, Writers.
    const titleHits = browse.querySelector("#title-hits");
    const titleResults = browse.querySelector("#title-results");
    const titleMore = browse.querySelector("#title-more");
    const titleTemplate = browse.querySelector("#works-by-title");
    const passageNote = browse.querySelector("#passage-note");
    const passageNoteText = passageNote ? passageNote.textContent : "";
    const writersH = browse.querySelector("#writers-h");
    const TITLE_CAP = 20;
    let titleEntries = null;
    let titleBySlug = null;
    let entryHits = new Map();
    let titleCount = 0;
    let titleExpanded = false;
    let titleHtml = "";
    let wasSearching = false;
    let meaningTimer = 0;
    let meaningSeq = 0;
    let meaningCount = 0;
    let meaningPending = false;
    const workCount = Number(browse.getAttribute("data-work-count") || "0");
    const authorCount = Number(browse.getAttribute("data-author-count") || "0");
    let sort = "chrono";
    let filter = "all";
    // Passage index: shards load as a word needs them. Several MB, not on page load.
    let searchIndex = null;
    let indexFailed = false;
    let indexPromise = null;
    let manifest = null;
    let manifestPromise = null;
    const loadedShards = new Map();
    // Word index (manifest.words, build_site.write_search_words): vocabulary,
    // one row per passage, and postings buckets. A one-word search reads these
    // (a few hundred KB) instead of the text shards (about 20 MB).
    let words = null;
    let wordsPromise = null;
    const WORD_TERM = /^[a-z0-9]+$/;
    let failedTerm = "";
    let passageCount = 0;
    // The term the passage list was last built for; until it equals the
    // typed term (debounce, index loading), the status says "Searching…".
    let passageTerm = null;
    let lastTerm = "";
    let lastShown = "";

    const items = () => Array.from(list.querySelectorAll(":scope > li.author-entry"));
    const inFilter = (li, f) => {
      if (f === "all") return true;
      if (f === "oet") return li.getAttribute("data-oet") === "1";
      return (li.getAttribute("data-era") || "").split(/\s+/).includes(f);
    };
    const plural = (n, one, many) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

    // Shards listed in data/search/manifest.json. Each shard carries a bitset
    // of a–z trigrams (build_site.search_trigrams); a word skips shards that
    // cannot contain it. Shards with no bitset are all loaded. There is no
    // single-file index. Each row's search text is lowercased once here.
    const readJson = (url) => fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))));
    // Word search starts only for 3 or more letters, after the typing pause.
    // Two letters still match titles and writers from the page (2026-10-06 audit).
    const PASSAGE_MIN = 3;
    const b64bytes = (b64) => {
      const bin = atob(b64);
      const out = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
      return out;
    };
    // Same bit order as build_site.search_grams_cover. No bitset, or no 3-letter
    // run, means the shard cannot be skipped.
    const gramsCover = (grams, term) => {
      if (!grams) return true;
      const runs = String(term || "").toLowerCase().match(/[a-z]{3,}/g);
      if (!runs) return true;
      const raw = b64bytes(grams);
      const has = (i) => ((raw[i >> 3] || 0) & (1 << (i & 7))) !== 0;
      for (const run of runs) {
        for (let i = 0; i <= run.length - 3; i++) {
          const a = run.charCodeAt(i) - 97;
          const b = run.charCodeAt(i + 1) - 97;
          const c = run.charCodeAt(i + 2) - 97;
          if (a < 0 || b < 0 || c < 0 || a > 25 || b > 25 || c > 25) return true;
          if (!has((a * 26 + b) * 26 + c)) return false;
        }
      }
      return true;
    };
    const shardPlan = (man) => {
      const raw = Array.isArray(man) ? man : man && (man.shards || man.files);
      if (!Array.isArray(raw) || !raw.length) return null;
      const plan = [];
      for (const s of raw) {
        const file = typeof s === "string" ? s : s && (s.file || s.path || s.href || s.url);
        if (typeof file !== "string" || !file) return null;
        const grams = s && typeof s === "object" && typeof s.grams === "string" ? s.grams : "";
        plan.push({ url: file.startsWith("/") ? file : `/data/search/${file}`, grams });
      }
      return plan;
    };
    const useWords = (term) =>
      !!(manifest && manifest.words && Array.isArray(manifest.words.buckets) && WORD_TERM.test(term));
    // Vocabulary entries that contain term, and the buckets holding their postings.
    let wordHitsFor = "";
    let wordHitsCache = null;
    const wordHits = (term) => {
      if (wordHitsFor === term && wordHitsCache) return wordHitsCache;
      const hits = [];
      const buckets = new Set();
      const firsts = words.buckets;
      for (let i = 0; i < words.vocab.length; i++) {
        if (!words.vocab[i].includes(term)) continue;
        let lo = 0;
        let hi = firsts.length - 1;
        while (lo < hi) {
          const mid = (lo + hi + 1) >> 1;
          if (firsts[mid].first <= i) lo = mid;
          else hi = mid - 1;
        }
        hits.push([i, lo]);
        buckets.add(lo);
      }
      wordHitsFor = term;
      wordHitsCache = { hits, buckets: [...buckets] };
      return wordHitsCache;
    };
    // Rows whose search text contains term, in shard order.
    const matchRows = (term) => {
      if (!useWords(term)) return (searchIndex || []).filter((row) => row._b.includes(term));
      const mark = new Uint8Array(words.docs.length);
      for (const [wi, bi] of wordHits(term).hits) {
        const list = words.loaded.get(bi)[wi - words.buckets[bi].first] || "";
        let id = -1;
        for (const gap of list.split(",")) {
          id += parseInt(gap, 36);
          if (id >= 0 && id < mark.length) mark[id] = 1;
        }
      }
      const rows = [];
      for (let id = 0; id < mark.length; id++) if (mark[id]) rows.push(words.docs[id]);
      return rows;
    };
    const indexReady = () => !!searchIndex || !!words;
    const termCovered = (term) => {
      if (!manifest) return false;
      if (useWords(term)) return !!words && wordHits(term).buckets.every((b) => words.loaded.has(b));
      const plan = shardPlan(manifest);
      if (!plan) return false;
      return plan.every((p) => !gramsCover(p.grams, term) || loadedShards.has(p.url));
    };
    const loadIndex = (term) => {
      if (indexPromise) return indexPromise;
      indexPromise = (async () => {
        if (!manifest) {
          if (!manifestPromise) {
            manifestPromise = readJson("/data/search/manifest.json").catch((err) => {
              manifestPromise = null;
              throw err;
            });
          }
          manifest = await manifestPromise;
        }
        if (useWords(term)) {
          if (!words) {
            const w = manifest.words;
            if (!wordsPromise) {
              wordsPromise = Promise.all([readJson(w.vocab), readJson(w.docs)]).catch((err) => {
                wordsPromise = null;
                throw err;
              });
            }
            const [vocab, docs] = await wordsPromise;
            if (!Array.isArray(vocab) || !Array.isArray(docs)) throw new Error("bad word index");
            words = {
              vocab,
              docs: docs.map(([kind, title, author, href]) => ({ kind, title, author, href })),
              buckets: w.buckets.map((b) => ({ url: b.file, first: Number(b.first) || 0 })),
              loaded: new Map(),
            };
          }
          const need = wordHits(term).buckets.filter((b) => !words.loaded.has(b));
          const parts = await Promise.all(need.map((b) => readJson(words.buckets[b].url)));
          if (!parts.every(Array.isArray)) throw new Error("bad word bucket");
          need.forEach((b, i) => words.loaded.set(b, parts[i]));
          indexFailed = false;
          return;
        }
        const plan = shardPlan(manifest);
        if (!plan) throw new Error("bad manifest");
        const missing = plan.filter((p) => gramsCover(p.grams, term) && !loadedShards.has(p.url));
        if (missing.length) {
          const parts = await Promise.all(missing.map((p) => readJson(p.url)));
          if (!parts.every(Array.isArray)) throw new Error("bad shard");
          missing.forEach((p, i) => {
            for (const row of parts[i]) {
              row._b = `${row.title || ""} ${row.author || ""} ${row.text || ""}`.toLowerCase();
              delete row.text;
            }
            loadedShards.set(p.url, parts[i]);
          });
        }
        const rows = [];
        for (const part of loadedShards.values()) rows.push(...part);
        searchIndex = rows;
        indexFailed = false;
      })().catch(() => {
        // Keep the failure for the status line; the next new term retries.
        indexFailed = true;
        failedTerm = lastTerm;
        searchIndex = [];
        manifest = null;
      }).finally(() => {
        indexPromise = null;
      });
      indexPromise.then(() => {
        passageTerm = null;
        if (lastTerm.length >= PASSAGE_MIN) apply();
      });
      return indexPromise;
    };

    const writeStatus = (term, visible) => {
      if (!status) return;
      if (term.length < 2) {
        const sortLabel = sort === "author" ? "author name" : "era (earliest first)";
        const lead = filter === "all" ? `${authorCount} authors` : `${visible.length} of ${authorCount} authors`;
        status.textContent = `${lead} · ${workCount} works · sorted by ${sortLabel}`;
        return;
      }
      const writers = visible.length ? ` · ${plural(visible.length, "writer", "writers")}` : "";
      const long = term.length >= PASSAGE_MIN;
      if (long && (!indexReady() || passageTerm !== term)) status.textContent = "Searching…";
      else if (long && indexFailed)
        status.textContent = titleCount
          ? `${plural(titleCount, "work matches", "works match")} “${lastShown}” by title or writer. Word search did not load; try again later.`
          : `Word search did not load. Try again later.${writers}`;
      else {
        // "N works and M passages match"; a part that is 0 is left out.
        const parts = [];
        if (titleCount) parts.push(plural(titleCount, "work", "works"));
        if (passageCount) parts.push(plural(passageCount, "passage", "passages"));
        const verb = parts.length > 1 || titleCount + passageCount > 1 ? "match" : "matches";
        status.textContent = parts.length
          ? `${parts.join(" and ")} ${verb} “${lastShown}”`
          : long
          ? `No works or passages match “${lastShown}”${writers}`
          : `No work titles match “${lastShown}”${writers}. Passages are searched from ${PASSAGE_MIN} letters.`;
      }
    };

    // Rows of the Title template, one per work (a series in books is one
    // row); read once, on the first search.
    const readTitles = () => {
      if (titleEntries) return titleEntries;
      titleEntries = [];
      titleBySlug = new Map();
      const lis = titleTemplate && titleTemplate.content ? titleTemplate.content.querySelectorAll("li.title-entry") : [];
      lis.forEach((li, order) => {
        const a = li.querySelector("a");
        const title = (li.querySelector(".work-title") || {}).textContent || "";
        const meta = (li.querySelector(".meta") || {}).textContent || "";
        const e = { order, href: a ? a.getAttribute("href") : "", title, meta, lc: title.toLowerCase(), find: `${title} ${meta}`.toLowerCase() };
        titleEntries.push(e);
        for (const s of (li.getAttribute("data-slug") || "").split(/\s+/)) if (s) titleBySlug.set(s, e);
      });
      return titleEntries;
    };
    // A work's passage row ("/works/<slug>/<section>/") -> its title row.
    const titleForRow = (row) => {
      const slug = String(row.href || "").split("/")[2];
      if (!slug) return null;
      readTitles();
      let e = titleBySlug.get(slug);
      if (!e) {
        // Not in the template: title from the row ("Title §3: head").
        const title = String(row.title || slug).split(" §")[0];
        const meta = row.author || "";
        e = { order: titleEntries.length, href: `/works/${slug}/`, title, meta, lc: title.toLowerCase(), find: `${title} ${meta}`.toLowerCase() };
        titleEntries.push(e);
        titleBySlug.set(slug, e);
      }
      return e;
    };

    // Matching works: title or writer matches at once; works whose passages
    // match join once the passage scan for this term has run. Title matches
    // first, then most matching passages, then A–Z.
    const renderTitles = (term, searching) => {
      if (!titleHits || !titleResults) return;
      let html = "";
      titleCount = 0;
      if (searching) {
        const counted = passageTerm === term;
        const hits = [];
        for (const e of readTitles()) {
          const n = counted ? entryHits.get(e) || 0 : 0;
          if (n || e.find.includes(term)) hits.push({ e, n, t: e.lc.includes(term) ? 1 : 0 });
        }
        hits.sort((a, b) => b.t - a.t || b.n - a.n || a.e.order - b.e.order);
        titleCount = hits.length;
        html = (titleExpanded ? hits : hits.slice(0, TITLE_CAP))
          .map(
            ({ e, n }) =>
              `<li><a href="${escapeHtml(e.href)}"><strong class="work-title">${escapeHtml(e.title)}</strong><span>${escapeHtml(
                e.meta
              )}${n ? ` · ${plural(n, "matching passage", "matching passages")}` : ""}</span></a></li>`
          )
          .join("");
      }
      // Rewrite only on change, so a focused row keeps focus.
      if (html !== titleHtml) {
        titleResults.innerHTML = html;
        titleHtml = html;
      }
      titleHits.hidden = titleCount === 0;
      if (titleMore) {
        titleMore.hidden = titleExpanded || titleCount <= TITLE_CAP;
        titleMore.textContent = `Show all ${titleCount} works`;
      }
    };

    // The empty note shows only when nothing at all is listed.
    const updateEmpty = (term, visible) => {
      if (!empty) return;
      const searching = term.length >= 2;
      let show = false;
      if (visible.length === 0) {
        if (!searching) show = true;
        // Not when word search failed: "nothing matches" is not known then.
        else
          show =
            // Short terms search titles only: no "nothing matches" yet.
            term.length >= PASSAGE_MIN &&
            indexReady() &&
            !indexFailed &&
            passageTerm === term &&
            passageCount === 0 &&
            titleCount === 0 &&
            meaningCount === 0 &&
            !meaningPending;
      }
      if (show && !searching) empty.textContent = "No writers in this group yet.";
      else if (show)
        empty.innerHTML = `Nothing in the library matches “${escapeHtml(lastShown)}”. You can also try <a href="/topics/">Topics</a> or <a href="/scripture/">Scripture</a>.`;
      else if (empty.innerHTML !== emptyHtml) empty.innerHTML = emptyHtml;
      empty.hidden = !show;
    };

    // Semantic search (/api/search): debounced, latest answer wins, hidden
    // on error so exact-word results still stand alone.
    const meaningSearch = (term) => {
      if (!meaningHits || !meaningResults) return;
      clearTimeout(meaningTimer);
      if (term.length < 3) {
        ++meaningSeq;
        meaningCount = 0;
        meaningPending = false;
        meaningHits.hidden = true;
        meaningResults.innerHTML = "";
        return;
      }
      meaningPending = true;
      // Bump on scheduling, so an answer already in flight for an older
      // term is dropped.
      const seq = ++meaningSeq;
      meaningTimer = setTimeout(() => {
        fetch(`/api/search?q=${encodeURIComponent(term)}&n=20`)
          .then((r) => (r.ok ? r.json() : { results: [] }))
          .then((data) => {
            if (seq !== meaningSeq) return;
            const rows = (data && data.results) || [];
            meaningPending = false;
            meaningCount = rows.length;
            meaningHits.hidden = rows.length === 0;
            meaningResults.innerHTML = rows
              .map(
                (h) =>
                  `<li><a href="${escapeHtml(h.href)}"><strong>${escapeHtml(h.title)}</strong><span>${escapeHtml(
                    h.author || ""
                  )}</span><em class="meaning-snippet">${escapeHtml(h.snippet || "")}</em></a></li>`
              )
              .join("");
            refresh();
          })
          .catch(() => {
            if (seq !== meaningSeq) return;
            meaningPending = false;
            meaningCount = 0;
            meaningHits.hidden = true;
            refresh();
          });
      }, 350);
    };

    let lastVisible = [];
    const refresh = () => {
      writeStatus(lastTerm, lastVisible);
      updateEmpty(lastTerm, lastVisible);
    };

    // scan=false filters the writer list only (cheap, on every keystroke);
    // the passage scan runs on the debounced call.
    const apply = (scan = true) => {
      const term = (q && q.value ? q.value : "").trim().toLowerCase();
      const termChanged = term !== lastTerm;
      lastTerm = term;
      lastShown = (q && q.value ? q.value : "").trim();
      const searching = term.length >= 2;
      browse.classList.toggle("searching", searching);
      if (termChanged) titleExpanded = false;
      // A new search looks in every era: the era chips are hidden while a
      // term is in the box, so a leftover era must not narrow the results.
      if (searching && !wasSearching && filter !== "all") {
        filter = "all";
        browse.querySelectorAll("[data-filter]").forEach((b) => {
          b.setAttribute("aria-pressed", b.getAttribute("data-filter") === "all" ? "true" : "false");
        });
      }
      wasSearching = searching;
      // After a failed load, the next new term (debounced) tries once more.
      const wordSearch = term.length >= PASSAGE_MIN;
      if (scan && wordSearch && indexFailed && !indexPromise && term !== failedTerm) {
        searchIndex = null;
        indexFailed = false;
      }
      if (scan && wordSearch && !indexFailed && !termCovered(term) && !indexPromise) loadIndex(term);
      let visible = items().filter((li) => {
        if (!inFilter(li, filter)) return false;
        if (searching) {
          const blob = li.getAttribute("data-blob") || "";
          if (!blob.includes(term)) return false;
        }
        return true;
      });
      visible.sort((a, b) => {
        if (sort === "author") {
          return (a.getAttribute("data-author") || "").localeCompare(
            b.getAttribute("data-author") || "",
            undefined,
            { sensitivity: "base" }
          );
        }
        const ya = Number(a.getAttribute("data-year") || "9999");
        const yb = Number(b.getAttribute("data-year") || "9999");
        if (ya !== yb) return ya - yb;
        return (a.getAttribute("data-author") || "").localeCompare(
          b.getAttribute("data-author") || "",
          undefined,
          { sensitivity: "base" }
        );
      });
      // Touch only rows that change, and move rows only when the order
      // changes, so a focused row keeps focus when a later pass runs.
      const all = items();
      const shown = new Set(visible);
      all.forEach((li) => {
        const hide = !shown.has(li);
        if (li.hidden !== hide) li.hidden = hide;
      });
      const inDom = all.filter((li) => shown.has(li));
      if (!inDom.every((li, i) => li === visible[i])) visible.forEach((li) => list.appendChild(li));
      if (termChanged) meaningSearch(term);
      if (scan && passageTerm !== term) scanPassages(term, wordSearch);
      renderTitles(term, searching);
      if (writersH) writersH.hidden = !(searching && visible.length);
      lastVisible = visible;
      refresh();
    };

    const scanPassages = (term, searching) => {
      const ready = !searching || (termCovered(term) && !indexFailed);
      passageCount = 0;
      entryHits = new Map();
      passageTerm = !searching || ready || indexFailed ? term : null;
      if (passageHits && passageResults) {
        if (searching && ready) {
          const hits = [];
          for (const row of matchRows(term)) {
            passageCount++;
            if (hits.length < 40) hits.push(row);
            if (row.kind === "work") {
              const e = titleForRow(row);
              if (e) entryHits.set(e, (entryHits.get(e) || 0) + 1);
            }
          }
          passageHits.hidden = hits.length === 0;
          if (passageNote)
            passageNote.textContent =
              passageCount > 40 ? `${passageNoteText} The first 40 of ${passageCount.toLocaleString("en-US")} are listed.` : passageNoteText;
          passageResults.innerHTML = hits
            .map(
              (h) =>
                `<li><a href="${escapeHtml(h.href)}"><strong>${escapeHtml(h.title)}</strong><span>${escapeHtml(
                  h.author || h.kind || ""
                )}</span></a></li>`
            )
            .join("");
        } else {
          passageHits.hidden = true;
          passageResults.innerHTML = "";
        }
      }
    };

    // Era chips with nothing in them are hidden (build count, else the list).
    browse.querySelectorAll("[data-filter]").forEach((btn) => {
      const f = btn.getAttribute("data-filter") || "all";
      if (f === "all") return;
      const n = btn.hasAttribute("data-count")
        ? Number(btn.getAttribute("data-count"))
        : items().filter((li) => inFilter(li, f)).length;
      if (!n) btn.hidden = true;
    });

    browse.querySelectorAll("[data-sort]").forEach((btn) => {
      btn.addEventListener("click", () => {
        sort = btn.getAttribute("data-sort") || "chrono";
        browse.querySelectorAll("[data-sort]").forEach((b) => {
          b.setAttribute("aria-pressed", b === btn ? "true" : "false");
        });
        apply();
      });
    });
    browse.querySelectorAll("[data-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        filter = btn.getAttribute("data-filter") || "all";
        browse.querySelectorAll("[data-filter]").forEach((b) => {
          b.setAttribute("aria-pressed", b === btn ? "true" : "false");
        });
        apply();
      });
    });
    if (titleMore) {
      titleMore.addEventListener("click", () => {
        titleExpanded = true;
        renderTitles(lastTerm, lastTerm.length >= 2);
        const next = titleResults && titleResults.children[TITLE_CAP];
        if (next) next.querySelector("a")?.focus();
      });
    }
    if (q) {
      let inputTimer = 0;
      q.addEventListener("input", () => {
        clearTimeout(inputTimer);
        apply(false);
        inputTimer = setTimeout(apply, 150);
      });
      // Header and home search land here as /works/?q=…
      try {
        const term = new URLSearchParams(window.location.search).get("q");
        if (term) q.value = term;
      } catch {
        /* no query string */
      }
    }

    apply();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
