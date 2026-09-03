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

  function readMode() {
    const fromHash = (location.hash.match(/^#(alpha|year|age)\b/) || [])[1];
    if (fromHash) return fromHash;
    try { const m = localStorage.getItem("movindi.mode"); if (MODES[m]) return m; } catch (e) { /* ignore */ }
    return "alpha";
  }

  function setMode(next, push) {
    mode = MODES[next] ? next : "alpha";
    try { localStorage.setItem("movindi.mode", mode); } catch (e) { /* ignore */ }
    document.querySelectorAll(".modes button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
    if (push) history.replaceState(null, "", "#" + mode);
    render();
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function slug(s) { return String(s).replace(/[^\w+]+/g, "-"); }

  function card(f) {
    const cats = Object.keys(data.categories);
    const sev = cats.map(k => {
      const v = f.parents_guide[k];
      return `<li data-sev="${esc(v || "")}" title="${esc(data.categories[k])}: ${esc(v || "unknown")}"></li>`;
    }).join("");
    const poster = f.poster
      ? `<img class="poster" src="${esc(f.poster)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'poster placeholder',textContent:'🎞'}))">`
      : `<div class="poster placeholder" aria-hidden="true">🎞</div>`;
    const title = f.imdb_url ? `<a href="${esc(f.imdb_url)}" rel="noopener">${esc(f.title)}</a>` : esc(f.title);
    const ageChip = f.age == null
      ? `<span class="chip age unknown">age ?</span>`
      : `<span class="chip age">${f.age}+</span>`;
    const series = f.series ? `<span class="chip">${esc(f.series)}${f.series_order ? " " + f.series_order : ""}</span>` : "";
    const links = [
      f.imdb_url ? `<a href="${esc(f.imdb_url)}" rel="noopener">IMDb</a>` : "",
      f.parents_guide_url ? `<a href="${esc(f.parents_guide_url)}" rel="noopener">Parents Guide</a>` : "",
    ].filter(Boolean).join("");
    const warn = f.status !== "ok"
      ? `<p class="warn">${f.status === "error" ? "Lookup failed: " + esc(f.error) : "Not fetched yet"}</p>`
      : (f.error ? `<p class="warn">${esc(f.error)}</p>` : "");
    return `<article class="card ${esc(f.status)}">
      ${poster}
      <div>
        <h3>${title}</h3>
        <p class="meta">${f.year ? `<span>${f.year}</span>` : ""}${f.rated ? `<span class="chip">${esc(f.rated)}</span>` : ""}${ageChip}${series}</p>
        ${f.synopsis ? `<p class="synopsis">${esc(f.synopsis)}</p>` : ""}
        <ul class="sev" aria-label="Parents Guide severities">${sev}</ul>
        ${f.age_reasons && f.age_reasons.length ? `<p class="why">${esc(f.age_reasons.join(" · "))}</p>` : ""}
        <p class="links">${links}</p>
        ${warn}
      </div>
    </article>`;
  }

  function render() {
    const m = MODES[mode];
    const films = data.films.slice();
    const groups = new Map();
    for (const f of films) {
      const g = m.group(f);
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(f);
    }
    const keys = Array.from(groups.keys()).sort(m.groupSort);
    jump.innerHTML = `<ul>${keys.map(k =>
      `<li><a href="#${mode}-${slug(k)}">${esc(m.jump ? m.jump(k) : m.heading(k))}</a></li>`).join("")}</ul>`;
    if (!films.length) {
      main.innerHTML = `<p class="empty">No films yet. Add a title to <code>list.md</code>.</p>`;
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

  document.querySelectorAll(".modes button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode, true)));
  window.addEventListener("hashchange", () => {
    const next = (location.hash.match(/^#(alpha|year|age)\b/) || [])[1];
    if (next && next !== mode) setMode(next, false);
  });

  fetch("films.json", { cache: "no-cache" })
    .then(r => { if (!r.ok) throw new Error(r.status + " " + r.statusText); return r.json(); })
    .then(json => {
      data = json;
      const n = data.films.length;
      $("#foot-note").textContent = `${n} film${n === 1 ? "" : "s"} · data refreshed ${data.generated_at} · ages are computed from the MPAA rating and IMDb Parents Guide severities, see the repo for the rules.`;
      setMode(mode, false);
      if (location.hash && location.hash.includes("-")) {
        const el = document.getElementById(location.hash.slice(1));
        if (el) el.scrollIntoView();
      }
    })
    .catch(err => { main.innerHTML = `<p class="empty">Could not load films.json (${esc(err.message)}).</p>`; });
})();
