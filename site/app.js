(function () {
  "use strict";

  const MODES = {
    alpha: {
      label: "A–Z",
      group: f => f.letter,
      groupSort: (a, b) => (a === "#") - (b === "#") || a.localeCompare(b),
      heading: g => g === "#" ? "0–9 & symbols" : g,
      sort: (a, b) => a.alpha_key.localeCompare(b.alpha_key) || (a.year || 0) - (b.year || 0),
    },
    year: {
      label: "Year",
      group: f => (f.year == null ? "?" : String(f.year)),
      groupSort: (a, b) => (a === "?") - (b === "?") || Number(a) - Number(b),
      heading: g => g === "?" ? "Year unknown" : g,
      sort: (a, b) => a.alpha_key.localeCompare(b.alpha_key),
    },
    age: {
      label: "Age",
      group: f => (f.age == null ? "?" : String(f.age)),
      groupSort: (a, b) => (a === "?") - (b === "?") || Number(a) - Number(b),
      heading: g => g === "?" ? "Not yet rated" : `Ages ${g}+`,
      jump: g => g === "?" ? "?" : `${g}+`,
      sort: (a, b) => a.alpha_key.localeCompare(b.alpha_key),
    },
  };

  const $ = sel => document.querySelector(sel);
  const main = $("#main");
  const jump = $("#jump");
  let data = null;
  let mode = readMode();
  let filter = readFilter();

  // A fresh load always starts on A–Z with nothing filtered. Sort and filter
  // choices are deliberately not remembered across reloads.
  function readMode() { return "alpha"; }
  function readFilter() { return "all"; }

  function setMode(next) {
    mode = MODES[next] ? next : "alpha";
    document.querySelectorAll(".modes:not(.filters) button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
    render();
  }

  function setFilter(next) {
    filter = ["all", "unwatched", "watched"].includes(next) ? next : "all";
    document.querySelectorAll(".filters button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.filter === filter)));
    render();
  }

  function fmtDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return "";
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function slug(s) { return String(s).replace(/[^\w+]+/g, "-"); }

  function card(f) {
    const cats = Object.keys(data.categories);
    const sev = cats.map(k => {
      const v = f.parents_guide[k];
      return `<li data-sev="${esc(v || "")}" title="${esc(data.categories[k])}: ${esc(v || "unknown")}" aria-label="${esc(data.categories[k])}: ${esc(v || "unknown")}"><span aria-hidden="true">${esc(data.icons[k] || "")}</span></li>`;
    }).join("");
    const watched = f.watched
      ? `<span class="chip watched" title="Watched${f.watched_on ? " on " + esc(fmtDate(f.watched_on)) : ""}">${f.watched_on ? "Watched " + esc(fmtDate(f.watched_on)) : "Watched"}</span>`
      : "";
    const poster = f.poster
      ? `<img class="poster" src="${esc(f.poster)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'poster placeholder',textContent:'🎞'}))">`
      : `<div class="poster placeholder" aria-hidden="true">🎞</div>`;
    const title = f.imdb_url ? `<a href="${esc(f.imdb_url)}" rel="noopener">${esc(f.title)}</a>` : esc(f.title);
    const why = (f.age_reasons || []).join("\n");
    const ageChip = f.age == null
      ? `<span class="chip age unknown" title="${esc(why)}">age ?</span>`
      : `<span class="chip age${f.age_estimated ? " est" : ""}" title="${esc(why)}" tabindex="0">${f.age}+${f.age_estimated ? "<sup>~</sup>" : ""}</span>`;
    const kind = f.kind === "series" ? `<span class="chip kind">Series</span>` : "";
    const runtime = f.runtime_label ? `<span class="runtime">${esc(f.runtime_label)}</span>` : "";
    const imdbLink = f.imdb_url ? `<a class="imdb-link" href="${esc(f.imdb_url)}" rel="noopener">IMDb</a>` : "";
    const guideLink = f.parents_guide_url ? `<p class="links"><a href="${esc(f.parents_guide_url)}" rel="noopener">Parents Guide</a></p>` : "";
    const warn = f.status !== "ok"
      ? `<p class="warn">${f.status === "error" ? "Lookup failed: " + esc(f.error) : "Not fetched yet"}</p>`
      : (f.error ? `<p class="warn">${esc(f.error)}</p>` : "");
    return `<article class="card ${esc(f.status)}${f.watched ? " is-watched" : ""}">
      <div class="side">${poster}${imdbLink}</div>
      <div>
        <h3>${title}</h3>
        <p class="meta">${f.year_label ? `<span>${esc(f.year_label)}</span>` : ""}${runtime}${f.rated ? `<span class="chip">${esc(f.rated)}</span>` : ""}${ageChip}${kind}${watched}</p>
        ${f.synopsis ? `<p class="synopsis">${esc(f.synopsis)}</p>` : ""}
        ${guideLink}
        <ul class="sev" aria-label="Parents Guide severities">${sev}</ul>
        ${warn}
      </div>
    </article>`;
  }

  function render() {
    const m = MODES[mode];
    const films = data.films.filter(f => filter === "all" || (filter === "watched") === !!f.watched);
    const groups = new Map();
    for (const f of films) {
      const g = m.group(f);
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(f);
    }
    const keys = Array.from(groups.keys()).sort(m.groupSort);
    jump.innerHTML = `<ul>${keys.map(k =>
      `<li><a href="#${mode}-${slug(k)}" data-target="${mode}-${slug(k)}">${esc(m.jump ? m.jump(k) : m.heading(k))}</a></li>`).join("")}</ul>`;
    // Scroll without leaving a hash in the URL, so a refresh starts clean.
    jump.querySelectorAll("a").forEach(a => a.addEventListener("click", ev => {
      ev.preventDefault();
      const el = document.getElementById(a.dataset.target);
      if (el) el.scrollIntoView({ block: "start" });
    }));
    if (!films.length) {
      main.innerHTML = filter === "all"
        ? `<p class="empty">No films yet. Add a title to <code>list.md</code>.</p>`
        : `<p class="empty">Nothing ${filter === "watched" ? "watched yet" : "unwatched"}.</p>`;
      return;
    }
    main.innerHTML = keys.map(k => {
      const items = groups.get(k).sort(m.sort);
      return `<section class="group" id="${mode}-${slug(k)}">
        <h2>${esc(m.heading(k))} <small>${items.length}</small></h2>
        <div class="grid">${items.map(card).join("")}</div>
      </section>`;
    }).join("");
  }

  document.querySelectorAll(".modes:not(.filters) button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode)));
  document.querySelectorAll(".filters button").forEach(b => b.addEventListener("click", () => setFilter(b.dataset.filter)));

  function renderLegend() {
    const cats = Object.keys(data.categories);
    const names = cats.map(k => `<span>${esc(data.icons[k] || "")} ${esc(data.categories[k])}</span>`).join("");
    const levels = ["None", "Mild", "Moderate", "Severe"].map(l => `<span><i class="swatch" style="background:var(--sev-${l.toLowerCase()})"></i>${l}</span>`).join("");
    $("#legend").innerHTML = `<div class="legend-row">${names}</div><div class="legend-row">${levels}</div>`;
  }

  // films.json is refetched with a cache-busting query so a new deploy shows up
  // on a normal reload even though Pages caches assets for ten minutes.
  fetch("films.json?t=" + Math.floor(Date.now() / 60000), { cache: "no-cache" })
    .then(r => { if (!r.ok) throw new Error(r.status + " " + r.statusText); return r.json(); })
    .then(json => {
      data = json;
      const n = data.films.length, w = data.films.filter(f => f.watched).length;
      $("#foot-note").textContent = `${n} film${n === 1 ? "" : "s"}, ${w} watched · data refreshed ${data.generated_at} · ages are computed from the MPAA rating, IMDb Parents Guide severities, genre and runtime; see the repo for the model.`;
      renderLegend();
      document.querySelectorAll(".filters button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.filter === filter)));
      setMode(mode);
    })
    .catch(err => { main.innerHTML = `<p class="empty">Could not load films.json (${esc(err.message)}).</p>`; });
})();
