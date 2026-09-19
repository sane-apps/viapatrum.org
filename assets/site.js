(() => {
  document.documentElement.classList.add("js");

  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector("#site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  if (toggle && nav) {
    const closeMenu = () => {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    };
    nav.addEventListener("click", (event) => { if (event.target.closest("a")) closeMenu(); });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && nav.classList.contains("is-open")) {
        closeMenu();
        toggle.focus();
      }
    });
  }
  const header = document.querySelector(".site-header");
  if (header && "ResizeObserver" in window) {
    new ResizeObserver(() => {
      const sticky = getComputedStyle(header).position === "sticky";
      document.documentElement.style.setProperty("--header-offset", `${sticky ? header.offsetHeight + 16 : 16}px`);
    }).observe(header);
  }
  document.querySelectorAll('a[href="#contents"]').forEach((link) => {
    link.addEventListener("click", () => {
      const contents = document.getElementById("contents");
      if (contents instanceof HTMLDetailsElement) contents.open = true;
    });
  });

  // Works catalog: find + sort + era/OET filters (Search tab merged here).
  const worksRoot = document.querySelector("[data-works-browse]");
  if (worksRoot) {
    const list = worksRoot.querySelector("#works-list");
    const status = worksRoot.querySelector("#works-status");
    const qInput = worksRoot.querySelector("#works-q");
    const passageSec = worksRoot.querySelector("#passage-hits");
    const passageList = worksRoot.querySelector("#passage-results");
    const sortBtns = [...worksRoot.querySelectorAll(".works-sort [data-sort]")];
    const filterBtns = [...worksRoot.querySelectorAll(".works-filters [data-filter]")];
    let sort = "chrono";
    let filter = "all";
    let index = [];
    let indexReady = false;
    let indexError = false;
    let indexLoading = false;

    const params = new URLSearchParams(location.search);
    if (["chrono", "author", "title"].includes(params.get("sort") || "")) {
      sort = params.get("sort");
    }
    if (filterBtns.some(b => b.dataset.filter === params.get("filter"))) filter = params.get("filter");
    if (params.get("q") && qInput) qInput.value = params.get("q");
    if (filterBtns.some((b) => b.dataset.filter === "oet") && (location.hash === "#original-english" || location.hash === "#no-prior-english")) {
      filter = "oet";
    }

    const setPressed = (btns, attr, value) => {
      btns.forEach((b) => b.setAttribute("aria-pressed", b.getAttribute(attr) === value ? "true" : "false"));
    };
    setPressed(sortBtns, "data-sort", sort);
    setPressed(filterBtns, "data-filter", filter);

    const syncUrl = () => {
      const next = new URLSearchParams();
      if (sort !== "chrono") next.set("sort", sort);
      if (filter !== "all") next.set("filter", filter);
      const qv = (qInput?.value || "").trim();
      if (qv) next.set("q", qv);
      const qs = next.toString();
      const url = qs ? `${location.pathname}?${qs}` : location.pathname;
      history.replaceState(null, "", url + (filter === "oet" && !qv ? "#original-english" : ""));
    };

    const sortItems = (items) => {
      const arr = [...items];
      arr.sort((a, b) => {
        if (sort === "author") {
          const ya = Number(a.dataset.year || 9999);
          const yb = Number(b.dataset.year || 9999);
          return (
            ya - yb ||
            (a.dataset.author || "").localeCompare(b.dataset.author || "", undefined, { sensitivity: "base", numeric: true }) ||
            (a.dataset.title || "").localeCompare(b.dataset.title || "", undefined, { sensitivity: "base", numeric: true })
          );
        }
        if (sort === "title") {
          return (a.dataset.title || "").localeCompare(b.dataset.title || "", undefined, { sensitivity: "base", numeric: true });
        }
        const ya = Number(a.dataset.year || 9999);
        const yb = Number(b.dataset.year || 9999);
        return ya - yb || (a.dataset.author || "").localeCompare(b.dataset.author || "", undefined, { sensitivity: "base", numeric: true });
      });
      return arr;
    };

    const apply = () => {
      if (!list) return;
      const term = (qInput?.value || "").trim().toLowerCase();
      list.querySelectorAll(".author-group").forEach((heading) => heading.remove());
      const items = [...list.querySelectorAll(":scope > li.work-entry")];
      list.classList.toggle("is-grouped", sort !== "title");
      let previousAuthor = null;
      let shown = 0;
      for (const li of sortItems(items)) {
        list.appendChild(li);
        const blob = li.dataset.blob || "";
        const era = li.dataset.era || "";
        const oet = li.dataset.oet === "1";
        let ok = true;
        if (filter === "oet") ok = oet;
        else if (filter !== "all") ok = era === filter;
        if (ok && term.length >= 2) ok = blob.includes(term);
        else if (ok && term.length === 1) ok = blob.includes(term);
        li.hidden = !ok;
        if (ok) {
          shown += 1;
          if (sort !== "title" && li.dataset.author !== previousAuthor) {
            const group = document.createElement("li");
            group.className = "author-group";
            const heading = document.createElement("h2");
            const author = document.createElement("a");
            author.href = li.dataset.authorHref;
            author.textContent = li.dataset.author;
            heading.appendChild(author);
            group.appendChild(heading);
            if (li.dataset.period) {
              const period = document.createElement("span");
              period.className = "author-dates author-period";
              period.textContent = li.dataset.period;
              group.appendChild(period);
            }
            list.insertBefore(group, li);
            previousAuthor = li.dataset.author;
          }
        }
      }
      const sortLabel =
        sort === "author" ? "author (earliest first)" : sort === "title" ? "work title" : "author era (earliest first)";
      const filterLabel =
        filter === "oet" ? "Original English only" : filter === "all" ? "all eras" : filter;
      if (status) {
        status.textContent = `${shown} work${shown === 1 ? "" : "s"} · sorted by ${sortLabel} · ${filterLabel}`;
      }
      let empty = worksRoot.querySelector(".search-empty");
      if (!empty) {
        empty = document.createElement("p");
        empty.className = "search-empty";
        empty.textContent = "No matching works. Try another word or select All to clear the era filter.";
        list.after(empty);
      }
      empty.hidden = shown > 0;
      syncUrl();
      renderPassages(term);
    };

    const escapeHtml = (s) =>
      String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");

    const renderPassages = (term) => {
      if (!passageSec || !passageList) return;
      if (!term || term.length < 2) {
        passageSec.hidden = true;
        passageList.innerHTML = "";
        return;
      }
      if (indexError) {
        passageSec.hidden = false;
        passageList.innerHTML = '<li class="search-hint">Passage search could not load. <button type="button" class="search-retry">Try again</button></li>';
        passageList.querySelector("button").addEventListener("click", loadIndex);
        return;
      }
      if (!indexReady) {
        passageSec.hidden = false;
        passageList.innerHTML = '<li class="search-hint">Loading passages…</li>';
        if (!indexLoading) loadIndex();
        return;
      }
      const hits = [];
      for (const row of index) {
        // Work records are individual passages, not catalog entries.
        const blob = `${row.title} ${row.author || ""} ${row.text || ""}`.toLowerCase();
        if (blob.includes(term)) hits.push(row);
        if (hits.length >= 30) break;
      }
      if (!hits.length) {
        passageSec.hidden = false;
        passageList.innerHTML = '<li class="search-hint">No matching passages. Try a shorter phrase.</li>';
        return;
      }
      passageSec.hidden = false;
      passageList.innerHTML = hits
        .map(
          (h) =>
            `<li><a href="${escapeHtml(h.href)}"><strong>${escapeHtml(h.title)}</strong><span>${escapeHtml(
              h.author || h.kind
            )}</span></a></li>`
        )
        .join("");
    };

    function loadIndex() {
      indexLoading = true;
      indexReady = false;
      indexError = false;
      renderPassages((qInput?.value || "").trim().toLowerCase());
      fetch("/data/search-index.json")
        .then((r) => {
          if (!r.ok) throw new Error("Search unavailable");
          return r.json();
        })
        .then((data) => {
          if (!Array.isArray(data)) throw new Error("Invalid search index");
          index = data;
          indexReady = true;
          indexLoading = false;
          apply();
        })
        .catch(() => {
          indexError = true;
          indexLoading = false;
          apply();
        });
    }

    sortBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        sort = btn.getAttribute("data-sort") || "chrono";
        setPressed(sortBtns, "data-sort", sort);
        apply();
      });
    });
    filterBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        filter = btn.getAttribute("data-filter") || "all";
        setPressed(filterBtns, "data-filter", filter);
        apply();
      });
    });
    qInput?.addEventListener("input", () => apply());
    apply();
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

  // Reader Contents: highlight the passage currently in view.
  const tocRoot = document.querySelector(".reader-rail .toc, #contents .toc");
  if (tocRoot) {
    const links = [...tocRoot.querySelectorAll('a[href*="#s"]')];
    const entries = links
      .map((link) => {
        const hash = (link.getAttribute("href") || "").split("#")[1];
        if (!hash) return null;
        const target = document.getElementById(hash);
        return target ? { link, target } : null;
      })
      .filter(Boolean);

    const contents = tocRoot.closest(".reader-contents") || document.querySelector("#contents");
    const meta = contents?.querySelector(".toc-summary-meta");
    let hereEl = meta?.querySelector(".toc-here");
    if (meta && !hereEl) {
      hereEl = document.createElement("span");
      hereEl.className = "toc-here";
      hereEl.setAttribute("aria-live", "polite");
      meta.appendChild(hereEl);
    }

    // While the pointer is in Contents, do not auto-scroll the rail —
    // rail motion under a moving mouse leaves ghost hover / stuck highlights.
    let pointerInToc = false;
    // After a TOC click, freeze rail follow + current highlight until the page
    // jump settles — otherwise smooth page scroll makes scrollspy walk every
    // intermediate row (and inherited smooth rail scroll stacks into chaos).
    let railFollowUntil = 0;
    let lockedLink = null;
    tocRoot.addEventListener("pointerenter", () => {
      pointerInToc = true;
    });
    tocRoot.addEventListener("pointerleave", () => {
      pointerInToc = false;
    });

    const snapRailTo = (active) => {
      if (!active || !tocRoot.closest(".reader-rail")) return;
      const rail = tocRoot;
      const row = active.closest("li");
      if (!row) return;
      const prev = rail.style.scrollBehavior;
      rail.style.scrollBehavior = "auto";
      const rowTop = row.getBoundingClientRect().top - rail.getBoundingClientRect().top + rail.scrollTop;
      const rowBottom = rowTop + row.offsetHeight;
      const viewTop = rail.scrollTop;
      const viewBottom = viewTop + rail.clientHeight;
      if (rowTop < viewTop + 8) rail.scrollTop = Math.max(0, rowTop - 12);
      else if (rowBottom > viewBottom - 8) rail.scrollTop = rowBottom - rail.clientHeight + 12;
      rail.style.scrollBehavior = prev;
    };

    const setCurrent = (active, { followRail = true } = {}) => {
      let idx = -1;
      for (let i = 0; i < entries.length; i++) {
        const { link, target } = entries[i];
        const on = link === active;
        link.classList.toggle("is-current", on);
        if (on) {
          link.setAttribute("aria-current", "location");
          idx = i;
        } else {
          link.removeAttribute("aria-current");
        }
        const sec = target.closest(".reader-sec");
        if (sec) sec.classList.toggle("is-current", on);
      }
      if (hereEl && idx >= 0) {
        hereEl.textContent = `Here · ${idx + 1} of ${entries.length}`;
      }
      if (!followRail) return;
      if (pointerInToc || tocRoot.contains(document.activeElement)) return;
      if (Date.now() < railFollowUntil) return;
      snapRailTo(active);
    };

    if (entries.length) {
      const pick = () => {
        if (Date.now() < railFollowUntil && lockedLink) {
          setCurrent(lockedLink, { followRail: false });
          return;
        }
        lockedLink = null;
        const probe = window.scrollY + Math.min(160, window.innerHeight * 0.28);
        let current = entries[0];
        for (const entry of entries) {
          const top = entry.target.getBoundingClientRect().top + window.scrollY;
          if (top <= probe) current = entry;
          else break;
        }
        setCurrent(current.link);
      };

      let ticking = false;
      const onScroll = () => {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(() => {
          pick();
          ticking = false;
        });
      };
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
      pick();

      tocRoot.addEventListener("click", (ev) => {
        const a = ev.target.closest('a[href*="#s"]');
        if (!a || !tocRoot.contains(a)) return;
        // Highlight + snap rail once, now. Keep rail still while the page scrolls.
        lockedLink = a;
        railFollowUntil = Date.now() + 900;
        setCurrent(a, { followRail: false });
        snapRailTo(a);
      });
    }
  }

  // Contents ↑ control: appear after the reader has been scrolled a bit.
  const topBtn = document.querySelector(".reader-top");
  if (topBtn) {
    const syncTop = () => {
      const show = window.scrollY > Math.min(420, window.innerHeight * 0.55);
      topBtn.tabIndex = show ? 0 : -1;
      topBtn.classList.toggle("is-visible", show);
    };
    let topTick = false;
    window.addEventListener(
      "scroll",
      () => {
        if (topTick) return;
        topTick = true;
        window.requestAnimationFrame(() => {
          syncTop();
          topTick = false;
        });
      },
      { passive: true }
    );
    syncTop();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
