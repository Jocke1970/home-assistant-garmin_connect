'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const registry = new Map();
class FakeElement {
  attachShadow() {
    this.shadowRoot = {
      innerHTML: '',
      addEventListener: () => {},
      getElementById: () => null,
    };
  }
}
const sandbox = {
  HTMLElement: FakeElement,
  customElements: { get: (k) => registry.get(k), define: (k, v) => registry.set(k, v) },
  window: { customCards: [] },
  console,
  CustomEvent: class {},
};
const source = fs.readFileSync(path.join(__dirname, '../garmin-fitness-dashboard-card.js'), 'utf8');
vm.runInNewContext(source, sandbox, { filename: 'garmin-fitness-dashboard-card.js' });
const Card = registry.get('garmin-fitness-dashboard-card');
assert.ok(Card, 'registered dashboard card');
const card = new Card();
const e = {
  insights: 'sensor.garmin_insights_overview',
  budget: 'sensor.garmin_fitness_garmin_daily_load_budget',
  evaluation: 'sensor.garmin_activity_evaluation',
  selector: 'select.garmin_activity_evaluation',
  acwr: 'sensor.garmin_fitness_acwr',
};
card._config = { entities: e, graph_days: 90 };
const snapshot = {
  [e.budget]: { state: '0', attributes: {
    recommended_max_load: 0, remaining_load: 0, canonical_current_load: 63.4,
    budget_consuming_load: 0, excluded_low_intensity_load: 63.4,
    planning_mode: 'load_priority', projected_acwr: 1.81,
    structural_limiting_factor: 'acwr', structural_limiting_factor_label: 'ACWR',
    projected_strain: 0, projected_tsb: -1.6, projected_ramp_rate: -0.3,
  } },
  [e.acwr]: { state: '2.48', attributes: {} },
  [e.insights]: { state: 'warning', attributes: {
    snapshot_date: '2026-09-17',
    presented_results: [
      { id: 'load_spike', title: '<script>alert(1)</script>', severity: 'warning',
        message: 'Belastningen har ökat snabbt', icon: 'mdi:trending-up',
        evidence: [{ code: 'acwr_above_spike_threshold', value: 2.48 }] },
      { id: 'recovery_caution', title: 'Återhämtningssignalerna är begränsade',
        severity: 'caution', message: 'Flera signaler pekar åt ett försiktigare håll.',
        icon: 'mdi:heart-pulse', evidence: [
          { code: 'body_battery_low', label: 'Body Battery låg', value: 10, threshold: 30 },
          { code: 'hrv_below_balanced_baseline', label: 'HRV under balanserad baslinje',
            value: 40, threshold: 43 },
        ] },
      { id: 'load_focus_imbalance', title: 'Träningsfokuset är ensidigt',
        severity: 'info', message: 'Training Effect är koncentrerad till en belastningstyp.',
        icon: 'mdi:chart-donut', evidence: [
          { code: 'dominant_focus.low_aerobic', label: 'Dominerande träningsfokus: low aerobic',
            value: 16.8, threshold: null },
          { code: 'recent_focus_activity_count', label: 'Aktiviteter med Training Effect',
            value: 8, threshold: 3 },
          { code: 'dominance_ratio', label: 'Dominanskvot för träningsfokus',
            value: 42, threshold: 1.5 },
        ] },
    ],
    load_focus: { low_aerobic: 16.8, high_aerobic: 0.4, anaerobic: 0 },
    data_quality: { training_complete: true, load_focus_complete: true,
      missing_fields: ['recovery.resting_hr'], missing_sources: ['hrv'], stale_fields: [] },
    recent_activities: [{ date: '2026-09-17', activity_type: 'walking',
      duration_minutes: 25.7, garmin_training_load: 16.8,
      aerobic_training_effect: 2.2, anaerobic_training_effect: 0 }],
  } },
  [e.evaluation]: { state: 'aerobic', attributes: {
    selected_activity_id: '42', activity_name: 'Promenad',
    duration_minutes: 25.7, garmin_training_load: 16.8,
    aerobic_training_effect: 2.2, anaerobic_training_effect: 0,
    title: 'Aerobt pass', message: 'Träningseffekt', avg_hr: 106, max_hr: 130,
    post_acwr: 2.48, post_strain: 12.8, post_tsb: -14.5,
  } },
  [e.selector]: { state: 'Idag · Promenad', attributes: { options: [
    'Idag · Promenad', 'Igår · Rodd',
  ] } },
};
card._hass = { states: snapshot, callService() {} };
let html = card._budgetHtml();
assert.match(html, /Faktisk \(TRIMP\)<\/span><strong>63,4/);
assert.match(html, /Budgeträknad<\/span><strong>0,0/);
assert.match(html, /Lågintensiv<\/span><strong>63,4/);
assert.match(html, /begränsas av ACWR \(1,81\)/);
assert.doesNotMatch(html, /Träningsbudgeten är uppnådd/);
assert.match(html, /Olika värden är därför förväntade/);
assert.match(html, /63,4 TRIMP från lågintensiva pass undantagits/);
assert.doesNotMatch(html, /inte synkroniserade/);
html = card._insightsHtml();
assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
assert.doesNotMatch(html, /<script>/);
assert.match(html, /Återhämtningsunderlag ofullständigt/);
assert.match(html, /Body Battery låg/);
assert.match(html, /10 · gräns 30/);
assert.match(html, /HRV under balanserad baslinje/);
assert.match(html, /40 · gräns 43/);
assert.match(html, /Träningsfokuset är ensidigt/);
assert.match(html, /Låg aerob/);
assert.match(html, /16,8/);
assert.match(html, /8<\/strong> pass med Training Effect/);
assert.match(html, /42,0× · gräns 1,5×/);
assert.match(html, /Senaste aktivitet · Promenad/);
html = card._evaluationHtml();
assert.match(html, /Idag · Promenad/);
snapshot[e.evaluation].attributes.linked_gear = [
  { gear_uuid: 'gear-1', name: 'Runnershoes', gear_type: 'Shoes',
    custom_make_model: 'Nike Pegasus' },
  { gear_uuid: 'gear-2', name: 'Garmin  Fenix 7 Pro', gear_type: 'Other',
    custom_make_model: 'Garmin Fenix 7 Pro' },
];
html = card._evaluationHtml();
assert.match(html, /Utrustning som användes/);
assert.match(html, /Nike Pegasus/);
assert.match(html, /Garmin Fenix 7 Pro/);
snapshot[e.evaluation].attributes.linked_gear = [
  { name: '<img src=x onerror=alert(1)>' },
];
html = card._evaluationHtml();
assert.match(html, /&lt;img/);
assert.doesNotMatch(html, /<img/);
snapshot[e.evaluation].attributes.linked_gear = [];
html = card._evaluationHtml();
assert.match(html, /Ingen kopplad utrustning/);
delete snapshot[e.evaluation].attributes.linked_gear;
html = card._evaluationHtml();
assert.doesNotMatch(html, /Utrustning som användes/);

