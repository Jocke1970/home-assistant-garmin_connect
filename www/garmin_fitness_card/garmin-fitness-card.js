/*
 * Garmin Fitness Card v0.1.6-dev.2
 * Native Lovelace frontend for the Garmin Fitness sensors.
 *
 * - No external frontend dependencies.
 * - No build step.
 * - Reads live values from sensor.garmin_fitness_*.
 * - Reads history from Home Assistant Long-Term Statistics via Recorder websocket.
 */

const GARMIN_FITNESS_CARD_VERSION = "0.1.6-dev.2";

class GarminFitnessCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    this._hass = null;
    this._config = null;
    this._stats = {};
    this._statsError = null;
    this._statsLoading = false;
    this._statsCacheKey = "";
    this._lastStateSignature = "";
    this._expanded = {
      strain: false,
      training: true,
      tsb: false,
    };
  }

  // Exposed on the registered class prototype even when reloading a resource.
  // Useful to distinguish a cached old script from a missing script.
  get cardVersion() {
    return GARMIN_FITNESS_CARD_VERSION;
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    const defaultEntities = {
      daily_load: "sensor.garmin_fitness_daily_load",
      ctl: "sensor.garmin_fitness_ctl",
      atl: "sensor.garmin_fitness_atl",
      tsb: "sensor.garmin_fitness_tsb",
      acwr: "sensor.garmin_fitness_acwr",
      ramp_rate: "sensor.garmin_fitness_ramp_rate",
      strain: "sensor.garmin_fitness_strain",
    };

    const rangeCandidates = Array.isArray(config?.ranges)
      ? config.ranges
      : [7, 28, 42, 90];
    const ranges = [...new Set(
      rangeCandidates
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value) && value >= 7)
        .map((value) => Math.round(value))
    )].sort((a, b) => a - b);

    this._config = {
      title: "Garmin Fitness",
      show_title: false,
      days: 90,
      storage_id: "garmin-fitness-card",
      ...config,
      ranges: ranges.length ? ranges : [7, 28, 42, 90],
      entities: {
        ...defaultEntities,
        ...(config?.entities || {}),
      },
    };

    const configuredDays = Math.round(Number(this._config.days));
    const fallbackDays = this._config.ranges.includes(configuredDays)
      ? configuredDays
      : this._config.ranges.includes(90)
        ? 90
        : this._config.ranges[this._config.ranges.length - 1];
    this._config.days = this._loadRangeDays(fallbackDays);

    this._expanded = {
      strain: this._loadExpanded("strain", false),
      training: this._loadExpanded("training", true),
      tsb: this._loadExpanded("tsb", false),
    };

    this._statsCacheKey = "";
    this._stats = {};
    this._statsError = null;
    this._render();
    this._ensureStatistics();
  }

  set hass(hass) {
    this._hass = hass;
    const signature = this._stateSignature();

    if (signature !== this._lastStateSignature) {
      this._lastStateSignature = signature;
      this._render();
    }

    this._ensureStatistics();
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return {
      rows: "auto",
      columns: "full",
      min_rows: 4,
    };
  }

  _stateSignature() {
    if (!this._hass || !this._config) return "";

    const values = Object.values(this._config.entities).map((entityId) => {
      const state = this._hass.states[entityId];
      return state ? `${entityId}:${state.state}:${state.last_updated}` : `${entityId}:missing`;
    });

    values.push(this._dateKey(new Date()));
    return values.join("|");
  }

  _state(entityId) {
    return this._hass?.states?.[entityId] || null;
  }

  _number(entityId) {
    const state = this._state(entityId);
    if (!state) return null;
    const value = Number(state.state);
    return Number.isFinite(value) ? value : null;
  }

  _format(value, decimals = 1, options = {}) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      return "—";
    }

    const number = Number(value);
    const sign = options.sign && number > 0 ? "+" : "";
    return `${sign}${number.toFixed(decimals)}`.replace(".", ",");
  }

  _entityUnit(entityId, fallback = "") {
    return this._state(entityId)?.attributes?.unit_of_measurement || fallback;
  }

  _dateKey(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  _localMidnight(date = new Date()) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0, 0, 0);
  }

  async _ensureStatistics() {
    if (!this._hass || !this._config || this._statsLoading) return;

    const entityIds = Object.values(this._config.entities);
    const cacheKey = `${this._config.days}|${this._dateKey(new Date())}|${entityIds.join("|")}`;
    if (cacheKey === this._statsCacheKey) return;

    this._statsLoading = true;
    this._statsError = null;
    this._render();

    const now = new Date();
    const start = this._localMidnight(now);
    start.setDate(start.getDate() - (this._config.days - 1));

    const end = this._localMidnight(now);
    end.setDate(end.getDate() + 1);

    try {
      const result = await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        statistic_ids: entityIds,
        period: "day",
        types: ["mean"],
      });

      this._stats = result || {};
      this._statsCacheKey = cacheKey;
    } catch (error) {
      this._statsError = error?.message || String(error);
      this._stats = {};
      this._statsCacheKey = cacheKey;
      console.warn("Garmin Fitness Card: Recorder statistics unavailable", error);
    } finally {
      this._statsLoading = false;
      this._render();
    }
  }

  _series(entityId) {
    const rows = Array.isArray(this._stats?.[entityId]) ? this._stats[entityId] : [];
    const byDay = new Map();

    for (const row of rows) {
      // A null statistic mean is unknown, not zero.
      if (row?.mean == null || row?.start == null) continue;
      const value = Number(row.mean);
      const rawStart = Number(row.start);
      if (!Number.isFinite(value) || !Number.isFinite(rawStart)) continue;

      const start = rawStart < 1e11 ? rawStart * 1000 : rawStart;
      const date = new Date(start);
      if (!Number.isFinite(date.getTime())) continue;
      byDay.set(this._dateKey(date), {
        key: this._dateKey(date),
        time: start,
        value,
      });
    }

    const live = this._number(entityId);
    if (live !== null) {
      const today = this._localMidnight(new Date());
      byDay.set(this._dateKey(today), {
        key: this._dateKey(today),
        time: today.getTime(),
        value: live,
      });
    }

    return [...byDay.values()].sort((a, b) => a.time - b.time);
  }

  _aligned(entityIds) {
    const dayMap = new Map();

    for (const entityId of entityIds) {
      for (const point of this._series(entityId)) {
        if (!dayMap.has(point.key)) {
          dayMap.set(point.key, {
            key: point.key,
            time: point.time,
            values: {},
          });
        }
        dayMap.get(point.key).values[entityId] = point.value;
      }
    }

    return [...dayMap.values()].sort((a, b) => a.time - b.time);
  }

  _storageKey(section) {
    return `${this._config?.storage_id || "garmin-fitness-card"}:${section}`;
  }

  _loadRangeDays(fallback) {
    try {
      const stored = Number(localStorage.getItem(this._storageKey("days")));
      if (Number.isFinite(stored) && this._config?.ranges?.includes(stored)) {
        return stored;
      }
    } catch (_error) {
      // LocalStorage is optional; fall back to configured/default range.
    }
    return fallback;
  }

  _saveRangeDays() {
    try {
      localStorage.setItem(this._storageKey("days"), String(this._config.days));
    } catch (_error) {
      // Ignore storage failures.
    }
  }

  _setDays(days) {
    if (!this._config || this._statsLoading) return;
    const next = Math.round(Number(days));
    if (!this._config.ranges.includes(next) || next === this._config.days) return;

    this._config.days = next;
    this._saveRangeDays();
    this._statsCacheKey = "";
    this._stats = {};
    this._statsError = null;
    this._render();
    this._ensureStatistics();
  }

  _xLabelCountForDays() {
    if (this._config.days <= 7) return 4;
    if (this._config.days <= 42) return 5;
    return 6;
  }

  _loadExpanded(section, fallback) {
    try {
      const stored = localStorage.getItem(this._storageKey(section));
      if (stored === "true") return true;
      if (stored === "false") return false;
    } catch (_error) {
      // LocalStorage is optional; fall back to defaults.
    }
    return fallback;
  }

  _saveExpanded(section) {
    try {
      localStorage.setItem(this._storageKey(section), String(this._expanded[section]));
    } catch (_error) {
      // Ignore storage failures.
    }
  }

  _toggle(section) {
    this._expanded[section] = !this._expanded[section];
    this._saveExpanded(section);
    this._render();
  }

  _showMoreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  _wireEvents() {
    if (!this.shadowRoot) return;

    this.shadowRoot.querySelectorAll("[data-toggle]").forEach((button) => {
      button.addEventListener("click", () => this._toggle(button.dataset.toggle));
    });

    this.shadowRoot.querySelectorAll("[data-entity]").forEach((button) => {
      button.addEventListener("click", () => this._showMoreInfo(button.dataset.entity));
    });

    this.shadowRoot.querySelectorAll("[data-range]").forEach((button) => {
      button.addEventListener("click", () => this._setDays(button.dataset.range));
    });
  }

  _monthLabel(time) {
    return new Intl.DateTimeFormat("sv-SE", {
      day: "numeric",
      month: "short",
    }).format(new Date(time));
  }

  _xLabelIndexes(length) {
    if (length <= 1) return [0];
    const candidates = [0, 0.25, 0.5, 0.75, 1].map((fraction) =>
      Math.round((length - 1) * fraction)
    );
    return [...new Set(candidates)];
  }

  _emptyChart(message = "Ingen historik tillgänglig") {
    if (this._statsLoading) {
      return `<div class="chart-message"><ha-icon icon="mdi:loading" class="spin"></ha-icon>Laddar ${this._config.days} dagar…</div>`;
    }
    if (this._statsError) {
      const detail = String(this._statsError).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      })[char]);
      return `<div class="chart-message error"><ha-icon icon="mdi:alert-circle-outline"></ha-icon>Kunde inte läsa Long-Term Statistics: ${detail}</div>`;
    }
    return `<div class="chart-message">${message}</div>`;
  }

  _svgGrid({ width, height, left, right, top, bottom, min, max, ticks, data }) {
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const y = (value) => top + ((max - value) / Math.max(0.0001, max - min)) * plotHeight;
    let svg = "";

    for (const tick of ticks) {
      const yy = y(tick);
      svg += `<line x1="${left}" y1="${yy}" x2="${width - right}" y2="${yy}" class="grid-line" />`;
      svg += `<text x="${left - 8}" y="${yy + 4}" text-anchor="end" class="axis-label">${this._format(tick, Number.isInteger(tick) ? 0 : 1)}</text>`;
    }

    for (const index of this._xLabelIndexes(data.length)) {
      const x = left + ((index + 0.5) / Math.max(1, data.length)) * plotWidth;
      svg += `<text x="${x}" y="${height - 5}" text-anchor="middle" class="axis-label x-label">${this._monthLabel(data[index].time)}</text>`;
    }

    return { svg, y, plotWidth, plotHeight };
  }

  _strainChart() {
    const entityId = this._config.entities.strain;
    const data = this._series(entityId);
    if (!data.length) return this._emptyChart();

    const width = 1000;
    const height = 205;
    const left = 44;
    const right = 12;
    const top = 12;
    const bottom = 32;
    const min = 0;
    const max = 21;
    const ticks = [0, 7, 14, 21];
    const grid = this._svgGrid({ width, height, left, right, top, bottom, min, max, ticks, data });
    const plotWidth = grid.plotWidth;
    const plotBottom = height - bottom;
    const barWidth = Math.max(2.5, Math.min(11, (plotWidth / Math.max(1, data.length)) * 0.58));

    let bars = "";
    data.forEach((point, index) => {
      const x = left + ((index + 0.5) / data.length) * plotWidth;
      const yy = grid.y(Math.max(min, Math.min(max, point.value)));
      const barHeight = Math.max(0, plotBottom - yy);
      const hard = point.value >= 14;
      bars += `<rect x="${x - barWidth / 2}" y="${yy}" width="${barWidth}" height="${barHeight}" rx="2" class="strain-bar ${hard ? "hard" : ""}"><title>${this._monthLabel(point.time)} · Strain ${this._format(point.value, 1)}</title></rect>`;
    });

    const hardY = grid.y(14);

    return `
      <div class="chart-shell">
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Strain senaste ${this._config.days} dagarna">
          ${grid.svg}
          <line x1="${left}" y1="${hardY}" x2="${width - right}" y2="${hardY}" class="threshold-line" />
          ${bars}
        </svg>
      </div>
    `;
  }

  _trainingChart() {
    const ids = this._config.entities;
    const data = this._aligned([ids.daily_load, ids.ctl, ids.atl]);
    if (!data.length) return this._emptyChart();

    const fitnessValues = [];
    const loadValues = [];
    for (const point of data) {
      const ctl = point.values[ids.ctl];
      const atl = point.values[ids.atl];
      const load = point.values[ids.daily_load];
      if (Number.isFinite(ctl)) fitnessValues.push(ctl);
      if (Number.isFinite(atl)) fitnessValues.push(atl);
      if (Number.isFinite(load)) loadValues.push(load);
    }

    const maxFitness = Math.max(1, ...fitnessValues) * 1.08;
    const maxLoad = Math.max(1, ...loadValues);
    const width = 1000;
    const height = 270;
    const left = 44;
    const right = 12;
    const top = 12;
    const bottom = 32;
    const min = 0;
    const max = maxFitness;
    const ticks = [0, max * 0.25, max * 0.5, max * 0.75, max];
    const grid = this._svgGrid({ width, height, left, right, top, bottom, min, max, ticks, data });
    const plotWidth = grid.plotWidth;
    const plotHeight = grid.plotHeight;
    const plotBottom = height - bottom;
    const barWidth = Math.max(2.5, Math.min(10, (plotWidth / Math.max(1, data.length)) * 0.5));

    let bars = "";
    data.forEach((point, index) => {
      const load = point.values[ids.daily_load];
      if (!Number.isFinite(load)) return;
      const x = left + ((index + 0.5) / data.length) * plotWidth;
      const normalizedHeight = (Math.max(0, load) / maxLoad) * plotHeight * 0.94;
      bars += `<rect x="${x - barWidth / 2}" y="${plotBottom - normalizedHeight}" width="${barWidth}" height="${normalizedHeight}" rx="2" class="load-bar"><title>${this._monthLabel(point.time)} · Daily Load ${this._format(load, 1)} TRIMP</title></rect>`;
    });

    const linePath = (entityId) => {
      let path = "";
      let penDown = false;
      data.forEach((point, index) => {
        const value = point.values[entityId];
        if (!Number.isFinite(value)) {
          penDown = false;
          return;
        }
        const x = left + ((index + 0.5) / data.length) * plotWidth;
        const yy = grid.y(value);
        path += `${penDown ? "L" : "M"}${x.toFixed(2)},${yy.toFixed(2)} `;
        penDown = true;
      });
      return path.trim();
    };

    return `
      <div class="chart-shell training-chart">
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Träningsbelastning senaste ${this._config.days} dagarna">
          ${grid.svg}
          ${bars}
          <path d="${linePath(ids.ctl)}" class="ctl-line" />
          <path d="${linePath(ids.atl)}" class="atl-line" />
        </svg>
      </div>
    `;
  }

  _tsbChart() {
    const entityId = this._config.entities.tsb;
    const data = this._series(entityId);
    if (!data.length) return this._emptyChart();

    const values = data.map((point) => point.value).filter(Number.isFinite);
    const rawMin = Math.min(0, ...values);
    const rawMax = Math.max(0, ...values);

    // Round the visible range to calm 5-TRIMP steps and keep zero explicit.
    let min = Math.floor(rawMin / 5) * 5;
    let max = Math.ceil(rawMax / 5) * 5;
    if (min === max) {
      min -= 5;
      max += 5;
    }

    const width = 1000;
    const height = 200;
    const left = 50;
    const right = 12;
    const top = 8;
    const bottom = 34;
    const ticks = min < 0 && max > 0 ? [min, 0, max] : [min, (min + max) / 2, max];
    const grid = this._svgGrid({
      width,
      height,
      left,
      right,
      top,
      bottom,
      min,
      max,
      ticks,
      data,
      tickDecimals: 0,
      xLabelCount: this._xLabelCountForDays(),
    });
    const plotWidth = grid.plotWidth;
    const plotBottom = height - bottom;
    const zeroY = grid.y(0);
    const xForIndex = (index) => left + ((index + 0.5) / data.length) * plotWidth;
    const points = data.map((point, index) => ({
      x: xForIndex(index),
      y: grid.y(point.value),
    }));
    const path = this._smoothPath(points);

    let hitTargets = "";
    data.forEach((point, index) => {
      hitTargets += `<circle cx="${xForIndex(index)}" cy="${grid.y(point.value)}" r="8" class="series-hit"><title>${this._monthLabel(point.time)} · TSB ${this._format(point.value, 1, { sign: true })} TRIMP</title></circle>`;
    });

    return `
      <div class="chart-shell tsb-chart">
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Formbalans senaste ${this._config.days} dagarna">
          <rect x="${left}" y="${top}" width="${plotWidth}" height="${Math.max(0, zeroY - top)}" class="tsb-positive" />
          <rect x="${left}" y="${zeroY}" width="${plotWidth}" height="${Math.max(0, plotBottom - zeroY)}" class="tsb-negative" />
          ${grid.svg}
          <line x1="${left}" y1="${zeroY}" x2="${width - right}" y2="${zeroY}" class="zero-line" />
          <path d="${path}" class="tsb-line" />
          ${hitTargets}
        </svg>
      </div>
    `;
  }

  _summaryMetric({ label, value, secondary, icon, entity, tone = "primary" }) {
    return `
      <button class="summary-metric ${tone}" type="button" data-entity="${entity}" aria-label="${label}">
        <ha-icon icon="${icon}"></ha-icon>
        <div class="summary-text">
          <span class="summary-label">${label}</span>
          <span class="summary-value">${value}</span>
          <span class="summary-secondary">${secondary}</span>
        </div>
      </button>
    `;
  }

  _section({ key, title, meta, content }) {
    const expanded = this._expanded[key];
    return `
      <section class="section ${expanded ? "expanded" : "collapsed"}">
        <button class="section-toggle" type="button" data-toggle="${key}" aria-expanded="${expanded}">
          <span class="section-title">${title}</span>
          <span class="section-meta">${expanded ? "" : meta || ""}</span>
          <ha-icon icon="mdi:chevron-${expanded ? "up" : "down"}"></ha-icon>
        </button>
        ${expanded ? `<div class="section-content">${content}</div>` : ""}
      </section>
    `;
  }

  _currentStateGrid() {
    const ids = this._config.entities;
    const load = this._number(ids.daily_load);
    const ctl = this._number(ids.ctl);
    const atl = this._number(ids.atl);

    return `
      <div class="state-grid">
        <button type="button" class="state-item load" data-entity="${ids.daily_load}">
          <span class="state-number">${this._format(load, 1)}</span><span class="state-unit">TRIMP</span>
          <span class="state-label">Daily Load</span>
        </button>
        <button type="button" class="state-item ctl" data-entity="${ids.ctl}">
          <span class="state-number">${this._format(ctl, 1)}</span><span class="state-unit">TRIMP</span>
          <span class="state-label">CTL</span>
        </button>
        <button type="button" class="state-item atl" data-entity="${ids.atl}">
          <span class="state-number">${this._format(atl, 1)}</span><span class="state-unit">TRIMP</span>
          <span class="state-label">ATL</span>
        </button>
      </div>
    `;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;

    if (!this._hass) {
      this.shadowRoot.innerHTML = `${this._styles()}<ha-card><div class="loading">Laddar Garmin Fitness…</div><div class="card-version">Garmin Fitness Card v${GARMIN_FITNESS_CARD_VERSION}</div></ha-card>`;
      return;
    }

    const ids = this._config.entities;
    const acwr = this._number(ids.acwr);
    const ramp = this._number(ids.ramp_rate);
    const strain = this._number(ids.strain);
    const tsb = this._number(ids.tsb);
    const rampIcon = ramp === null ? "mdi:trending-neutral" : ramp > 0 ? "mdi:trending-up" : ramp < 0 ? "mdi:trending-down" : "mdi:trending-neutral";

    const missing = Object.entries(ids)
      .filter(([, entityId]) => !this._state(entityId))
      .map(([key]) => key);

    const title = this._config.show_title
      ? `<div class="card-title"><ha-icon icon="mdi:run-fast"></ha-icon><span>${this._config.title}</span></div>`
      : "";

    const warning = missing.length
      ? `<div class="warning"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>Saknar Fitness-entiteter: ${missing.join(", ")}</span></div>`
      : "";

    const summary = `
      <div class="summary">
        ${this._summaryMetric({
          label: "ACWR",
          value: this._format(acwr, 2),
          secondary: "7 d / 28 d",
          icon: "mdi:scale-balance",
          entity: ids.acwr,
        })}
        ${this._summaryMetric({
          label: "Ramp",
          value: this._format(ramp, 1, { sign: true }),
          secondary: "TRIMP / 7 d",
          icon: rampIcon,
          entity: ids.ramp_rate,
        })}
      </div>
    `;

    const rangeSelector = `
      <div class="range-selector" role="group" aria-label="Historikintervall">
        ${this._config.ranges.map((days) => `
          <button
            type="button"
            class="range-button ${days === this._config.days ? "active" : ""}"
            data-range="${days}"
            aria-pressed="${days === this._config.days}"
            ${this._statsLoading ? "disabled" : ""}
          >${days} d</button>
        `).join("")}
      </div>
    `;

    const strainContent = `
      <div class="single-state">
        <button type="button" data-entity="${ids.strain}" class="single-state-button strain-state">
          <span class="single-number">${this._format(strain, 1)}</span>
          <span class="single-unit">/ 21</span>
          <span class="single-label">Strain</span>
        </button>
        <div class="section-note"><span class="threshold-dot"></span>Hård dag ≥ 14</div>
      </div>
      ${this._strainChart()}
    `;

    const trainingContent = `${this._currentStateGrid()}${this._trainingChart()}`;

    const tsbContent = `
      <div class="single-state">
        <button type="button" data-entity="${ids.tsb}" class="single-state-button tsb-state">
          <span class="single-number">${this._format(tsb, 1, { sign: true })}</span>
          <span class="single-unit">TRIMP</span>
          <span class="single-label">TSB</span>
        </button>
      </div>
      ${this._tsbChart()}
    `;

    this.shadowRoot.innerHTML = `
      ${this._styles()}
      <ha-card>
        <div class="card-wrap">
          ${title}
          ${warning}
          ${summary}
          ${rangeSelector}
          <div class="sections">
            ${this._section({
              key: "strain",
              title: "Strain",
              meta: `${this._format(strain, 1)} / 21`,
              content: strainContent,
            })}
            ${this._section({
              key: "training",
              title: "Träningsbelastning",
              meta: `${this._config.days} dagar`,
              content: trainingContent,
            })}
            ${this._section({
              key: "tsb",
              title: "Formbalans (TSB)",
              meta: `${this._format(tsb, 1, { sign: true })} TRIMP`,
              content: tsbContent,
            })}
          </div>
          <div class="card-version">Garmin Fitness Card v${GARMIN_FITNESS_CARD_VERSION}</div>
        </div>
      </ha-card>
    `;

    this._wireEvents();
  }

  _styles() {
    return `
      <style>
        :host {
          display: block;
          --fitness-border: var(--divider-color, rgba(127, 127, 127, 0.2));
          --fitness-muted: var(--secondary-text-color, #8a8a8a);
          --fitness-surface-hover: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
          --fitness-accent: var(--primary-color, #03a9f4);
          --fitness-info: var(--info-color, #03a9f4);
          --fitness-warning: var(--warning-color, #ff9800);
          --fitness-success: var(--success-color, #4caf50);
        }

        * {
          box-sizing: border-box;
        }

        ha-card {
          overflow: hidden;
        }

        button {
          font: inherit;
        }

        .card-wrap {
          width: 100%;
        }

        .card-version {
          padding: 5px 10px 7px;
          text-align: right;
          color: var(--primary-text-color, #242424);
          font-size: 12px;
          font-weight: 600;
          line-height: 1.35;
          opacity: 1;
          user-select: none;
        }

        .loading {
          padding: 24px;
          color: var(--fitness-muted);
        }

        .card-title {
          display: flex;
          align-items: center;
          gap: 9px;
          padding: 15px 16px 8px;
          font-size: 1.05rem;
          font-weight: 650;
          color: var(--primary-text-color);
        }

        .card-title ha-icon {
          color: var(--fitness-accent);
          --mdc-icon-size: 22px;
        }

        .warning {
          display: flex;
          gap: 8px;
          align-items: center;
          margin: 8px 12px;
          padding: 10px 12px;
          border-radius: 10px;
          background: color-mix(in srgb, var(--error-color, #f44336) 13%, transparent);
          color: var(--error-color, #f44336);
          font-size: 0.82rem;
        }

        .warning ha-icon {
          --mdc-icon-size: 18px;
        }

        .summary {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .summary-metric {
          appearance: none;
          min-width: 0;
          border: 0;
          border-right: 1px solid var(--fitness-border);
          border-bottom: 1px solid var(--fitness-border);
          background: transparent;
          color: var(--primary-text-color);
          padding: 12px 8px;
          cursor: pointer;
          display: grid;
          grid-template-columns: 1fr;
          gap: 6px;
          align-items: center;
          justify-items: center;
          text-align: center;
          transition: background 120ms ease;
        }

        .summary-metric:last-child {
          border-right: 0;
        }

        .summary-metric:hover {
          background: var(--fitness-surface-hover);
        }

        .summary-metric ha-icon {
          color: var(--fitness-accent);
          --mdc-icon-size: 24px;
        }

        .summary-text {
          display: grid;
          grid-template-columns: auto auto;
          column-gap: 7px;
          align-items: baseline;
          justify-items: center;
          justify-content: center;
          text-align: center;
          min-width: 0;
          width: 100%;
        }

        .summary-label {
          grid-column: 1 / -1;
          font-size: 0.78rem;
          font-weight: 650;
          color: var(--fitness-muted);
        }

        .summary-value {
          font-size: 1.45rem;
          line-height: 1.05;
          font-weight: 500;
          color: var(--primary-text-color);
        }

        .summary-secondary {
          font-size: 0.75rem;
          color: var(--fitness-muted);
          white-space: nowrap;
        }

        .range-selector {
          display: flex;
          justify-content: center;
          gap: 5px;
          padding: 8px 12px;
          border-bottom: 1px solid var(--fitness-border);
        }

        .range-button {
          appearance: none;
          border: 1px solid var(--fitness-border);
          border-radius: 999px;
          background: transparent;
          color: var(--fitness-muted);
          min-width: 48px;
          padding: 5px 10px;
          font: inherit;
          font-size: 0.74rem;
          cursor: pointer;
          transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
        }

        .range-button:hover:not(:disabled) {
          background: var(--fitness-surface-hover);
          color: var(--primary-text-color);
        }

        .range-button.active {
          color: var(--fitness-accent);
          border-color: color-mix(in srgb, var(--fitness-accent) 45%, var(--fitness-border));
          background: color-mix(in srgb, var(--fitness-accent) 10%, transparent);
          font-weight: 650;
        }

        .range-button:disabled {
          cursor: default;
          opacity: 0.55;
        }

        .sections {
          width: 100%;
        }

        .section {
          border-bottom: 1px solid var(--fitness-border);
        }

        .section:last-child {
          border-bottom: 0;
        }

        .section-toggle {
          appearance: none;
          width: 100%;
          border: 0;
          background: transparent;
          color: var(--primary-text-color);
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto auto;
          align-items: center;
          gap: 10px;
          padding: 14px 16px;
          cursor: pointer;
          text-align: left;
          transition: background 120ms ease;
        }

        .section-toggle:hover {
          background: var(--fitness-surface-hover);
        }

        .section.expanded .section-toggle {
          padding-bottom: 10px;
        }

        .section-title {
          font-weight: 600;
          min-width: 0;
        }

        .section-meta {
          font-size: 0.78rem;
          color: var(--fitness-muted);
          white-space: nowrap;
        }

        .section-toggle ha-icon {
          --mdc-icon-size: 20px;
          color: var(--fitness-muted);
        }

        .section-content {
          padding: 0 12px 12px;
          animation: reveal 130ms ease-out;
        }

        @keyframes reveal {
          from { opacity: 0; transform: translateY(-3px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .state-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 8px;
          padding: 0 0 6px;
        }

        .state-item,
        .single-state-button {
          appearance: none;
          border: 0;
          background: transparent;
          cursor: pointer;
          color: var(--primary-text-color);
        }

        .state-item {
          padding: 7px 4px 5px;
          text-align: center;
          border-radius: 9px;
          transition: background 120ms ease;
        }

        .state-item:hover,
        .single-state-button:hover {
          background: var(--fitness-surface-hover);
        }

        .state-number {
          font-size: 1.6rem;
          line-height: 1;
          font-weight: 450;
        }

        .state-unit {
          margin-left: 2px;
          font-size: 0.76rem;
          color: var(--fitness-muted);
        }

        .state-label {
          display: block;
          margin-top: 5px;
          font-size: 0.72rem;
          color: var(--fitness-muted);
        }

        .state-item.load .state-number {
          color: var(--fitness-info);
        }

        .state-item.ctl .state-number {
          color: var(--fitness-accent);
        }

        .state-item.atl .state-number {
          color: var(--fitness-warning);
        }

        .single-state {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          min-height: 48px;
          padding: 0 0 3px;
        }

        .single-state-button {
          padding: 6px 8px;
          border-radius: 9px;
          text-align: left;
        }

        .single-number {
          font-size: 1.55rem;
          line-height: 1;
          color: var(--fitness-accent);
        }

        .tsb-state .single-number {
          color: var(--fitness-success);
        }

        .single-unit {
          margin-left: 3px;
          font-size: 0.78rem;
          color: var(--fitness-muted);
        }

        .single-label {
          display: block;
          margin-top: 5px;
          font-size: 0.72rem;
          color: var(--fitness-muted);
        }

        .section-note {
          display: flex;
          align-items: center;
          gap: 6px;
          color: var(--fitness-muted);
          font-size: 0.72rem;
        }

        .threshold-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: var(--fitness-warning);
        }

        .chart-shell {
          width: 100%;
          min-height: 155px;
        }

        .training-chart {
          min-height: 205px;
        }

        .chart-shell svg {
          display: block;
          width: 100%;
          height: auto;
          min-height: 155px;
          overflow: visible;
        }

        .training-chart svg {
          min-height: 205px;
        }

        .grid-line {
          stroke: var(--fitness-border);
          stroke-width: 1;
          stroke-dasharray: 4 5;
          vector-effect: non-scaling-stroke;
        }

        .axis-label {
          fill: var(--fitness-muted);
          font-size: 25px;
          font-family: sans-serif;
        }

        .x-label {
          font-size: 23px;
        }

        .strain-bar {
          fill: var(--fitness-info);
          opacity: 0.58;
        }

        .strain-bar.hard {
          fill: var(--fitness-warning);
          opacity: 0.82;
        }

        .threshold-line {
          stroke: var(--fitness-warning);
          stroke-width: 1.5;
          stroke-dasharray: 5 5;
          vector-effect: non-scaling-stroke;
          opacity: 0.9;
        }

        .load-bar {
          fill: var(--fitness-info);
          opacity: 0.16;
        }

        .ctl-line,
        .atl-line,
        .tsb-line {
          fill: none;
          vector-effect: non-scaling-stroke;
          stroke-linecap: round;
          stroke-linejoin: round;
        }

        .ctl-line {
          stroke: var(--fitness-accent);
          stroke-width: 3;
        }

        .atl-line {
          stroke: var(--fitness-warning);
          stroke-width: 2.25;
        }

        .tsb-line {
          stroke: var(--fitness-success);
          stroke-width: 3;
        }

        .zero-line {
          stroke: var(--fitness-border);
          stroke-width: 1.5;
          stroke-dasharray: 5 5;
          vector-effect: non-scaling-stroke;
        }

        .tsb-positive {
          fill: var(--fitness-success);
          opacity: 0.045;
        }

        .tsb-negative {
          fill: var(--fitness-warning);
          opacity: 0.04;
        }

        .chart-message {
          min-height: 145px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          color: var(--fitness-muted);
          font-size: 0.82rem;
          text-align: center;
        }

        .chart-message.error {
          color: var(--error-color, #f44336);
        }

        .chart-message ha-icon {
          --mdc-icon-size: 18px;
        }

        .spin {
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        @media (max-width: 520px) {
          .summary-label {
            font-size: 0.74rem;
          }

          .summary-value {
            font-size: 1.3rem;
          }

          .section-toggle {
            padding: 13px 14px;
          }

          .section-content {
            padding-left: 9px;
            padding-right: 9px;
          }

          .section-meta {
            display: none;
          }

          .section-toggle {
            grid-template-columns: minmax(0, 1fr) auto;
          }

          .state-number {
            font-size: 1.35rem;
          }

          .axis-label {
            font-size: 29px;
          }

          .x-label {
            font-size: 26px;
          }
        }
      </style>
    `;
  }
}

