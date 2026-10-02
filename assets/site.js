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
    const paint = () => {
      themeBtn.textContent = isDark() ? "☀" : "☾";
      themeBtn.setAttribute("aria-pressed", isDark() ? "true" : "false");
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
    const paint = (rows) => {
      const map = new Map(rows.map(([v, t]) => [String(v), t]));
      text.querySelectorAll(".v").forEach((el) => {
        const t = map.get(el.dataset.v);
        if (t) el.querySelector(".vt").textContent = t;
      });
    };
    const useTr = async (key) => {
      if (!text) return;
      try {
        const btn = trButtons.find((b) => b.dataset.tr === key);
        if (key === "bsb") paint(original);
        else if (btn && btn.dataset.remote) {
          const r = await fetch(`https://bolls.life/get-text/${btn.dataset.remote}/${text.dataset.booknum}/${text.dataset.chap}/`);
          if (!r.ok) throw new Error("missing");
          const rows = await r.json();
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
          if (!r.ok) throw new Error("missing");
          paint(await r.json());
        }
        trButtons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.tr === key ? "true" : "false"));
        const credit = bx.querySelector(".bx-tr-credit");
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
        trButtons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.tr === "bsb" ? "true" : "false"));
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

  const q = document.querySelector("#q");
  const results = document.querySelector("#results");
  if (q && results) {
    let index = [];
    fetch("/data/search-index.json")
      .then((r) => r.json())
      .then((data) => {
        index = data;
        if (q.value) render(q.value);
      })
      .catch(() => {
        results.innerHTML = "<li>Search index unavailable.</li>";
      });

    const render = (term) => {
      const t = term.trim().toLowerCase();
      if (t.length < 2) {
        results.innerHTML = "";
        return;
      }
      const hits = [];
      for (const row of index) {
        const blob = `${row.title} ${row.author || ""} ${row.text || ""}`.toLowerCase();
        if (blob.includes(t)) hits.push(row);
        if (hits.length >= 40) break;
      }
      results.innerHTML = hits
        .map(
          (h) =>
            `<li><a href="${h.href}"><strong>${escapeHtml(h.title)}</strong><span>${escapeHtml(
              h.author || h.kind
            )}</span></a></li>`
        )
        .join("");
    };

    q.addEventListener("input", () => render(q.value));
  }

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
    const passageHits = browse.querySelector("#passage-hits");
    const passageResults = browse.querySelector("#passage-results");
    const workCount = Number(browse.getAttribute("data-work-count") || "0");
    const authorCount = Number(browse.getAttribute("data-author-count") || "0");
    let sort = "chrono";
    let filter = "all";
    let searchIndex = null;

    const items = () => Array.from(list.querySelectorAll(":scope > li.author-entry"));

    const apply = () => {
      const term = (q && q.value ? q.value : "").trim().toLowerCase();
      let visible = items().filter((li) => {
        if (filter === "oet" && li.getAttribute("data-oet") !== "1") return false;
        if (filter !== "all" && filter !== "oet") {
          const eras = (li.getAttribute("data-era") || "").split(/\s+/);
          if (!eras.includes(filter)) return false;
        }
        if (term.length >= 2) {
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
      items().forEach((li) => {
        li.hidden = true;
      });
      visible.forEach((li) => {
        li.hidden = false;
        list.appendChild(li);
      });
      const empty = browse.querySelector("#works-empty");
      if (empty) empty.hidden = !(term.length >= 2 && visible.length === 0);
      if (status) {
        const sortLabel = sort === "author" ? "author name" : "era (earliest first)";
        status.textContent = `${visible.length} of ${authorCount} authors · ${workCount} works · sorted by ${sortLabel}`;
      }
      if (passageHits && passageResults) {
        if (term.length >= 2 && searchIndex) {
          const hits = [];
          for (const row of searchIndex) {
            const blob = `${row.title || ""} ${row.author || ""} ${row.text || ""}`.toLowerCase();
            if (blob.includes(term)) hits.push(row);
            if (hits.length >= 40) break;
          }
          passageHits.hidden = hits.length === 0;
          passageResults.innerHTML = hits
            .map(
              (h) =>
                `<li><a href="${h.href}"><strong>${escapeHtml(h.title)}</strong><span>${escapeHtml(
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
    if (q) {
      q.addEventListener("input", () => apply());
      // Header and home search land here as /works/?q=…
      try {
        const term = new URLSearchParams(window.location.search).get("q");
        if (term) q.value = term;
      } catch {
        /* no query string */
      }
    }

    fetch("/data/search-index.json")
      .then((r) => r.json())
      .then((data) => {
        searchIndex = data;
        if (q && q.value) apply();
      })
      .catch(() => {
        searchIndex = [];
      });

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