assert.match(html, /Efter passet \(faktisk belastning\)/);
assert.doesNotMatch(html, /Undantagen från budgetförbrukning/);
snapshot[e.budget].attributes.activity_decisions = [{
  activity_id: 42, selected_source: 'hr', intensity_lane: 'low', canonical_trimp: 63.4,
}];
html = card._evaluationHtml();
assert.match(html, /Undantagen från budgetförbrukning/);
// A difference without any excluded low-intensity load is not automatically explained.
snapshot[e.budget].attributes.excluded_low_intensity_load = 0;
html = card._budgetHtml();
assert.match(html, /Kontrollera att de avser samma dag/);
assert.doesNotMatch(html, /Olika värden är därför förväntade/);
snapshot[e.budget].attributes.excluded_low_intensity_load = 63.4;
// Equal ACWR readings should not show either discrepancy notice.
snapshot[e.acwr].state = '1.81';
html = card._budgetHtml();
assert.doesNotMatch(html, /Kontrollera att de avser samma dag|Olika värden är därför förväntade/);
snapshot[e.acwr].state = '2.48';
assert.equal(card.cardVersion, '0.1.1-dev.4');
assert.ok(sandbox.window.customCards.some((c) => c.type === 'garmin-fitness-dashboard-card'));
console.log('PASS: frontend smoke assertions (budget, explanatory ACWR, XSS, insights, selection, evaluation, version)');

// A mounted chart must not be recreated after HA state updates, otherwise its
// selected range and expanded graphs reset and Recorder can be queried again.
class FakeGraph { setConfig(config) { this.config = config; } }
registry.set('garmin-fitness-card', FakeGraph);
sandbox.document = { createElement: () => new FakeGraph() };
const holder = { children: [], replaceChildren() { this.children = []; },
  appendChild(node) { this.children.push(node); } };
card._nodes = { insights: { innerHTML: '' }, budget: { innerHTML: '' },
  evaluation: { innerHTML: '' }, graph: holder };
card._refresh();
const sameGraph = card._graph;
assert.equal(holder.children.length, 1);
assert.equal(sameGraph.config.days, 90);
assert.equal(sameGraph.hass, card._hass);
card._hass = { states: { ...snapshot }, callService() {} };
card._hass.states[e.acwr] = { state: '2.50', last_updated: 'new', attributes: {} };
card._refresh();
assert.equal(card._graph, sameGraph, 'graph instance preserved');
assert.equal(holder.children.length, 1, 'chart not duplicated');
console.log('PASS: graph instance and configuration retained after HA refresh');

const dashboardCss = card._styles();
assert.match(dashboardCss, /footer\{[^}]*font-size:12px;[^}]*color:var\(--primary-text-color/);
assert.doesNotMatch(dashboardCss, /footer\{[^}]*color:var\(--secondary-text-color/);
console.log('PASS: dashboard footer contrast and readability');