const registeredGarminFitnessCard = customElements.get("garmin-fitness-card");

if (!registeredGarminFitnessCard) {
  customElements.define("garmin-fitness-card", GarminFitnessCard);
} else if (registeredGarminFitnessCard !== GarminFitnessCard) {
  // Lovelace resources can be reloaded while the browser tab stays alive.
  // Custom elements cannot be re-defined, so copy the newest prototype onto
  // the already registered class instead of leaving an old card implementation
  // active until the whole tab is closed.
  for (const name of Object.getOwnPropertyNames(GarminFitnessCard.prototype)) {
    if (name === "constructor") continue;
    const descriptor = Object.getOwnPropertyDescriptor(GarminFitnessCard.prototype, name);
    if (descriptor) {
      Object.defineProperty(registeredGarminFitnessCard.prototype, name, descriptor);
    }
  }
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "garmin-fitness-card")) {
  window.customCards.push({
    type: "garmin-fitness-card",
    name: "Garmin Fitness Card",
    description: "Garmin Fitness insights, Strain, Training Load and TSB with Long-Term Statistics.",
    preview: true,
  });
}

console.info("%c GARMIN-FITNESS-CARD %c v0.1.6-dev.2 ", "color: white; background: #0288d1; font-weight: 700;", "color: #0288d1; background: transparent;");

