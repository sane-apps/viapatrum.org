(() => {
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector("#site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

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
    if (q) q.addEventListener("input", () => apply());

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
