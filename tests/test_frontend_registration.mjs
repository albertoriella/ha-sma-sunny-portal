import assert from "node:assert/strict";

const CARD_TAG = "sma-sunny-portal-energy-card";
const EDITOR_TAG = "sma-sunny-portal-energy-card-editor";
const HA_ROOT_TAG = "home-assistant";

const createRegistry = () => {
  const definitions = new Map();
  return {
    define(name, constructor) {
      if (definitions.has(name)) throw new Error(`duplicate definition: ${name}`);
      definitions.set(name, constructor);
    },
    get(name) {
      return definitions.get(name);
    },
  };
};

globalThis.HTMLElement = class HTMLElement {
  attachShadow() {
    this.shadowRoot = {};
    return this.shadowRoot;
  }
};
const pendingTimers = [];
globalThis.setTimeout = (callback) => {
  pendingTimers.push(callback);
  return pendingTimers.length;
};

const earlyRegistry = createRegistry();
globalThis.customElements = earlyRegistry;

await import(
  "../custom_components/sma_sunny_portal/frontend_assets/sma-sunny-portal-energy-card.js"
);

assert.equal(earlyRegistry.get(CARD_TAG), undefined);
assert.equal(earlyRegistry.get(EDITOR_TAG), undefined);
assert.equal(pendingTimers.length, 1);

const homeAssistantRegistry = createRegistry();
globalThis.customElements = homeAssistantRegistry;
homeAssistantRegistry.define(HA_ROOT_TAG, class HomeAssistant extends HTMLElement {});
pendingTimers.shift()();

assert.equal(homeAssistantRegistry.get(CARD_TAG)?.name, "SmaSunnyPortalEnergyCard");
assert.equal(
  homeAssistantRegistry.get(EDITOR_TAG)?.name,
  "SmaSunnyPortalEnergyCardEditor",
);
assert.equal(pendingTimers.length, 0);

const Card = homeAssistantRegistry.get(CARD_TAG);
const card = new Card();
const labels = {
  actual: "Actual",
  forecast: "Forecast",
  pv: "PV",
  consumption: "Consumption",
  surplus: "Surplus",
  deficit: "Deficit",
  power: "Power",
  noData: "No data",
  noForecast: "No forecast",
};
const graphData = {
  day_start_utc: "2026-10-05T00:00:00Z",
  day_end_utc: "2026-10-06T00:00:00Z",
  measurements: [
    {
      time_utc: "2026-10-05T10:00:00Z",
      pv_generation_w: 3000,
      total_consumption_w: 800,
      surplus_w: 2200,
    },
  ],
  predictions: [
    {
      time_utc: "2026-10-05T11:00:00Z",
      pv_generation_w: 2500,
      total_consumption_w: 3200,
      surplus_w: -700,
    },
  ],
};

const allSeriesGraph = card._renderGraph(graphData, labels, "UTC", "en");
assert.equal((allSeriesGraph.match(/<svg\b/g) ?? []).length, 1);
assert.equal((allSeriesGraph.match(/class="zero-line"/g) ?? []).length, 1);
for (const key of [
  "actual_pv",
  "forecast_pv",
  "actual_consumption",
  "forecast_consumption",
  "surplus",
  "deficit",
]) {
  assert.match(allSeriesGraph, new RegExp(`data-series="${key}" aria-pressed="true"`));
  assert.match(allSeriesGraph, new RegExp(`data-series-path="${key}"`));
}

card._visibleSeries.delete("forecast_pv");
const filteredGraph = card._renderGraph(graphData, labels, "UTC", "en");
assert.match(filteredGraph, /data-series="forecast_pv" aria-pressed="false"/);
assert.doesNotMatch(filteredGraph, /data-series-path="forecast_pv"/);

console.log("Frontend registration and unified-series graph tests passed");
