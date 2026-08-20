/* crowdsec-card - Lovelace card for the CrowdSec LAPI integration.
 * Served and registered automatically by the integration; no manual resource
 * needed. Usage: `type: custom:crowdsec-card` (all options optional).
 */
import { WORLD, WORLD_VIEWBOX } from "./world-map.js";

/* Sequential ramps, one hue each, monotonic lightness, CVD-checked
 * (light and dark variants validated separately). */
const PALETTES = {
  menace: {
    light: ["#f7dcc9", "#eda36c", "#d9752f", "#a94e17", "#753208"],
    dark: ["#45220e", "#7c3a13", "#b25a1e", "#e08034", "#ffb376"],
  },
  ocean: {
    light: ["#dbe7f6", "#a9c6e8", "#6f9fd4", "#3f73b4", "#1e4c85"],
    dark: ["#14304f", "#2a4f7e", "#4a77ad", "#7ba3d6", "#b7d1f2"],
  },
  amethyste: {
    light: ["#ecdff5", "#cfb0e4", "#ab7fce", "#8351b3", "#5b3387"],
    dark: ["#33204d", "#503677", "#7257a4", "#9a7fd0", "#c8b2f0"],
  },
};
const ZERO = { light: "#ececef", dark: "#2b2b2f" };

const STRINGS = {
  fr: {
    subtitle: (b, i, p) => `${b} ban${b > 1 ? "s" : ""} actif${b > 1 ? "s" : ""} · ${i} IP · ${p} pays`,
    manual: "manuel",
    remaining: "restant",
    top: "Top pays",
    empty: "Aucun ban actif",
    missing: (e) => `Entité introuvable : ${e}`,
    bans: (n) => `${n} ban${n > 1 ? "s" : ""}`,
    filterHint: "Cliquer sur un pays filtre la liste",
    legend20: "20 et +",
  },
  en: {
    subtitle: (b, i, p) => `${b} active ban${b > 1 ? "s" : ""} · ${i} IP${i > 1 ? "s" : ""} · ${p} countr${p > 1 ? "ies" : "y"}`,
    manual: "manual",
    remaining: "left",
    top: "Top countries",
    empty: "No active ban",
    missing: (e) => `Entity not found: ${e}`,
    bans: (n) => `${n} ban${n > 1 ? "s" : ""}`,
    filterHint: "Click a country to filter the list",
    legend20: "20+",
  },
};

const BIN_LABELS = ["0", "1", "2–4", "5–9", "10–19"];

function bin(count, steps, zero) {
  if (!count) return zero;
  if (count >= 20) return steps[4];
  if (count >= 10) return steps[3];
  if (count >= 5) return steps[2];
  if (count >= 2) return steps[1];
  return steps[0];
}