/* Garmin Fitness Card v0.1.2 Training graph patch */
const GarminFitnessCardV012 = customElements.get("garmin-fitness-card");

if (!GarminFitnessCardV012) {
  throw new Error("Garmin Fitness Card v0.1.2: base card did not load.");
}

const proto = GarminFitnessCardV012.prototype;

proto._xLabelIndexes = function (length, count = 5) {
  if (length <= 1) return [0];
  const safeCount = Math.max(2, Math.min(count, length));
  const candidates = Array.from({ length: safeCount }, (_, index) =>
    Math.round(((length - 1) * index) / (safeCount - 1))
  );
  return [...new Set(candidates)];
};

proto._svgGrid = function ({
  width,
  height,
  left,
  right,
  top,
  bottom,
  min,
  max,
  ticks,
  data,
  tickDecimals = null,
  xLabelCount = null,
}) {
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const y = (value) => top + ((max - value) / Math.max(0.0001, max - min)) * plotHeight;
  let svg = "";

  for (const tick of ticks) {
    const yy = y(tick);
    const decimals = tickDecimals === null ? (Number.isInteger(tick) ? 0 : 1) : tickDecimals;
    svg += `<line x1="${left}" y1="${yy}" x2="${width - right}" y2="${yy}" class="grid-line" />`;
    svg += `<text x="${left - 8}" y="${yy + 4}" text-anchor="end" class="axis-label">${this._format(tick, decimals)}</text>`;
  }

  const resolvedXLabelCount = xLabelCount ?? this._xLabelCountForDays();
  for (const index of this._xLabelIndexes(data.length, resolvedXLabelCount)) {
    const x = left + ((index + 0.5) / Math.max(1, data.length)) * plotWidth;
    svg += `<text x="${x}" y="${height - 5}" text-anchor="middle" class="axis-label x-label">${this._monthLabel(data[index].time)}</text>`;
  }

  return { svg, y, plotWidth, plotHeight };
};

