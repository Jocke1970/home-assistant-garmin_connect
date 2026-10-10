/* Garmin Fitness Dashboard v0.1.1-dev.3 — presentation only.
 * Keeps the existing garmin-fitness-card graph as a separate, persistent element.
 * No backend calculations, external libraries or build step.
 */
(() => {
  'use strict';
  const VERSION = '0.1.1-dev.3';
  const TAG = 'garmin-fitness-dashboard-card';
  const DEFAULTS = Object.freeze({
    insights: 'sensor.garmin_insights_overview',
    budget: 'sensor.garmin_fitness_garmin_daily_load_budget',
    evaluation: 'sensor.garmin_activity_evaluation',
    selector: 'select.garmin_activity_evaluation',
    acwr: 'sensor.garmin_fitness_acwr',
  });
  const ICONS = Object.freeze({
    walking: 'mdi:walk', hiking: 'mdi:hiking', cycling: 'mdi:bike',
    road_biking: 'mdi:bike', virtual_ride: 'mdi:bike', running: 'mdi:run',
    trail_running: 'mdi:run', rowing: 'mdi:rowing', rowing_v2: 'mdi:rowing',
    strength_training: 'mdi:dumbbell', swimming: 'mdi:swim', yoga: 'mdi:meditation',
  });
  const SPORT = Object.freeze({
    walking: 'Promenad', hiking: 'Vandring', cycling: 'Cykling',
    road_biking: 'Cykling', virtual_ride: 'Virtuell cykling', running: 'Löpning',
    trail_running: 'Traillöpning', rowing: 'Rodd', rowing_v2: 'Rodd',
    strength_training: 'Styrketräning', swimming: 'Simning', yoga: 'Yoga',
  });
  const QUALITY = Object.freeze({
    hrv: 'HRV', sleep: 'Sömn', summary: 'Dagssammanfattning',
    'recovery.resting_hr': 'vilopuls',
    'recovery.hrv_last_night_avg': 'nattlig HRV',
    'recovery.sleep_score': 'sömnpoäng',
  });
  const finite = (v) => v !== null && v !== undefined && v !== '' && typeof v !== 'boolean' && Number.isFinite(Number(v));
  const number = (v) => finite(v) ? Number(v) : null;
  const fmt = (v, n = 1) => finite(v) ? Number(v).toFixed(n).replace('.', ',') : '–';
  const signed = (v, n = 1) => finite(v) ? `${Number(v) > 0 ? '+' : ''}${fmt(v, n)}` : '–';
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const icon = (name, cls = '') => `<ha-icon class="${esc(cls)}" icon="${esc(name)}"></ha-icon>`;
  const activityIcon = (type) => ICONS[type] || 'mdi:run-fast';
  const sport = (type) => SPORT[type] || String(type || 'Aktivitet').replaceAll('_', ' ');
  const maybe = (v, suffix = '', n = 1) => finite(v) ? `${fmt(v, n)}${suffix}` : '–';
  const attr = (state) => state?.attributes || {};
  const isPresent = (state) => state && state.state !== 'unknown' && state.state !== 'unavailable';

  class GarminFitnessDashboardCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._config = null;
      this._hass = null;
      this._graph = null;
      this._signature = '';
      this._nodes = {};
      this._eventsBound = false;
    }

    static getStubConfig() { return {}; }
    get cardVersion() { return VERSION; }
    getCardSize() { return 12; }
    getGridOptions() { return { rows: 'auto', columns: 'full', min_rows: 6 }; }

    setConfig(config) {
      if (!config || typeof config !== 'object' || Array.isArray(config)) {
        throw new Error('Garmin Fitness Dashboard: ogiltig konfiguration');
      }
      const days = Number(config.graph_days ?? 90);
      this._config = {
        graph_days: [7, 28, 42, 90].includes(days) ? days : 90,
        show_banner: true, show_insights: true, show_graph: true,
        show_budget: true, show_activity_evaluation: true,
        banner: '/local/garmin_fitness_card/garmin_fitness_banner.png',
        ...config,
        entities: { ...DEFAULTS, ...(config.entities || {}) },
      };
      this._graph = null;
      this._signature = '';
      this._build();
      if (this._hass) this._refresh();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._config || !this._nodes.insights) return;
      this._refresh();
    }

    _state(key) {
      return this._hass?.states?.[this._config.entities[key]] || null;
    }

    _build() {
      const c = this._config;
      this.shadowRoot.innerHTML = `<style>${this._styles()}</style>
        <ha-card class="dashboard">
          ${c.show_banner ? `<div class="banner"><img src="${esc(c.banner)}" alt="Garmin Fitness"></div>` : ''}
          ${c.show_insights ? '<section class="insights" id="insights"></section>' : ''}
          ${c.show_graph ? '<section class="graph" id="graph"></section>' : ''}
          ${c.show_budget ? '<section class="budget" id="budget"></section>' : ''}
          ${c.show_activity_evaluation ? '<section class="evaluation" id="evaluation"></section>' : ''}
          <footer>Garmin Fitness Dashboard v${VERSION} · Grafkortet har egen version</footer>
        </ha-card>`;
      this._nodes = Object.fromEntries(['insights', 'graph', 'budget', 'evaluation']
        .map((key) => [key, this.shadowRoot.getElementById(key)]));
      if (!this._eventsBound) {
      this._eventsBound = true;
      this.shadowRoot.addEventListener('change', (ev) => {
        if (ev.target?.id !== 'activity-selector' || !this._hass) return;
        const option = ev.target.value;
        const id = this._config.entities.selector;
        const options = attr(this._state('selector')).options || [];
        if (!Array.isArray(options) || !options.includes(option)) return;
        Promise.resolve(this._hass.callService('select', 'select_option', {
          entity_id: id, option,
        })).catch((err) => console.error('Garmin Fitness: passval misslyckades', err));
      });
      this.shadowRoot.addEventListener('click', (ev) => {
        const target = ev.target?.closest?.('[data-more-info]');
        if (!target) return;
        const entityId = target.getAttribute('data-more-info');
        if (entityId && this._hass?.states?.[entityId]) {
          this.dispatchEvent(new CustomEvent('hass-more-info', {
            bubbles: true, composed: true, detail: { entityId },
          }));
        }
      });
      this.shadowRoot.addEventListener('keydown', (ev) => {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        const target = ev.target?.closest?.('[data-more-info]');
        if (!target) return;
        ev.preventDefault();
        target.click();
      });
      }
    }

    _refresh() {
      const keys = ['insights', 'budget', 'evaluation', 'selector', 'acwr'];
      const signature = keys.map((key) => {
        const s = this._state(key);
        return `${key}:${s?.state ?? 'missing'}:${s?.last_updated ?? ''}`;
      }).join('|');
      if (signature !== this._signature) {
        this._signature = signature;
        if (this._nodes.insights) this._nodes.insights.innerHTML = this._insightsHtml();
        if (this._nodes.budget) this._nodes.budget.innerHTML = this._budgetHtml();
        if (this._nodes.evaluation) this._nodes.evaluation.innerHTML = this._evaluationHtml();
      }
      this._updateGraph();
    }

    _updateGraph() {
      const holder = this._nodes.graph;
      if (!holder) return;
      if (!customElements.get('garmin-fitness-card')) {
        holder.innerHTML = '<div class="notice">Grafresursen saknas. Kontrollera att <code>garmin-fitness-card.js</code> är registrerad som separat Lovelace-resurs.</div>';
        this._graph = null;
        return;
      }
      if (!this._graph) {
        holder.replaceChildren();
        this._graph = document.createElement('garmin-fitness-card');
        this._graph.setConfig({
          days: this._config.graph_days,
          show_title: true,
          storage_id: 'garmin-fitness-dashboard-graph',
        });
        holder.appendChild(this._graph);
      }
      // Crucial: do not replace the graph DOM during routine HA state updates.
      this._graph.hass = this._hass;
    }

    _insightsHtml() {
      const s = this._state('insights');
      if (!isPresent(s)) return this._panel('mdi:information-outline', 'Insikter', 'Väntar på Garmin Insights.');
      const a = attr(s);
      const results = Array.isArray(a.presented_results)
        ? a.presented_results.filter((item) => item && item.id !== 'insufficient_or_stale_data') : [];
      const quality = a.data_quality || {};
      const missing = [...(quality.missing_sources || []), ...(quality.missing_fields || []),
        ...(quality.stale_fields || [])];
      let html = '';
      if (results.length === 0) {
        html += this._panel('mdi:check-circle-outline', 'Garmin Insights',
          a.status === 'clear' ? 'Inga aktiva insikter just nu.' : 'Inväntar insiktsdata.');
      } else {
        html += results.map((r, index) => {
          if (!r || typeof r !== 'object') return '';
          const evidence = Array.isArray(r.evidence) ? r.evidence : [];
          const context = index === 0 ? evidence
            .filter((e) => ['acwr_above_spike_threshold', 'acwr_below_low_load_threshold',
              'positive_ramp_rate', 'negative_ramp_rate'].includes(e.code) && finite(e.value))
            .map((e) => `${e.code.includes('acwr') ? 'ACWR' : 'Ramp'} ${fmt(e.value, 2)}`)
            .join(' · ') : '';
          const detail = this._insightDetail(r, a, evidence);
          return `<div class="insight ${index === 0 ? 'primary' : ''} ${esc(r.severity || '')}"
            data-more-info="${esc(this._config.entities.insights)}" role="button" tabindex="0">
              ${icon(r.icon || 'mdi:lightbulb-outline', 'insight-icon')}
              <div class="insight-text"><strong>${esc(r.title || 'Insikt')}</strong>
                <p>${esc(r.message || '')}</p>${context ? `<small>${esc(context)}</small>` : ''}
                ${detail}
              </div></div>`;
        }).join('');
      }
      if (missing.length) {
        const names = [...new Set(missing.map((v) => QUALITY[v] || String(v).replaceAll('_', ' ')))];
        const recoveryOnly = quality.training_complete === true && quality.load_focus_complete === true &&
          missing.every((v) => v === 'hrv' || String(v).startsWith('recovery.'));
        html += `<div class="quality">${icon('mdi:database-alert-outline')}
          <div><strong>${recoveryOnly ? 'Återhämtningsunderlag ofullständigt – träningsdata finns' :
            'Vissa underlag saknas eller är äldre'}</strong><span>${esc(names.join(' · '))}</span></div></div>`;
      }
      const acts = Array.isArray(a.recent_activities) ? a.recent_activities : [];
      if (acts.length) {
        const first = acts[0];
        const today = a.snapshot_date;
        html += `<div class="recent" data-more-info="${esc(this._config.entities.insights)}" role="button" tabindex="0">
          ${icon(activityIcon(first.activity_type))}<div><strong>Senaste aktivitet · ${esc(sport(first.activity_type))}</strong>
          <span>${esc(first.date === today ? 'Idag' : (first.date || '–'))} · ${maybe(first.duration_minutes, ' min')} · Load ${fmt(first.garmin_training_load)} · TE ${fmt(first.aerobic_training_effect)} / ${fmt(first.anaerobic_training_effect)}</span></div></div>`;
      }
      return html;
    }

    _panel(ic, heading, detail) {
      return `<div class="notice">${icon(ic)}<div><strong>${esc(heading)}</strong><p>${esc(detail)}</p></div></div>`;
    }
    _insightDetail(result, attributes, evidence) {
      if (result?.id === 'load_focus_imbalance') {
        return this._focusInsightHtml(attributes, evidence);
      }
      if (result?.id === 'recovery_caution') {
        return this._recoveryInsightHtml(evidence);
      }
      return '';
    }

    _evidence(evidence, code) {
      return Array.isArray(evidence)
        ? evidence.find((item) => item && item.code === code) || null
        : null;
    }

    _focusInsightHtml(attributes, evidence) {
      const focus = attributes?.load_focus || {};
      const low = number(focus.low_aerobic);
      const high = number(focus.high_aerobic);
      const anaerobic = number(focus.anaerobic);
      const values = [low, high, anaerobic].map((value) => value ?? 0);
      const total = values.reduce((sum, value) => sum + Math.max(0, value), 0);
      const countEvidence = this._evidence(evidence, 'recent_focus_activity_count');
      const ratioEvidence = this._evidence(evidence, 'dominance_ratio');
      const count = number(countEvidence?.value);
      const ratio = number(ratioEvidence?.value);
      const ratioThreshold = number(ratioEvidence?.threshold);

      if (total <= 0 && count === null && ratio === null) return '';

      const lowPct = total > 0 ? (Math.max(0, values[0]) / total) * 100 : 0;
      const highPct = total > 0 ? (Math.max(0, values[1]) / total) * 100 : 0;
      const highEnd = lowPct + highPct;
      const ring = total > 0
        ? `<div class="focus-ring" style="background:conic-gradient(
            var(--info-color,#00bceb) 0 ${lowPct.toFixed(2)}%,
            var(--warning-color,#ff9800) ${lowPct.toFixed(2)}% ${highEnd.toFixed(2)}%,
            var(--error-color,#f44336) ${highEnd.toFixed(2)}% 100%)">
            <div><strong>${fmt(total)}</strong><span>TE</span></div></div>`
        : '';

      const ratioText = ratio !== null
        ? `${fmt(ratio, 1)}×${ratioThreshold !== null ? ` · gräns ${fmt(ratioThreshold, 1)}×` : ''}`
        : '–';

      return `<div class="insight-detail focus-detail">
        <div class="focus-main">${ring}<div class="focus-legend">
          ${this._focusLegend('low', 'Låg aerob', low)}
          ${this._focusLegend('high', 'Hög aerob', high)}
          ${this._focusLegend('anaerobic', 'Anaerob', anaerobic)}
        </div></div>
        <div class="focus-meta">
          <span><strong>${count !== null ? fmt(count, 0) : '–'}</strong> pass med Training Effect</span>
          <span><strong>${esc(ratioText)}</strong> dominanskvot</span>
        </div></div>`;
    }

    _focusLegend(kind, label, value) {
      return `<div class="focus-legend-row"><i class="${esc(kind)}"></i>
        <span>${esc(label)}</span><strong>${fmt(value)}</strong></div>`;
    }

    _recoveryInsightHtml(evidence) {
      const items = [
        this._evidence(evidence, 'body_battery_low'),
        this._evidence(evidence, 'hrv_below_balanced_baseline'),
      ].filter((item) => item && finite(item.value));

      if (!items.length) return '';

      return `<div class="insight-detail recovery-detail">${items.map((item) => {
        const value = number(item.value);
        const threshold = number(item.threshold);
        const width = threshold !== null && threshold > 0 && value !== null
          ? Math.max(0, Math.min(100, (value / threshold) * 100))
          : 0;
        const thresholdText = threshold !== null ? ` · gräns ${fmt(threshold, 0)}` : '';
        return `<div class="recovery-meter">
          <div class="recovery-meter-head"><span>${esc(item.label || item.code || 'Återhämtning')}</span>
            <strong>${fmt(value, 0)}${esc(thresholdText)}</strong></div>
          ${threshold !== null ? `<div class="evidence-track"><div style="width:${width.toFixed(1)}%"></div></div>` : ''}
        </div>`;
      }).join('')}</div>`;
    }

    _gearHtml(activity) {
      // Linked Gear must belong to the selected activity, not to Last Activity.
      const gear = Array.isArray(activity?.linked_gear) ? activity.linked_gear : null;
      if (gear === null) return '';
      const items = gear.filter((item) => item && typeof item === 'object');
      if (!items.length) return '<div class="mini-title">Utrustning som användes</div><p class="small">Ingen kopplad utrustning för valt pass.</p>';
      return `<div class="mini-title">Utrustning som användes</div>
        <div class="gear-items">${items.map((item) => {
          const type = String(item.gear_type || '').toLowerCase();
          const gearIcon = type.includes('shoe') ? 'mdi:shoe-sneaker'
            : type.includes('bike') ? 'mdi:bike'
              : 'mdi:watch-variant';
          const name = String(item.name || item.custom_make_model || 'Utrustning').replace(/\\s+/g, ' ').trim();
          const custom = String(item.custom_make_model || '').replace(/\\s+/g, ' ').trim();
          const brand = String(item.brand || '').trim();
          const model = String(item.model || '').trim();
          const description = custom && custom !== name ? custom
            : [brand, model].filter((v) => v && v.toLowerCase() !== 'other' && !v.toLowerCase().startsWith('unknown')).join(' ');
          return `<div class="gear-item">${icon(gearIcon)}<div><strong>${esc(name)}</strong>${description ? `<span>${esc(description)}</span>` : ''}</div></div>`;
        }).join('')}</div>`;
    }

    _budgetHtml() {
      const s = this._state('budget');
      if (!isPresent(s)) return this._panel('mdi:gauge', 'Dagens träningsbudget', 'Väntar på aktuell budgetsensor.');
      const a = attr(s);
      const max = number(a.recommended_max_load);
      const current = number(a.budget_consuming_load ?? a.current_load);
      const remaining = number(a.remaining_load ?? s.state);
      const actual = number(a.canonical_current_load ?? a.current_load);
      const excluded = number(a.excluded_low_intensity_load);
      const factor = String(a.structural_limiting_factor || a.limiting_factor || '');
      const factorLabel = a.structural_limiting_factor_label || a.limiting_factor_label || factor;
      let line;
      if (remaining === null) line = 'Budgetberäkning saknas.';
      else if (remaining <= 0 && factor === 'acwr')
        line = `Beräknad träningsbudget: 0 TRIMP – begränsas av ACWR (${fmt(a.projected_acwr, 2)}).`;
      else if (remaining <= 0 && max === 0)
        line = `Beräknad träningsbudget: 0 TRIMP – begränsas av ${factorLabel || 'modellen'}.`;
      else if (remaining <= 0) line = 'Ingen ytterligare träningsbelastning ryms i modellens dagsbudget.';
      else line = `${fmt(remaining)} TRIMP kvar enligt modellens dagsbudget.`;
      const progress = current !== null && max !== null && max > 0
        ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
      const currentAcwr = number(this._state('acwr')?.state);
      const budgetAcwr = number(a.projected_acwr);
      const differing = currentAcwr !== null && budgetAcwr !== null && Math.abs(currentAcwr - budgetAcwr) > 0.05;
      const planningDifference = a.planning_mode === 'load_priority' && excluded !== null && excluded > 0;
      let acwrContext = '';
      if (differing && planningDifference) {
        acwrContext = `<p class="acwr-context">${icon('mdi:information-outline')} Faktisk ACWR ${fmt(currentAcwr, 2)} omfattar dagens verkliga belastning. Budget-ACWR ${fmt(budgetAcwr, 2)} använder ett separat planeringsunderlag där ${fmt(excluded)} TRIMP från lågintensiva pass undantagits. Olika värden är därför förväntade.</p>`;
      } else if (differing) {
        acwrContext = `<p class="acwr-context caution">${icon('mdi:clock-alert-outline')} Faktisk ACWR ${fmt(currentAcwr, 2)} och budget-ACWR ${fmt(budgetAcwr, 2)} skiljer sig trots ${fmt(excluded ?? 0)} TRIMP undantagen lågintensiv belastning i dag. Värdena kommer från faktisk Fitness-historik respektive budgetens planeringsberäkning. Kontrollera att de avser samma dag och uppdateringstillfälle innan skillnaden tolkas.</p>`;
      }
      const diagnostics = a.planning_mode === 'load_priority' &&
        [actual, current, excluded].every((v) => v !== null)
        ? `<div class="breakdown-title">Belastning i dag</div><div class="breakdown">
          ${this._metric('Faktisk (TRIMP)', fmt(actual))}
          ${this._metric('Budgeträknad', fmt(current))}
          ${this._metric('Lågintensiv', fmt(excluded))}</div>` : '';
      const unknown = number(a.unknown_intensity_activity_count);
      return `<div class="section-title">${icon('mdi:gauge', 'round-icon')}<div>
        <strong>Dagens träningsbudget</strong><p>${esc(line)}</p></div></div>
        <div class="budget-values"><span>${fmt(current)} TRIMP</span><span>${fmt(max)} TRIMP</span></div>
        <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress.toFixed(0)}"><div style="width:${progress}%"></div></div>
        ${diagnostics}${unknown > 0 ? `<p class="small">${unknown} pass saknar säker klassning; inga automatiska undantag för dessa.</p>` : ''}
        <p class="small">${factorLabel ? `Begränsande faktor: <strong>${esc(factorLabel)}</strong>. ` : ''}
          Modellen skiljer på faktisk träningsbelastning och budgetförbrukning; detta är ingen träningsordination.</p>
        ${acwrContext}
        <div class="metrics four">${this._metric('Budget-ACWR', fmt(a.projected_acwr, 2))}
          ${this._metric('Budget-Strain', fmt(a.projected_strain))}
          ${this._metric('Budget-TSB', signed(a.projected_tsb))}
          ${this._metric('Budget-Ramp', signed(a.projected_ramp_rate))}</div>`;
    }

    _metric(label, value) {
      return `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
    }

    _evaluationHtml() {
      const s = this._state('evaluation');
      const selector = this._state('selector');
      const opts = attr(selector).options || [];
      const options = Array.isArray(opts) ? opts : [];
      const select = options.length ? `<select id="activity-selector" aria-label="Välj pass">
        ${options.map((option) => `<option value="${esc(option)}" ${option === selector.state ? 'selected' : ''}>${esc(option)}</option>`).join('')}
        </select>` : '<span class="small">Inga pass att välja</span>';
      const title = `<div class="evaluation-header">${icon('mdi:chart-timeline-variant-shimmer')}
        <strong>Passutvärdering</strong>${select}</div>`;
      if (!isPresent(s)) return title + this._panel('mdi:history', 'Pass saknas', 'Inväntar passutvärdering från Garmin.');
      const a = attr(s);
      const b = attr(this._state('budget'));
      const decisions = Array.isArray(b.activity_decisions) ? b.activity_decisions : [];
      const decision = decisions.find((d) => String(d.activity_id) === String(a.selected_activity_id)) || null;
      let source = '';
      if (decision) {
        const sName = { hr: 'Puls', power: 'Effekt', pace: 'Tempo', garmin: 'Garmin Load' }[decision.selected_source] || decision.selected_source || 'Okänd källa';
        const lane = { low: 'Låg intensitet', training: 'Träningsbelastning', unknown: 'Osäker intensitet' }[decision.intensity_lane] || 'Okänd intensitet';
        const disposition = decision.intensity_lane === 'low' && finite(decision.canonical_trimp)
          ? 'Undantagen från budgetförbrukning' : decision.intensity_lane === 'low'
            ? 'TRIMP saknas – inget undantag' : decision.intensity_lane === 'unknown'
              ? 'Inget automatiskt undantag' : 'Räknas mot dagsbudgeten';
        source = `<p class="small source"><strong>Load Priority</strong> · ${esc(sName)} · ${esc(lane)} · ${esc(disposition)}</p>`;
      } else if (a.selected_activity_id !== null && a.selected_activity_id !== undefined) {
        source = '<p class="small">Load Priority: dagens klassificering visas endast för dagens pass.</p>';
      }
      const power = finite(a.avg_power) || finite(a.normalized_power);
      const performances = finite(a.estimated_vo2max) || finite(a.estimated_ftp_watts);
      const post = [a.post_acwr, a.post_strain, a.post_tsb].some(finite);
      const message = a.assessment_id === 'recovery'
        ? 'Låg träningseffekt. Passet liknar återhämtning eller mycket lätt aktivitet.'
        : a.message || '';
      return `${title}<div class="eval-body">
        <div class="activity-heading">${icon(a.activity_icon || 'mdi:run-fast', 'round-icon')}
          <div><strong>${esc(a.activity_name || 'Aktivitet')}</strong>
          <span>${maybe(a.duration_minutes, ' min')} · Load ${fmt(a.garmin_training_load)} · TE ${fmt(a.aerobic_training_effect)} / ${fmt(a.anaerobic_training_effect)}</span></div></div>
        <div class="assessment"><strong>${esc(a.title || 'Ingen bedömning')}</strong><p>${esc(message)}</p></div>
        ${source}${this._gearHtml(a)}<div class="mini-title">Passdata</div><div class="metrics ${power ? 'two' : 'one'}">
          ${this._metric('Puls', `${fmt(a.avg_hr, 0)} / ${fmt(a.max_hr, 0)} bpm`)}
          ${power ? this._metric('Effekt', `${maybe(a.avg_power, ' W', 0)} / ${maybe(a.normalized_power, ' W NP', 0)}`) : ''}</div>
        ${performances ? `<div class="mini-title">Beräknad prestation</div><div class="metrics three">
          ${this._metric('VO₂max', fmt(a.estimated_vo2max))}${this._metric('FTP', maybe(a.estimated_ftp_watts, ' W', 0))}
          ${this._metric('Säkerhet', a.confidence_label || '–')}</div>` : ''}
        ${post ? `<div class="mini-title">Belastning för passets kalenderdag</div><div class="metrics three">
          ${this._metric('ACWR', fmt(a.post_acwr, 2))}${this._metric('Strain', fmt(a.post_strain))}
          ${this._metric('TSB', signed(a.post_tsb))}</div>` : ''}
      </div>`;
    }

    _styles() {
      return `:host{display:block;color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,inherit)}
        *{box-sizing:border-box}.dashboard{display:block;overflow:hidden;background:var(--ha-card-background,var(--card-background-color,#fff));border-radius:var(--ha-card-border-radius,12px)}
        .banner img{display:block;width:100%;height:140px;object-fit:cover;object-position:center}
        section{width:100%;min-width:0}section.graph{padding:8px 0}section.graph>garmin-fitness-card{display:block}
        section.budget,section.evaluation{margin-top:8px;border:1px solid var(--divider-color,#ddd);border-radius:12px;overflow:hidden}
        .insight{display:flex;gap:12px;padding:12px 14px;border-bottom:1px solid var(--divider-color,#ddd);align-items:flex-start;cursor:pointer}
        .insight.primary{min-height:104px;align-items:center;justify-content:center;text-align:center;flex-direction:column;gap:5px;padding:20px 14px}
        .insight-icon{--mdc-icon-size:21px;color:var(--info-color,#03a9f4);flex-shrink:0}.insight.warning .insight-icon{color:var(--error-color,#f44336)}
        .insight.caution .insight-icon{color:var(--warning-color,#ff9800)}.insight.positive .insight-icon{color:var(--success-color,#4caf50)}
        .insight-text{min-width:0;flex:1}.insight.primary .insight-text{width:100%;max-width:430px}.insight strong,.section-title strong,.evaluation-header strong{font-size:14px}.insight p,.section-title p,.notice p{margin:3px 0 0;font-size:12px;line-height:1.45}
        .insight small{font-size:12px;display:block;margin-top:4px}.insight-detail{width:100%;margin-top:10px;padding-top:10px;border-top:1px solid var(--divider-color,#ddd)}
        .focus-main{display:flex;align-items:center;justify-content:center;gap:16px}.focus-ring{width:68px;height:68px;border-radius:50%;padding:8px;flex:0 0 68px}.focus-ring>div{height:100%;border-radius:50%;background:var(--ha-card-background,var(--card-background-color,#fff));display:flex;flex-direction:column;align-items:center;justify-content:center}.focus-ring strong{font-size:15px}.focus-ring span{font-size:9px;color:var(--secondary-text-color)}
        .focus-legend{min-width:150px;display:grid;gap:5px}.focus-legend-row{display:grid;grid-template-columns:9px 1fr auto;gap:7px;align-items:center;font-size:11px}.focus-legend-row i{width:8px;height:8px;border-radius:50%;background:var(--secondary-text-color)}.focus-legend-row i.low{background:var(--info-color,#00bceb)}.focus-legend-row i.high{background:var(--warning-color,#ff9800)}.focus-legend-row i.anaerobic{background:var(--error-color,#f44336)}.focus-legend-row span{color:var(--secondary-text-color)}.focus-legend-row strong{font-size:11px}
        .focus-meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:10px}.focus-meta span{font-size:10px;color:var(--secondary-text-color);line-height:1.35}.focus-meta strong{display:block;font-size:12px;color:var(--primary-text-color)}
        .recovery-detail{display:grid;gap:10px}.recovery-meter-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;font-size:10px}.recovery-meter-head span{color:var(--secondary-text-color);text-align:left}.recovery-meter-head strong{font-size:11px;text-align:right;white-space:nowrap}.evidence-track{height:6px;margin-top:5px;border-radius:99px;background:rgba(128,128,128,.20);overflow:hidden}.evidence-track>div{height:100%;border-radius:99px;background:var(--warning-color,#ff9800)}
        .gear-items{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px;margin-top:8px}.gear-item{display:flex;gap:8px;align-items:center;border:1px solid var(--divider-color,#ddd);border-radius:10px;padding:9px;min-width:0;background:var(--secondary-background-color,var(--card-background-color,#fff))}.gear-item ha-icon{--mdc-icon-size:20px;color:var(--info-color,#00bceb)}.gear-item strong,.gear-item span{display:block;overflow-wrap:anywhere}.gear-item strong{font-size:12px}.gear-item span{font-size:10px;color:var(--secondary-text-color);margin-top:3px}
        .quality{display:flex;gap:9px;align-items:flex-start;padding:8px 13px;color:var(--warning-color,#b58900);border-bottom:1px solid var(--divider-color,#ddd)}
        .quality strong{display:block;font-size:12px}.quality span{display:block;font-size:11px;color:var(--secondary-text-color);margin-top:2px}
        .recent,.notice{display:flex;gap:11px;align-items:center;padding:12px 14px}.recent{cursor:pointer}.recent>ha-icon{color:var(--info-color,#03a9f4)}
        .recent strong,.notice strong{font-size:13px}.recent span{display:block;font-size:11px;color:var(--secondary-text-color);margin-top:3px;line-height:1.4}
        .notice{color:var(--secondary-text-color);line-height:1.4}.notice code{font-size:12px;overflow-wrap:anywhere}
        .budget{padding:12px}.section-title{display:flex;align-items:center;gap:12px}.round-icon{background:rgba(0,188,235,.15);border-radius:50%;padding:12px;width:47px;height:47px;color:var(--info-color,#00bceb);flex-shrink:0}
        .budget .round-icon{background:rgba(255,152,0,.14);color:var(--warning-color,#ff9800)}.section-title p{color:var(--secondary-text-color)}
        .budget-values{display:flex;justify-content:space-between;color:var(--secondary-text-color);font-size:11px;margin-top:13px}
        .progress{height:8px;background:rgba(128,128,128,.22);border-radius:99px;overflow:hidden;margin:5px 0 8px}.progress>div{height:100%;background:var(--info-color,#00bceb);border-radius:99px}
        .breakdown-title{text-align:center;font-weight:600;font-size:11px}.breakdown,.metrics{display:grid;gap:8px;min-width:0}.breakdown{grid-template-columns:repeat(3,minmax(0,1fr))}
        .metrics{margin-top:8px}.metrics.four{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:15px}.metrics.three{grid-template-columns:repeat(3,minmax(0,1fr))}.metrics.two{grid-template-columns:repeat(2,minmax(0,1fr))}.metrics.one{grid-template-columns:1fr}
        .metric{min-width:0;text-align:center}.metric span{display:block;font-size:10px;color:var(--secondary-text-color);overflow-wrap:anywhere}.metric strong{font-size:14px;display:block;margin-top:3px;overflow-wrap:anywhere}
        .small{font-size:11px;line-height:1.4;color:var(--secondary-text-color);margin:8px 0}.acwr-context{font-size:11px;line-height:1.4;color:var(--secondary-text-color);display:flex;align-items:flex-start;gap:5px;margin:9px 0}.acwr-context ha-icon{--mdc-icon-size:15px;color:var(--info-color,#00bceb);flex-shrink:0}.acwr-context.caution{color:var(--warning-color,#ff9800)}.acwr-context.caution ha-icon{color:var(--warning-color,#ff9800)}
        .evaluation-header{display:flex;align-items:center;gap:9px;padding:12px;border-bottom:1px solid var(--divider-color,#ddd)}.evaluation-header>ha-icon{color:var(--info-color,#00bceb)}
        .evaluation-header select{margin-left:auto;max-width:58%;min-width:0;border:1px solid var(--divider-color,#ddd);border-radius:12px;padding:7px;background:var(--secondary-background-color,var(--card-background-color,#fff));color:var(--primary-text-color);font:inherit;font-size:12px}
        .eval-body{padding:13px}.activity-heading{display:flex;align-items:center;gap:12px}.activity-heading strong{display:block;font-size:16px}.activity-heading span{display:block;color:var(--secondary-text-color);font-size:11px;line-height:1.5;margin-top:3px}
        .assessment{margin-top:17px}.assessment strong{font-size:14px}.assessment p{font-size:13px;color:var(--secondary-text-color);line-height:1.45;margin:5px 0}.mini-title{margin-top:17px;font-size:12px;font-weight:600;color:var(--secondary-text-color)}
        .eval-body .metric{text-align:left}.source{margin:8px 0}.source strong{color:var(--primary-text-color)}footer{text-align:right;font-size:12px;font-weight:600;line-height:1.4;color:var(--primary-text-color,#242424);opacity:1;padding:9px 12px}
        [data-more-info]:focus-visible,select:focus-visible{outline:2px solid var(--info-color,#00bceb);outline-offset:-2px}
        @media(max-width:360px){.breakdown{gap:3px}.metrics{gap:3px}.metric strong{font-size:12px}.evaluation-header select{max-width:51%}.focus-main{gap:10px}.focus-ring{width:60px;height:60px;flex-basis:60px}.focus-legend{min-width:135px}.focus-meta{grid-template-columns:1fr}}`;
    }
  }

  if (!customElements.get(TAG)) customElements.define(TAG, GarminFitnessDashboardCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === TAG)) {
    window.customCards.push({type: TAG, name: 'Garmin Fitness Dashboard (dev)',
      description: 'Insikter, befintliga grafer, belastningsbudget och passutvärdering.'});
  }
  console.info(`%cGARMIN FITNESS DASHBOARD v${VERSION}`, 'color:#00bceb;font-weight:bold');
})();