function tint(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function parseDuration(str) {
  const m = /^(-)?(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?$/.exec(str || "");
  if (!m || (m[2] === undefined && m[3] === undefined && m[4] === undefined)) return null;
  const sec = (+m[2] || 0) * 3600 + (+m[3] || 0) * 60 + (+m[4] || 0);
  return m[1] ? -sec : sec;
}

function fmtRemaining(sec) {
  if (sec === null || sec < 0) return "";
  if (sec < 60) return "< 1 min";
  if (sec < 3600) return `${Math.floor(sec / 60)} min`;
  const h = Math.floor(sec / 3600);
  const mn = Math.floor((sec % 3600) / 60);
  return `${h} h ${String(mn).padStart(2, "0")}`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fireEvent(node, type, detail) {
  node.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
}

const SHIELD = `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z"></path></svg>`;

class CrowdsecCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("crowdsec-card-editor");
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass?.states || {}).find(
      (e) => e.startsWith("sensor.") && hass.states[e].attributes?.decisions !== undefined
    );
    return { entity: entity || "sensor.crowdsec_active_decisions" };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._filter = null;
    this._wide = false;
  }

  setConfig(config) {
    this._config = { show_map: true, palette: "menace", view: "auto", ...config };
    this._filter = null;
    this._invalidate();
  }

  set hass(hass) {
    const entity = this._entityId(hass);
    const stateObj = hass.states[entity];
    const dark = !!hass.themes?.darkMode;
    const changed =
      stateObj !== this._stateObj || dark !== this._dark || hass.language !== this._lang;
    this._hass = hass;
    this._stateObj = stateObj;
    this._dark = dark;
    this._lang = hass.language;
    if (this._editor) this._editor.hass = hass;
    if (changed) this._invalidate();
  }

  connectedCallback() {
    this._ro = new ResizeObserver(() => {
      const wide = this.offsetWidth >= 640;
      if (wide !== this._wide) {
        this._wide = wide;
        this._invalidate();
      }
    });
    this._ro.observe(this);
    this._invalidate();
  }

  disconnectedCallback() {
    if (this._ro) this._ro.disconnect();
  }

  getCardSize() {
    return 6;
  }

  _entityId(hass) {
    if (this._config?.entity) return this._config.entity;
    if (this._autoEntity && hass.states[this._autoEntity]) return this._autoEntity;
    this._autoEntity = Object.keys(hass?.states || {}).find(
      (e) => e.startsWith("sensor.") && hass.states[e].attributes?.decisions !== undefined
    );
    return this._autoEntity || "sensor.crowdsec_active_decisions";
  }

  _t() {
    return STRINGS[(this._lang || "en").startsWith("fr") ? "fr" : "en"];
  }

  _countryName(cc) {
    try {
      if (!this._names) this._names = new Intl.DisplayNames([this._lang || "en"], { type: "region" });
      return this._names.of(cc) || cc;
    } catch (e) {
      return cc;
    }
  }

  _invalidate() {
    if (this._pending) return;
    this._pending = true;
    Promise.resolve().then(() => {
      this._pending = false;
      this._render();
    });
  }

  _render() {
    if (!this._config || !this._hass || !this.isConnected) return;
    const t = this._t();
    const stateObj = this._stateObj;
    if (!stateObj) {
      this.shadowRoot.innerHTML =
        `<ha-card style="padding:16px;color:var(--primary-text-color)">` +
        `${esc(t.missing(this._entityId(this._hass)))}</ha-card>`;
      return;
    }

    const decisions = (stateObj.attributes.decisions || []).map((d) => ({
      ...d,
      _remaining: parseDuration(d.duration),
    }));
    decisions.sort((a, b) => (b._remaining ?? -1) - (a._remaining ?? -1));

    const counts = {};
    for (const d of decisions) {
      if (d.country) counts[d.country] = (counts[d.country] || 0) + 1;
    }
    const countryCount = Object.keys(counts).length;
    const ipCount = new Set(decisions.map((d) => d.value)).size;
    const steps = (PALETTES[this._config.palette] || PALETTES.menace)[this._dark ? "dark" : "light"];
    const zero = ZERO[this._dark ? "dark" : "light"];
    const accent = steps[this._dark ? 4 : 3];
    const accentBg = tint(accent, this._dark ? 0.14 : 0.12);
    const showMap = this._config.show_map !== false;
    const viewCfg = showMap ? this._config.view || "auto" : "list";
    const wide = this._wide && viewCfg === "auto";

    const style = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        .cols { display: flex; gap: 16px; }
        .col-list { display: flex; flex-direction: column; gap: 12px; flex: 1 1 0; min-width: 0; }
        .col-map { display: flex; flex-direction: column; gap: 10px; flex: 1 1 0; min-width: 0; }
        .vsep { width: 1px; align-self: stretch; background: var(--divider-color); }
        .header { display: flex; align-items: center; gap: 12px; }
        .icon-tile { width: 38px; height: 38px; border-radius: 10px; background: ${accentBg};
          display: flex; align-items: center; justify-content: center; color: ${accent}; }
        .icon-tile svg { stroke: ${accent}; }
        .titles { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
        .title { font-size: 15px; font-weight: 500; color: var(--primary-text-color); }
        .subtitle { font-size: 12px; color: var(--secondary-text-color); }
        .rows { display: flex; flex-direction: column; max-height: 336px; overflow-y: auto; }
        .row { display: flex; align-items: center; gap: 12px; padding: 9px 2px; }
        .row + .row { border-top: 1px solid var(--divider-color); }
        .flag { width: 21px; height: 15px; border-radius: 2px; object-fit: cover; flex: 0 0 auto;
          box-shadow: inset 0 0 0 1px var(--divider-color); background: var(--secondary-background-color); }
        .flag-fallback { width: 21px; height: 15px; border-radius: 2px; flex: 0 0 auto; font-size: 8px;
          font-weight: 700; display: inline-flex; align-items: center; justify-content: center;
          background: var(--secondary-background-color); color: var(--secondary-text-color); }
        .row-main { display: flex; flex-direction: column; gap: 2px; flex: 1 1 auto; min-width: 0; }
        .ip-line { display: flex; align-items: center; gap: 6px; min-width: 0; }
        .ip { font-family: var(--code-font-family, ui-monospace, monospace); font-size: 13px; font-weight: 500;
          color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .chip { font-size: 10px; font-weight: 600; line-height: 16px; padding: 0 5px; border-radius: 8px;
          background: ${accentBg}; color: ${accent}; flex: 0 0 auto; }
        .chip-alt { background: transparent; border: 1px solid var(--divider-color);
          color: var(--secondary-text-color); line-height: 14px; font-weight: 500; }
        .row-sub { font-size: 11.5px; line-height: 1.35; color: var(--secondary-text-color); }
        .row-right { display: flex; flex-direction: column; gap: 2px; align-items: flex-end; flex: 0 0 auto; }
        .left { font-size: 12.5px; font-weight: 500; color: var(--primary-text-color); }
        .left-sub { font-size: 10.5px; color: var(--secondary-text-color); opacity: 0.8; }
        .empty { padding: 24px 0; text-align: center; font-size: 13px; color: var(--secondary-text-color); }
        .map-wrap { position: relative; }
        .map-wrap svg { display: block; width: 100%; height: auto; }
        .map-wrap path { transition: fill-opacity 0.1s ease; }
        .map-wrap path.hit { cursor: pointer; }
        .map-wrap path.dim { fill-opacity: 0.35; }
        .tooltip { position: absolute; display: none; pointer-events: none; padding: 5px 10px; border-radius: 8px;
          background: ${this._dark ? "#383838" : "#212121"}; color: #fff; font-size: 12px; white-space: nowrap;
          box-shadow: 0 2px 8px rgba(0,0,0,0.35); z-index: 1; }
        .tooltip b { font-weight: 500; }
        .tooltip span { color: ${this._dark ? "#b5b5b5" : "#bdbdbd"}; }
        .legend { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .legend div { display: flex; align-items: center; gap: 4px; }
        .legend span.sw { width: 14px; height: 10px; border-radius: 2px; display: inline-block; }
        .legend span.lb { font-size: 10.5px; color: var(--secondary-text-color); }
        .top { display: flex; flex-direction: column; gap: 8px; padding-top: 4px; }
        .top-title { font-size: 11px; font-weight: 500; letter-spacing: 0.5px; text-transform: uppercase;
          color: var(--secondary-text-color); opacity: 0.85; }
        .top-row { display: flex; align-items: center; gap: 10px; }
        .top-row .flag, .top-row .flag-fallback { width: 18px; height: 13px; }
        .top-name { font-size: 13px; color: var(--primary-text-color); flex: 0 0 84px; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; }
        .bar { flex: 1 1 auto; height: 4px; border-radius: 2px; background: var(--secondary-background-color); }
        .bar div { height: 4px; border-radius: 2px; background: ${steps[3]}; }
        .top-count { font-size: 12.5px; font-weight: 500; color: var(--primary-text-color); flex: 0 0 22px;
          text-align: right; }
      </style>`;

    // Only well-formed ISO alpha-2 codes reach the img markup (and its inline
    // onerror handler); anything else renders as an inert text chip.
    const flag = (cc) => {
      if (!/^[a-z]{2}$/i.test(cc || "")) return `<span class="flag-fallback">${esc(cc || "?")}</span>`;
      const up = cc.toUpperCase();
      return `<img class="flag" loading="lazy" src="https://flagcdn.com/w40/${cc.toLowerCase()}.png"
        alt="${up}" onerror="this.outerHTML='<span class=&quot;flag-fallback&quot;>${up}</span>'">`;
    };

    // An explicitly empty title (title: "") hides the whole header.
    const titleCfg = this._config.title;
    const header = titleCfg === "" || titleCfg === false || titleCfg === null
      ? ""
      : `
      <div class="header">
        <div class="icon-tile">${SHIELD}</div>
        <div class="titles">
          <span class="title">${esc(titleCfg || "CrowdSec")}</span>
          <span class="subtitle">${esc(t.subtitle(decisions.length, ipCount, countryCount))}</span>
        </div>
      </div>`;

    const shown = this._filter ? decisions.filter((d) => d.country === this._filter) : decisions;
    // One row per IP: scenarios aggregated, longest remaining time kept.
    // Input is sorted by remaining desc, so groups inherit that order.
    const groups = [];
    const byIp = new Map();
    for (const d of shown) {
      let g = byIp.get(d.value);
      if (!g) {
        g = { value: d.value, country: d.country, scenarios: [], types: [], manual: false, count: 0, remaining: null };
        byIp.set(d.value, g);
        groups.push(g);
      }
      g.count += 1;
      if (!g.country && d.country) g.country = d.country;
      const sc = (d.scenario || "").split("/").pop();
      if (sc && !g.scenarios.includes(sc)) g.scenarios.push(sc);
      // Every decision type gets its badge; manual (cscli) bans get one more.
      if (d.type && !g.types.includes(d.type)) g.types.push(d.type);
      if (d.origin === "cscli") g.manual = true;
      if (d._remaining !== null && (g.remaining === null || d._remaining > g.remaining)) g.remaining = d._remaining;
    }
    const rows = groups.length
      ? `<div class="rows">${groups
          .map((g) => {
            const sub = [g.country ? this._countryName(g.country) : null, ...g.scenarios]
              .filter(Boolean)
              .join(" · ");
            const rem = fmtRemaining(g.remaining);
            return `<div class="row">
              ${flag(g.country)}
              <div class="row-main">
                <div class="ip-line">
                  <span class="ip">${esc(g.value)}</span>
                  ${g.count > 1 ? `<span class="chip">×${g.count}</span>` : ""}
                  ${g.types.map((ty) => `<span class="chip chip-alt">${esc(ty)}</span>`).join("")}
                  ${g.manual ? `<span class="chip chip-alt">${t.manual}</span>` : ""}
                </div>
                <span class="row-sub">${esc(sub)}</span>
              </div>
              <div class="row-right">
                <span class="left">${esc(rem)}</span>
                ${rem ? `<span class="left-sub">${t.remaining}</span>` : ""}
              </div>
            </div>`;
          })
          .join("")}</div>`
      : `<div class="empty">${esc(t.empty)}</div>`;

    const mapSvg = `
      <div class="map-wrap">
        <svg viewBox="${WORLD_VIEWBOX}" fill-rule="evenodd" aria-hidden="true">
          ${WORLD.map((c) => {
            const n = c.c ? counts[c.c] || 0 : 0;
            const cls = [n ? "hit" : "", this._filter && this._filter !== c.c ? "dim" : ""].join(" ").trim();
            return `<path d="${c.d}" fill="${bin(n, steps, zero)}"
              style="stroke: var(--card-background-color); stroke-width: 0.7"
              ${cls ? `class="${cls}"` : ""} data-cc="${esc(c.c)}" data-n="${esc(c.n)}" data-count="${n}"></path>`;
          }).join("")}
        </svg>
        <div class="tooltip"></div>
      </div>`;

    const legend = `
      <div class="legend" title="${esc(t.filterHint)}">
        ${[zero, ...steps]
          .map((color, i) => {
            const label = i < 5 ? BIN_LABELS[i] : t.legend20;
            return `<div><span class="sw" style="background:${color}"></span><span class="lb">${label}</span></div>`;
          })
          .join("")}
      </div>`;

    const topCountries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
    const maxCount = topCountries.length ? topCountries[0][1] : 1;
    const top = topCountries.length
      ? `<div class="top">
          <span class="top-title">${t.top}</span>
          ${topCountries
            .map(([cc, n]) => `<div class="top-row">
              ${flag(cc)}
              <span class="top-name">${esc(this._countryName(cc))}</span>
              <div class="bar"><div style="width:${Math.round((n / maxCount) * 100)}%"></div></div>
              <span class="top-count">${n}</span>
            </div>`)
            .join("")}
        </div>`
      : "";

    const mapCol = `${mapSvg}${legend}${top}`;
    let body;
    if (wide) {
      body = `<div class="cols">
          <div class="col-list">${header}${rows}</div>
          <div class="vsep"></div>
          <div class="col-map">${mapCol}</div>
        </div>`;
    } else if (viewCfg === "map") {
      body = `${header}${mapCol}`;
    } else if (viewCfg === "list") {
      body = `${header}${rows}`;
    } else {
      // auto on a narrow column: map stacked above the list.
      body = `${header}${mapSvg}${legend}${rows}`;
    }

    this.shadowRoot.innerHTML = `${style}<ha-card>${body}</ha-card>`;
    this._wire();
  }

  _wire() {
    const root = this.shadowRoot;
    const wrap = root.querySelector(".map-wrap");
    if (!wrap) return;
    const svg = wrap.querySelector("svg");
    const tooltip = wrap.querySelector(".tooltip");
    const t = this._t();
    // Delegated listeners: 3 on the svg instead of 3 per country path.
    svg.addEventListener("mousemove", (ev) => {
      const p = ev.target.closest("path");
      if (!p) {
        tooltip.style.display = "none";
        return;
      }
      const r = wrap.getBoundingClientRect();
      const count = +p.dataset.count;
      const name = p.dataset.cc ? this._countryName(p.dataset.cc) : p.dataset.n;
      tooltip.innerHTML = `<b>${esc(name)}</b> <span>${esc(t.bans(count))}</span>`;
      tooltip.style.display = "block";
      const x = Math.min(ev.clientX - r.left + 12, r.width - tooltip.offsetWidth - 4);
      tooltip.style.left = `${Math.max(0, x)}px`;
      // Flip below the pointer when there is no room above.
      const y = ev.clientY - r.top - 30;
      tooltip.style.top = `${y < 2 ? ev.clientY - r.top + 16 : y}px`;
    });
    svg.addEventListener("mouseleave", () => {
      tooltip.style.display = "none";
    });
    svg.addEventListener("click", (ev) => {
      const p = ev.target.closest("path");
      if (!p) return;
      const cc = p.dataset.cc;
      if (!cc || !+p.dataset.count) return;
      this._filter = this._filter === cc ? null : cc;
      this._invalidate();
    });
  }
}

class CrowdsecCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { palette: "menace", view: "auto", ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  _schema(fr) {
    return [
      { name: "entity", selector: { entity: { domain: "sensor" } } },
      { name: "title", selector: { text: {} } },
      {
        name: "view",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "auto", label: fr ? "Automatique (liste + carte en large)" : "Automatic (list + map when wide)" },
              { value: "list", label: fr ? "Liste seule" : "List only" },
              { value: "map", label: fr ? "Carte seule" : "Map only" },
            ],
          },
        },
      },
      {
        name: "palette",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "menace", label: fr ? "Menace (rouge-orangé)" : "Threat (red-orange)" },
              { value: "ocean", label: fr ? "Océan (bleu)" : "Ocean (blue)" },
              { value: "amethyste", label: fr ? "Améthyste (violet)" : "Amethyst (purple)" },
            ],
          },
        },
      },
    ];
  }

  _render() {
    if (!this._config) return;
    const fr = (this._hass?.language || "en").startsWith("fr");
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) =>
        ({
          entity: fr ? "Entité (auto-détectée si vide)" : "Entity (auto-detected if empty)",
          title: fr ? "Titre" : "Title",
          view: fr ? "Vue" : "View",
          palette: fr ? "Palette du dégradé" : "Gradient palette",
        }[s.name] || s.name);
      this._form.addEventListener("value-changed", (ev) => {
        fireEvent(this, "config-changed", { config: { ...ev.detail.value } });
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema(fr);
    this._form.data = this._config;
  }
}

/* Guarded: the module may be loaded twice (e.g. a manually added resource on
 * top of the automatic registration) and define() must not throw. */
if (!customElements.get("crowdsec-card")) {
  customElements.define("crowdsec-card", CrowdsecCard);
  customElements.define("crowdsec-card-editor", CrowdsecCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "crowdsec-card")) {
  window.customCards.push({
    type: "crowdsec-card",
    name: "CrowdSec Card",
    description: "Active CrowdSec bans: list with flags and a world map colored by bans per country.",
    preview: true,
  });
}