proto._smoothPath = function (points) {
  if (!points.length) return "";
  if (points.length === 1) {
    return `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`;
  }

  let path = `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`;

  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[index - 1] || points[index];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[index + 2] || p2;

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    path += ` C${cp1x.toFixed(2)},${cp1y.toFixed(2)} ${cp2x.toFixed(2)},${cp2y.toFixed(2)} ${p2.x.toFixed(2)},${p2.y.toFixed(2)}`;
  }

  return path;
};

proto._smoothSeriesPath = function (data, entityId, xForIndex, yForValue) {
  const segments = [];
  let current = [];

  data.forEach((point, index) => {
    const value = point.values?.[entityId];
    if (!Number.isFinite(value)) {
      if (current.length) segments.push(current);
      current = [];
      return;
    }

    current.push({
      x: xForIndex(index),
      y: yForValue(value),
    });
  });

  if (current.length) segments.push(current);
  return segments.map((segment) => this._smoothPath(segment)).join(" ");
};

proto._trainingChart = function () {
  const ids = this._config.entities;
  const data = this._aligned([ids.daily_load, ids.ctl, ids.atl]);
  if (!data.length) return this._emptyChart();

  const fitnessValues = [];
  const loadValues = [];
  for (const point of data) {
    const ctl = point.values[ids.ctl];
    const atl = point.values[ids.atl];
    const load = point.values[ids.daily_load];
    if (Number.isFinite(ctl)) fitnessValues.push(ctl);
    if (Number.isFinite(atl)) fitnessValues.push(atl);
    if (Number.isFinite(load)) loadValues.push(load);
  }

  // Keep the left axis calm and human-readable, similar to the old ApexCharts view.
  const rawFitnessMax = Math.max(1, ...fitnessValues);
  const max = Math.max(20, Math.ceil((rawFitnessMax * 1.04) / 10) * 10);
  const maxLoad = Math.max(1, ...loadValues);

  const width = 1000;
  const height = 250;
  const left = 50;
  const right = 12;
  const top = 8;
  const bottom = 34;
  const min = 0;
  const ticks = [0, max * 0.25, max * 0.5, max * 0.75, max];

  const grid = this._svgGrid({
    width,
    height,
    left,
    right,
    top,
    bottom,
    min,
    max,
    ticks,
    data,
    tickDecimals: 0,
    xLabelCount: this._xLabelCountForDays(),
  });

  const plotWidth = grid.plotWidth;
  const plotHeight = grid.plotHeight;
  const plotBottom = height - bottom;
  const slotWidth = plotWidth / Math.max(1, data.length);
  const barWidth = Math.max(2.5, Math.min(11, slotWidth * 0.58));
  const xForIndex = (index) => left + ((index + 0.5) / data.length) * plotWidth;

  let bars = "";
  data.forEach((point, index) => {
    const load = point.values[ids.daily_load];
    if (!Number.isFinite(load)) return;
    const x = xForIndex(index);
    const normalizedHeight = (Math.max(0, load) / maxLoad) * plotHeight * 0.92;
    bars += `<rect x="${x - barWidth / 2}" y="${plotBottom - normalizedHeight}" width="${barWidth}" height="${normalizedHeight}" rx="2" class="load-bar"><title>${this._monthLabel(point.time)} · Daily Load ${this._format(load, 1)} TRIMP</title></rect>`;
  });

  const ctlPath = this._smoothSeriesPath(data, ids.ctl, xForIndex, grid.y);
  const atlPath = this._smoothSeriesPath(data, ids.atl, xForIndex, grid.y);

  // Transparent hit targets keep simple native browser tooltips available on the lines.
  let hitTargets = "";
  data.forEach((point, index) => {
    const x = xForIndex(index);
    const ctl = point.values[ids.ctl];
    const atl = point.values[ids.atl];

    if (Number.isFinite(ctl)) {
      hitTargets += `<circle cx="${x}" cy="${grid.y(ctl)}" r="8" class="series-hit"><title>${this._monthLabel(point.time)} · CTL ${this._format(ctl, 1)} TRIMP</title></circle>`;
    }
    if (Number.isFinite(atl)) {
      hitTargets += `<circle cx="${x}" cy="${grid.y(atl)}" r="8" class="series-hit"><title>${this._monthLabel(point.time)} · ATL ${this._format(atl, 1)} TRIMP</title></circle>`;
    }
  });

  return `
    <div class="chart-shell training-chart training-v012">
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Träningsbelastning senaste ${this._config.days} dagarna">
        ${grid.svg}
        ${bars}
        <path d="${ctlPath}" class="ctl-line" />
        <path d="${atlPath}" class="atl-line" />
        ${hitTargets}
      </svg>
    </div>
  `;
};

const baseStyles = proto._styles;
proto._styles = function () {
  return `${baseStyles.call(this)}
    <style>
      .state-grid {
        padding-bottom: 4px;
      }

      .training-chart {
        min-height: 195px;
        margin-top: 2px;
      }

      .training-chart svg {
        min-height: 195px;
      }

      .load-bar {
        opacity: 0.14;
      }

      .atl-line {
        stroke-width: 2.2;
      }

      .series-hit {
        fill: transparent;
        stroke: transparent;
        pointer-events: all;
      }
    </style>
  `;
};