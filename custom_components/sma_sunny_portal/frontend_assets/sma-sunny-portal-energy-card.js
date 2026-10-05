const CARD_TAG = "sma-sunny-portal-energy-card";
const EDITOR_TAG = "sma-sunny-portal-energy-card-editor";
const HA_ROOT_TAG = "home-assistant";
const HISTORY_COMMAND = "sma_sunny_portal/history";
const ENTRIES_COMMAND = "sma_sunny_portal/entries";
const FORECAST_MODES = ["latest", "day_ahead", "rolling"];
const SERIES_KEYS = [
  "actual_pv",
  "forecast_pv",
  "actual_consumption",
  "forecast_consumption",
  "surplus",
  "deficit",
];

const STRINGS = {
  en: {
    title: "SMA Energy Live",
    previousDay: "Previous day",
    nextDay: "Next day",
    today: "Today",
    refresh: "Refresh",
    mode: "Forecast",
    latest: "Latest snapshot",
    day_ahead: "Day ahead",
    rolling: "Rolling",
    latestHelp: "Newest archived forecast for this date",
    day_aheadHelp: "Last forecast saved before local midnight",
    rollingHelp: "Newest forecast known at each interval",
    loading: "Loading archived curves…",
    noData: "No archived data is available for this date.",
    noForecast: "No forecast exists for this selection mode.",
    error: "The archived curves could not be loaded.",
    noEntries: "No SMA Sunny Portal Forecast configuration was found.",
    multipleEntries:
      "More than one SMA configuration exists. Select one in the card editor.",
    actual: "Actual",
    forecast: "Forecast",
    pv: "PV",
    consumption: "Consumption",
    surplus: "Surplus",
    deficit: "Deficit",
    power: "PV, consumption, and balance power",
    balance: "Surplus and deficit",
    forecastIssued: "Forecast issued",
    forecastVersions: "forecast versions",
    archive: "Archive",
    firstData: "First data",
    lastData: "Last data",
    at: "at",
    configuration: "Card configuration",
    entry: "SMA configuration",
    automatic: "Automatic (when only one exists)",
    customTitle: "Card title",
    defaultMode: "Default forecast mode",
    editorHelp:
      "The configuration is detected automatically when only one SMA entry exists.",
    loaded: "loaded",
    unavailable: "not loaded",
  },
  it: {
    title: "SMA Energy Live",
    previousDay: "Giorno precedente",
    nextDay: "Giorno successivo",
    today: "Oggi",
    refresh: "Aggiorna",
    mode: "Previsione",
    latest: "Ultima disponibile",
    day_ahead: "Giorno prima",
    rolling: "Progressiva",
    latestHelp: "Previsione archiviata più recente per questa data",
    day_aheadHelp: "Ultima previsione salvata prima della mezzanotte locale",
    rollingHelp: "Previsione più recente nota in ciascun intervallo",
    loading: "Caricamento delle curve archiviate…",
    noData: "Non sono disponibili dati archiviati per questa data.",
    noForecast: "Non esiste una previsione per questa modalità.",
    error: "Impossibile caricare le curve archiviate.",
    noEntries: "Non è stata trovata alcuna configurazione SMA Sunny Portal Forecast.",
    multipleEntries:
      "Esiste più di una configurazione SMA. Selezionane una nell’editor della card.",
    actual: "Reale",
    forecast: "Previsione",
    pv: "FV",
    consumption: "Consumo",
    surplus: "Surplus",
    deficit: "Deficit",
    power: "Potenza FV, consumo e bilancio",
    balance: "Surplus e deficit",
    forecastIssued: "Previsione emessa",
    forecastVersions: "versioni previsionali",
    archive: "Archivio",
    firstData: "Primo dato",
    lastData: "Ultimo dato",
    at: "alle",
    configuration: "Configurazione card",
    entry: "Configurazione SMA",
    automatic: "Automatica (se ne esiste una sola)",
    customTitle: "Titolo della card",
    defaultMode: "Modalità di previsione predefinita",
    editorHelp:
      "La configurazione viene rilevata automaticamente quando esiste una sola voce SMA.",
    loaded: "caricata",
    unavailable: "non caricata",
  },
};

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const languageFor = (hass) => {
  const language = hass?.locale?.language ?? globalThis.navigator?.language ?? "en";
  return String(language).toLowerCase().startsWith("it") ? "it" : "en";
};

const stringsFor = (hass) => STRINGS[languageFor(hass)];

const timezoneFor = (hass) => hass?.config?.time_zone ?? "UTC";

const localeFor = (hass) => hass?.locale?.language ?? globalThis.navigator?.language ?? "en";

const dateInZone = (value, timeZone) => {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
};

const shiftDate = (value, days) => {
  const [year, month, day] = value.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days, 12));
  return shifted.toISOString().slice(0, 10);
};

const formatCalendarDate = (value, locale) => {
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, {
    timeZone: "UTC",
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(Date.UTC(year, month - 1, day, 12)));
};

const formatTime = (value, timeZone, locale) =>
  new Intl.DateTimeFormat(locale, {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

const formatDateTime = (value, timeZone, locale) =>
  new Intl.DateTimeFormat(locale, {
    timeZone,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

const formatPower = (value, locale, signed = false) => {
  if (!Number.isFinite(Number(value))) return "—";
  const numeric = Number(value);
  const absolute = Math.abs(numeric);
  const formatter = new Intl.NumberFormat(locale, {
    maximumFractionDigits: absolute >= 1000 ? 2 : 0,
    signDisplay: signed ? "exceptZero" : "auto",
  });
  return absolute >= 1000
    ? `${formatter.format(numeric / 1000)} kW`
    : `${formatter.format(numeric)} W`;
};

const niceMaximum = (value) => {
  if (!Number.isFinite(value) || value <= 0) return 1000;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const multiplier = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return Math.max(1000, multiplier * magnitude);
};

const pathFor = (points, key, xFor, yFor, maximumGapMs) => {
  let path = "";
  let previousTime = null;
  for (const point of points) {
    const timestamp = Date.parse(point.time_utc);
    const value = Number(point[key]);
    if (!Number.isFinite(timestamp) || !Number.isFinite(value)) continue;
    const command =
      previousTime === null || timestamp - previousTime > maximumGapMs ? "M" : "L";
    path += `${command}${xFor(timestamp).toFixed(2)},${yFor(value).toFixed(2)} `;
    previousTime = timestamp;
  }
  return path.trim();
};

const signedPathFor = (points, key, sign, xFor, yFor, maximumGapMs) => {
  let path = "";
  let previousTime = null;
  for (const point of points) {
    const timestamp = Date.parse(point.time_utc);
    const value = Number(point[key]);
    const accepted = sign === "positive" ? value >= 0 : value <= 0;
    if (!Number.isFinite(timestamp) || !Number.isFinite(value) || !accepted) {
      previousTime = null;
      continue;
    }
    const command =
      previousTime === null || timestamp - previousTime > maximumGapMs ? "M" : "L";
    path += `${command}${xFor(timestamp).toFixed(2)},${yFor(value).toFixed(2)} `;
    previousTime = timestamp;
  }
  return path.trim();
};

const nearestPoint = (points, targetTime) => {
  let nearest = null;
  let distance = Number.POSITIVE_INFINITY;
  for (const point of points) {
    const currentDistance = Math.abs(Date.parse(point.time_utc) - targetTime);
    if (currentDistance < distance) {
      nearest = point;
      distance = currentDistance;
    }
  }
  return nearest;
};

const CARD_STYLES = `
  :host {
    display: block;
  }
  ha-card {
    overflow: hidden;
    padding: 18px 18px 14px;
  }
  .header {
    align-items: center;
    display: flex;
    gap: 12px;
    justify-content: space-between;
    margin-bottom: 14px;
  }
  .title {
    color: var(--primary-text-color);
    font-size: 1.25rem;
    font-weight: 600;
    line-height: 1.2;
  }
  .date-label {
    color: var(--secondary-text-color);
    font-size: 0.86rem;
    margin-top: 4px;
  }
  .controls {
    align-items: center;
    display: grid;
    gap: 8px;
    grid-template-columns: auto minmax(132px, auto) auto auto minmax(145px, auto) auto;
    margin-bottom: 7px;
  }
  button,
  input,
  select {
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, #d8d8d8);
    border-radius: 8px;
    box-sizing: border-box;
    color: var(--primary-text-color);
    font: inherit;
    min-height: 38px;
  }
  button {
    cursor: pointer;
    padding: 0 12px;
  }
  button.icon {
    font-size: 1.3rem;
    min-width: 40px;
    padding: 0;
  }
  button:hover:not(:disabled) {
    background: var(--secondary-background-color);
  }
  button:disabled {
    cursor: default;
    opacity: 0.35;
  }
  input,
  select {
    padding: 0 9px;
    width: 100%;
  }
  .mode-help {
    color: var(--secondary-text-color);
    font-size: 0.78rem;
    margin: 0 0 12px;
    min-height: 1.2em;
  }
  .metrics {
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(6, minmax(88px, 1fr));
    margin: 10px 0 14px;
  }
  .metric {
    background: color-mix(in srgb, var(--secondary-background-color) 72%, transparent);
    border-radius: 10px;
    min-width: 0;
    padding: 9px 10px;
  }
  .metric-name {
    color: var(--secondary-text-color);
    font-size: 0.72rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .metric-value {
    color: var(--primary-text-color);
    font-size: 1rem;
    font-weight: 600;
    margin-top: 3px;
  }
  .metric-time {
    color: var(--secondary-text-color);
    font-size: 0.68rem;
    margin-top: 2px;
  }
  .chart-wrap {
    min-height: 260px;
    position: relative;
  }
  svg {
    display: block;
    height: auto;
    overflow: visible;
    touch-action: pan-y;
    width: 100%;
  }
  .grid {
    stroke: var(--divider-color, #d8d8d8);
    stroke-width: 1;
  }
  .axis-label,
  .tick-label {
    fill: var(--secondary-text-color, #777);
    font-family: sans-serif;
  }
  .axis-label {
    font-size: 14px;
    font-weight: 600;
  }
  .tick-label {
    font-size: 12px;
  }
  .line {
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 3;
    vector-effect: non-scaling-stroke;
  }
  .forecast-line {
    stroke-dasharray: 8 6;
    stroke-width: 2.5;
  }
  .actual-pv { stroke: var(--warning-color, #f2c037); }
  .forecast-pv { stroke: #f5a623; }
  .actual-consumption { stroke: var(--primary-color, #03a9f4); }
  .forecast-consumption { stroke: #6574cd; }
  .positive { stroke: var(--success-color, #43a047); }
  .negative { stroke: var(--error-color, #db4437); }
  .zero-line { stroke: var(--secondary-text-color, #777); stroke-width: 1.2; }
  .now-line { stroke: var(--accent-color, #e91e63); stroke-dasharray: 3 5; }
  .hover-line { stroke: var(--primary-text-color, #222); stroke-width: 1; }
  .hit-area { fill: transparent; cursor: crosshair; }
  .legend {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    font-size: 0.76rem;
    gap: 4px 8px;
    margin: 5px 0 0 68px;
  }
  .legend-item {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 8px;
    color: var(--secondary-text-color);
    cursor: pointer;
    display: inline-flex;
    gap: 5px;
    min-height: 28px;
    padding: 3px 6px;
  }
  .legend-item:hover {
    background: var(--secondary-background-color);
  }
  .legend-item[aria-pressed="false"] {
    opacity: 0.42;
  }
  .legend-check {
    align-items: center;
    background: var(--series-color);
    border: 2px solid var(--series-color);
    border-radius: 50%;
    color: #fff;
    display: inline-flex;
    font-size: 10px;
    font-weight: 700;
    height: 14px;
    justify-content: center;
    line-height: 1;
    width: 14px;
  }
  .legend-item[aria-pressed="false"] .legend-check {
    background: transparent;
    color: transparent;
  }
  .legend-line {
    border-color: var(--series-color);
    border-top-style: solid;
    border-top-width: 3px;
    display: inline-block;
    width: 22px;
  }
  .legend-line.dashed { border-top-style: dashed; }
  .legend-item.pv-actual { --series-color: var(--warning-color, #f2c037); }
  .legend-item.pv-forecast { --series-color: #f5a623; }
  .legend-item.consumption-actual { --series-color: var(--primary-color, #03a9f4); }
  .legend-item.consumption-forecast { --series-color: #6574cd; }
  .legend-item.surplus { --series-color: var(--success-color, #43a047); }
  .legend-item.deficit { --series-color: var(--error-color, #db4437); }
  .tooltip {
    background: color-mix(in srgb, var(--card-background-color, #fff) 94%, transparent);
    border: 1px solid var(--divider-color, #d8d8d8);
    border-radius: 8px;
    box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgb(0 0 0 / 18%));
    color: var(--primary-text-color);
    display: none;
    font-size: 0.75rem;
    max-width: 230px;
    padding: 8px 10px;
    pointer-events: none;
    position: absolute;
    top: 30px;
    z-index: 2;
  }
  .tooltip.visible { display: block; }
  .tooltip-title { font-weight: 600; margin-bottom: 4px; }
  .tooltip-row { display: flex; gap: 10px; justify-content: space-between; }
  .message {
    align-items: center;
    color: var(--secondary-text-color);
    display: flex;
    justify-content: center;
    min-height: 180px;
    padding: 25px;
    text-align: center;
  }
  .message.error { color: var(--error-color, #db4437); }
  .footer {
    color: var(--secondary-text-color);
    display: flex;
    flex-wrap: wrap;
    font-size: 0.7rem;
    gap: 5px 16px;
    justify-content: space-between;
    margin-top: 10px;
  }
  .spinner {
    animation: spin 0.9s linear infinite;
    border: 2px solid var(--divider-color);
    border-radius: 50%;
    border-top-color: var(--primary-color);
    height: 18px;
    margin-right: 9px;
    width: 18px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 760px) {
    ha-card { padding: 14px 10px 12px; }
    .controls { grid-template-columns: auto 1fr auto auto; }
    .controls select { grid-column: 1 / span 3; }
    .controls .refresh { grid-column: 4; grid-row: 2; }
    .metrics { grid-template-columns: repeat(3, minmax(82px, 1fr)); }
    .legend { margin-left: 48px; }
  }
`;

class SmaSunnyPortalEnergyCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._date = null;
    this._mode = "latest";
    this._entryId = null;
    this._data = null;
    this._error = null;
    this._loading = false;
    this._started = false;
    this._requestSequence = 0;
    this._visibleSeries = new Set(SERIES_KEYS);
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    if (config.config_entry_id !== undefined && typeof config.config_entry_id !== "string") {
      throw new Error("config_entry_id must be a string");
    }
    if (config.default_mode !== undefined && !FORECAST_MODES.includes(config.default_mode)) {
      throw new Error("default_mode must be latest, day_ahead, or rolling");
    }
    this._config = { ...config };
    this._mode = config.default_mode ?? "latest";
    this._entryId = config.config_entry_id ?? null;
    this._data = null;
    this._error = null;
    this._started = false;
    this._render();
    this._start();
  }

  set hass(value) {
    this._hass = value;
    if (!this._date) this._date = dateInZone(new Date(), timezoneFor(value));
    this._start();
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return {
      columns: 12,
      rows: 8,
      min_columns: 6,
      min_rows: 5,
    };
  }

  connectedCallback() {
    this._render();
    this._start();
  }

  _start() {
    if (this._started || !this.isConnected || !this._hass || !this._config) return;
    this._started = true;
    queueMicrotask(() => this._load());
  }

  async _resolveEntryId() {
    if (this._entryId) return this._entryId;
    const result = await this._hass.callWS({ type: ENTRIES_COMMAND });
    const entries = Array.isArray(result?.entries) ? result.entries : [];
    if (entries.length === 1) {
      this._entryId = entries[0].entry_id;
      return this._entryId;
    }
    const error = new Error(entries.length === 0 ? "no_entries" : "multiple_entries");
    error.code = entries.length === 0 ? "no_entries" : "multiple_entries";
    throw error;
  }

  async _load() {
    if (!this._hass || !this._date) return;
    const sequence = ++this._requestSequence;
    this._loading = true;
    this._error = null;
    this._render();
    try {
      const entryId = await this._resolveEntryId();
      const data = await this._hass.callWS({
        type: HISTORY_COMMAND,
        config_entry_id: entryId,
        date: this._date,
        mode: this._mode,
      });
      if (sequence !== this._requestSequence) return;
      this._data = data;
    } catch (error) {
      if (sequence !== this._requestSequence) return;
      this._data = null;
      this._error = error;
    } finally {
      if (sequence === this._requestSequence) {
        this._loading = false;
        this._render();
      }
    }
  }

  _changeDate(days) {
    this._date = shiftDate(this._date, days);
    this._load();
  }

  _navigationBounds() {
    const timezone = timezoneFor(this._hass);
    const first = this._data?.archive?.first_available_utc;
    const last = this._data?.archive?.last_available_utc;
    return {
      firstDate: first ? dateInZone(new Date(first), timezone) : null,
      lastDate: last ? dateInZone(new Date(last), timezone) : null,
    };
  }

  _renderMetrics(measurements, predictions, labels, timezone, locale) {
    const actual = measurements.at(-1) ?? null;
    const now = Date.now();
    const forecast =
      predictions.find((point) => Date.parse(point.time_utc) >= now) ??
      predictions.at(-1) ??
      null;
    const metric = (name, value, point) => `
      <div class="metric">
        <div class="metric-name">${escapeHtml(name)}</div>
        <div class="metric-value">${escapeHtml(value)}</div>
        <div class="metric-time">${point ? escapeHtml(formatTime(point.time_utc, timezone, locale)) : "—"}</div>
      </div>`;
    return `
      <div class="metrics">
        ${metric(`${labels.actual} ${labels.pv}`, formatPower(actual?.pv_generation_w, locale), actual)}
        ${metric(`${labels.actual} ${labels.consumption}`, formatPower(actual?.total_consumption_w, locale), actual)}
        ${metric(labels.surplus, formatPower(actual?.surplus_w, locale, true), actual)}
        ${metric(`${labels.forecast} ${labels.pv}`, formatPower(forecast?.pv_generation_w, locale), forecast)}
        ${metric(`${labels.forecast} ${labels.consumption}`, formatPower(forecast?.total_consumption_w, locale), forecast)}
        ${metric(`${labels.forecast} ${labels.surplus}`, formatPower(forecast?.surplus_w, locale, true), forecast)}
      </div>`;
  }

  _renderGraph(data, labels, timezone, locale) {
    const measurements = Array.isArray(data.measurements) ? data.measurements : [];
    const predictions = Array.isArray(data.predictions) ? data.predictions : [];
    const startTime = Date.parse(data.day_start_utc);
    const endTime = Date.parse(data.day_end_utc);
    const width = 1000;
    const left = 68;
    const right = 18;
    const plotWidth = width - left - right;
    const chartTop = 38;
    const chartHeight = 315;
    const chartBottom = chartTop + chartHeight;
    const timeLabelY = chartBottom + 29;
    const xFor = (timestamp) =>
      left + ((timestamp - startTime) / (endTime - startTime)) * plotWidth;
    const valuesFor = (points, key) =>
      points.map((point) => Number(point[key])).filter(Number.isFinite);
    const visibleValues = [];
    if (this._visibleSeries.has("actual_pv")) {
      visibleValues.push(...valuesFor(measurements, "pv_generation_w"));
    }
    if (this._visibleSeries.has("forecast_pv")) {
      visibleValues.push(...valuesFor(predictions, "pv_generation_w"));
    }
    if (this._visibleSeries.has("actual_consumption")) {
      visibleValues.push(...valuesFor(measurements, "total_consumption_w"));
    }
    if (this._visibleSeries.has("forecast_consumption")) {
      visibleValues.push(...valuesFor(predictions, "total_consumption_w"));
    }
    const allBalanceValues = valuesFor([...measurements, ...predictions], "surplus_w");
    if (this._visibleSeries.has("surplus")) {
      visibleValues.push(...allBalanceValues.filter((value) => value >= 0));
    }
    if (this._visibleSeries.has("deficit")) {
      visibleValues.push(...allBalanceValues.filter((value) => value <= 0));
    }
    const positiveMaximum = niceMaximum(
      Math.max(0, ...visibleValues.filter((value) => value >= 0)),
    );
    const negativeMagnitude = Math.max(
      0,
      ...visibleValues.filter((value) => value < 0).map(Math.abs),
    );
    const negativeMaximum = negativeMagnitude > 0 ? niceMaximum(negativeMagnitude) : 0;
    const axisMinimum = -negativeMaximum;
    const axisMaximum = positiveMaximum;
    const axisSpan = axisMaximum - axisMinimum;
    const yFor = (value) => chartTop + ((axisMaximum - value) / axisSpan) * chartHeight;
    const zeroY = yFor(0);

    const actualPvPath = pathFor(measurements, "pv_generation_w", xFor, yFor, 20 * 60 * 1000);
    const actualConsumptionPath = pathFor(
      measurements,
      "total_consumption_w",
      xFor,
      yFor,
      20 * 60 * 1000,
    );
    const forecastPvPath = pathFor(predictions, "pv_generation_w", xFor, yFor, 50 * 60 * 1000);
    const forecastConsumptionPath = pathFor(
      predictions,
      "total_consumption_w",
      xFor,
      yFor,
      50 * 60 * 1000,
    );
    const actualPositivePath = signedPathFor(
      measurements,
      "surplus_w",
      "positive",
      xFor,
      yFor,
      20 * 60 * 1000,
    );
    const actualNegativePath = signedPathFor(
      measurements,
      "surplus_w",
      "negative",
      xFor,
      yFor,
      20 * 60 * 1000,
    );
    const forecastPositivePath = signedPathFor(
      predictions,
      "surplus_w",
      "positive",
      xFor,
      yFor,
      50 * 60 * 1000,
    );
    const forecastNegativePath = signedPathFor(
      predictions,
      "surplus_w",
      "negative",
      xFor,
      yFor,
      50 * 60 * 1000,
    );

    const horizontalGrid = Array.from({ length: 7 }, (_, index) => {
      const ratio = index / 6;
      const y = chartTop + ratio * chartHeight;
      const value = axisMaximum - ratio * axisSpan;
      if (Math.abs(value) < axisSpan / 1000) return "";
      return `
        <line class="grid" x1="${left}" x2="${width - right}" y1="${y}" y2="${y}" />
        <text class="tick-label" x="${left - 9}" y="${y + 4}" text-anchor="end">${escapeHtml(formatPower(value, locale))}</text>`;
    }).join("");
    const verticalGrid = Array.from({ length: 7 }, (_, index) => {
      const ratio = index / 6;
      const timestamp = startTime + (endTime - startTime) * ratio;
      const x = left + plotWidth * ratio;
      return `
        <line class="grid" x1="${x}" x2="${x}" y1="${chartTop}" y2="${chartBottom}" />
        <text class="tick-label" x="${x}" y="${timeLabelY}" text-anchor="middle">${escapeHtml(formatTime(timestamp, timezone, locale))}</text>`;
    }).join("");
    const now = Date.now();
    const nowLine =
      now >= startTime && now < endTime
        ? `<line class="now-line" x1="${xFor(now)}" x2="${xFor(now)}" y1="${chartTop}" y2="${chartBottom}" />`
        : "";
    const noData = measurements.length === 0 && predictions.length === 0;
    const missingForecast = measurements.length > 0 && predictions.length === 0;
    const legendButton = (key, style, lineStyle, text) => {
      const visible = this._visibleSeries.has(key);
      return `
        <button class="legend-item ${style}" type="button" data-series="${key}" aria-pressed="${visible}">
          <span class="legend-check" aria-hidden="true">${visible ? "✓" : ""}</span>
          <span class="legend-line ${lineStyle}" aria-hidden="true"></span>
          <span>${escapeHtml(text)}</span>
        </button>`;
    };

    return `
      ${this._renderMetrics(measurements, predictions, labels, timezone, locale)}
      <div class="chart-wrap">
        <div class="tooltip" role="status"></div>
        <svg viewBox="0 0 ${width} 400" role="img" aria-label="${escapeHtml(labels.power)}">
          <text class="axis-label" x="${left}" y="20">${escapeHtml(labels.power)}</text>
          ${horizontalGrid}
          ${verticalGrid}
          <line class="zero-line" x1="${left}" x2="${width - right}" y1="${zeroY}" y2="${zeroY}" />
          <text class="tick-label" x="${left - 9}" y="${zeroY + 4}" text-anchor="end">0 W</text>
          ${this._visibleSeries.has("surplus") && actualPositivePath ? `<path class="line positive" data-series-path="surplus" d="${actualPositivePath}" />` : ""}
          ${this._visibleSeries.has("deficit") && actualNegativePath ? `<path class="line negative" data-series-path="deficit" d="${actualNegativePath}" />` : ""}
          ${this._visibleSeries.has("surplus") && forecastPositivePath ? `<path class="line forecast-line positive" data-series-path="surplus" d="${forecastPositivePath}" />` : ""}
          ${this._visibleSeries.has("deficit") && forecastNegativePath ? `<path class="line forecast-line negative" data-series-path="deficit" d="${forecastNegativePath}" />` : ""}
          ${this._visibleSeries.has("actual_pv") && actualPvPath ? `<path class="line actual-pv" data-series-path="actual_pv" d="${actualPvPath}" />` : ""}
          ${this._visibleSeries.has("actual_consumption") && actualConsumptionPath ? `<path class="line actual-consumption" data-series-path="actual_consumption" d="${actualConsumptionPath}" />` : ""}
          ${this._visibleSeries.has("forecast_pv") && forecastPvPath ? `<path class="line forecast-line forecast-pv" data-series-path="forecast_pv" d="${forecastPvPath}" />` : ""}
          ${this._visibleSeries.has("forecast_consumption") && forecastConsumptionPath ? `<path class="line forecast-line forecast-consumption" data-series-path="forecast_consumption" d="${forecastConsumptionPath}" />` : ""}
          ${nowLine}
          <line class="hover-line" x1="0" x2="0" y1="${chartTop}" y2="${chartBottom}" visibility="hidden" />
          <rect class="hit-area" x="${left}" y="${chartTop}" width="${plotWidth}" height="${chartHeight}" />
          ${
            noData
              ? `<text class="axis-label" x="${left + plotWidth / 2}" y="${chartTop + chartHeight / 2}" text-anchor="middle">${escapeHtml(labels.noData)}</text>`
              : missingForecast
                ? `<text class="tick-label" x="${left + plotWidth / 2}" y="${chartTop + 20}" text-anchor="middle">${escapeHtml(labels.noForecast)}</text>`
                : ""
          }
        </svg>
      </div>
      <div class="legend">
        ${legendButton("actual_pv", "pv-actual", "", `${labels.actual} ${labels.pv}`)}
        ${legendButton("forecast_pv", "pv-forecast", "dashed", `${labels.forecast} ${labels.pv}`)}
        ${legendButton("actual_consumption", "consumption-actual", "", `${labels.actual} ${labels.consumption}`)}
        ${legendButton("forecast_consumption", "consumption-forecast", "dashed", `${labels.forecast} ${labels.consumption}`)}
        ${legendButton("surplus", "surplus", "", labels.surplus)}
        ${legendButton("deficit", "deficit", "", labels.deficit)}
      </div>`;
  }

  _forecastProvenance(data, labels, timezone, locale) {
    const issued = [
      ...new Set((data?.predictions ?? []).map((point) => point.issued_at_utc).filter(Boolean)),
    ].sort();
    if (issued.length === 0) return "";
    if (issued.length === 1) {
      return `${labels.forecastIssued}: ${formatDateTime(issued[0], timezone, locale)}`;
    }
    return `${issued.length} ${labels.forecastVersions}`;
  }

  _render() {
    if (!this.shadowRoot) return;
    const labels = stringsFor(this._hass);
    const locale = localeFor(this._hass);
    const timezone = timezoneFor(this._hass);
    const today = dateInZone(new Date(), timezone);
    const date = this._date ?? today;
    const { firstDate, lastDate } = this._navigationBounds();
    const previousDisabled = firstDate ? date <= firstDate : false;
    const nextDisabled = lastDate ? date >= lastDate : false;
    const title = this._config?.title?.trim() || labels.title;
    const errorCode = this._error?.code ?? this._error?.message;
    const errorMessage =
      errorCode === "no_entries"
        ? labels.noEntries
        : errorCode === "multiple_entries"
          ? labels.multipleEntries
          : labels.error;
    let content = "";
    if (this._loading && !this._data) {
      content = `<div class="message"><span class="spinner"></span>${escapeHtml(labels.loading)}</div>`;
    } else if (this._error) {
      content = `<div class="message error">${escapeHtml(errorMessage)}</div>`;
    } else if (this._data) {
      content = this._renderGraph(this._data, labels, timezone, locale);
    } else {
      content = `<div class="message">${escapeHtml(labels.loading)}</div>`;
    }
    const archiveFirst = this._data?.archive?.first_available_utc;
    const archiveLast = this._data?.archive?.last_available_utc;
    const provenance = this._forecastProvenance(this._data, labels, timezone, locale);

    this.shadowRoot.innerHTML = `
      <style>${CARD_STYLES}</style>
      <ha-card>
        <div class="header">
          <div>
            <div class="title">${escapeHtml(title)}</div>
            <div class="date-label">${escapeHtml(formatCalendarDate(date, locale))} · ${escapeHtml(timezone)}</div>
          </div>
        </div>
        <div class="controls">
          <button class="icon previous" type="button" aria-label="${escapeHtml(labels.previousDay)}" ${previousDisabled ? "disabled" : ""}>‹</button>
          <input class="date" type="date" value="${escapeHtml(date)}" ${firstDate ? `min="${escapeHtml(firstDate)}"` : ""} ${lastDate ? `max="${escapeHtml(lastDate)}"` : ""} aria-label="${escapeHtml(labels.today)}" />
          <button class="icon next" type="button" aria-label="${escapeHtml(labels.nextDay)}" ${nextDisabled ? "disabled" : ""}>›</button>
          <button class="today" type="button">${escapeHtml(labels.today)}</button>
          <select class="mode" aria-label="${escapeHtml(labels.mode)}">
            ${FORECAST_MODES.map((mode) => `<option value="${mode}" ${this._mode === mode ? "selected" : ""}>${escapeHtml(labels[mode])}</option>`).join("")}
          </select>
          <button class="refresh" type="button" aria-label="${escapeHtml(labels.refresh)}">↻</button>
        </div>
        <div class="mode-help">${escapeHtml(labels[`${this._mode}Help`])}</div>
        ${content}
        <div class="footer">
          <span>${provenance ? escapeHtml(provenance) : ""}</span>
          <span>${
            archiveFirst && archiveLast
              ? `${escapeHtml(labels.archive)}: ${escapeHtml(formatDateTime(archiveFirst, timezone, locale))} – ${escapeHtml(formatDateTime(archiveLast, timezone, locale))}`
              : ""
          }</span>
        </div>
      </ha-card>`;
    this._bindControls();
    this._bindLegend();
    this._bindChart();
  }

  _bindControls() {
    const root = this.shadowRoot;
    root.querySelector(".previous")?.addEventListener("click", () => this._changeDate(-1));
    root.querySelector(".next")?.addEventListener("click", () => this._changeDate(1));
    root.querySelector(".today")?.addEventListener("click", () => {
      this._date = dateInZone(new Date(), timezoneFor(this._hass));
      this._load();
    });
    root.querySelector(".refresh")?.addEventListener("click", () => this._load());
    root.querySelector(".date")?.addEventListener("change", (event) => {
      if (!event.target.value) return;
      this._date = event.target.value;
      this._load();
    });
    root.querySelector(".mode")?.addEventListener("change", (event) => {
      if (!FORECAST_MODES.includes(event.target.value)) return;
      this._mode = event.target.value;
      this._load();
    });
  }

  _bindLegend() {
    for (const button of this.shadowRoot.querySelectorAll(".legend-item[data-series]")) {
      button.addEventListener("click", () => {
        const key = button.dataset.series;
        if (!SERIES_KEYS.includes(key)) return;
        if (this._visibleSeries.has(key)) this._visibleSeries.delete(key);
        else this._visibleSeries.add(key);
        this._render();
      });
    }
  }

  _bindChart() {
    if (!this._data) return;
    const svg = this.shadowRoot.querySelector("svg");
    const hitArea = this.shadowRoot.querySelector(".hit-area");
    const hoverLine = this.shadowRoot.querySelector(".hover-line");
    const tooltip = this.shadowRoot.querySelector(".tooltip");
    const wrap = this.shadowRoot.querySelector(".chart-wrap");
    if (!svg || !hitArea || !hoverLine || !tooltip || !wrap) return;
    const labels = stringsFor(this._hass);
    const locale = localeFor(this._hass);
    const timezone = timezoneFor(this._hass);
    const startTime = Date.parse(this._data.day_start_utc);
    const endTime = Date.parse(this._data.day_end_utc);
    const measurements = this._data.measurements ?? [];
    const predictions = this._data.predictions ?? [];
    const left = 68;
    const plotWidth = 914;

    hitArea.addEventListener("pointermove", (event) => {
      const svgRect = svg.getBoundingClientRect();
      const chartX = ((event.clientX - svgRect.left) / svgRect.width) * 1000;
      const boundedX = Math.max(left, Math.min(left + plotWidth, chartX));
      const targetTime = startTime + ((boundedX - left) / plotWidth) * (endTime - startTime);
      const actual = nearestPoint(measurements, targetTime);
      const forecast = nearestPoint(predictions, targetTime);
      if (!actual && !forecast) return;
      const reference = actual ?? forecast;
      const rows = [];
      if (actual) {
        if (this._visibleSeries.has("actual_pv")) {
          rows.push(`<div class="tooltip-row"><span>${escapeHtml(labels.actual)} ${escapeHtml(labels.pv)}</span><strong>${escapeHtml(formatPower(actual.pv_generation_w, locale))}</strong></div>`);
        }
        if (this._visibleSeries.has("actual_consumption")) {
          rows.push(`<div class="tooltip-row"><span>${escapeHtml(labels.actual)} ${escapeHtml(labels.consumption)}</span><strong>${escapeHtml(formatPower(actual.total_consumption_w, locale))}</strong></div>`);
        }
        const actualBalanceKey = Number(actual.surplus_w) >= 0 ? "surplus" : "deficit";
        if (this._visibleSeries.has(actualBalanceKey)) {
          rows.push(`<div class="tooltip-row"><span>${escapeHtml(labels.actual)} ${escapeHtml(labels[actualBalanceKey])}</span><strong>${escapeHtml(formatPower(actual.surplus_w, locale, true))}</strong></div>`);
        }
      }
      if (forecast) {
        if (this._visibleSeries.has("forecast_pv")) {
          rows.push(`<div class="tooltip-row"><span>${escapeHtml(labels.forecast)} ${escapeHtml(labels.pv)}</span><strong>${escapeHtml(formatPower(forecast.pv_generation_w, locale))}</strong></div>`);
        }
        if (this._visibleSeries.has("forecast_consumption")) {
          rows.push(`<div class="tooltip-row"><span>${escapeHtml(labels.forecast)} ${escapeHtml(labels.consumption)}</span><strong>${escapeHtml(formatPower(forecast.total_consumption_w, locale))}</strong></div>`);
        }
        const forecastBalanceKey = Number(forecast.surplus_w) >= 0 ? "surplus" : "deficit";
        if (this._visibleSeries.has(forecastBalanceKey)) {
          rows.push(`<div class="tooltip-row"><span>${escapeHtml(labels.forecast)} ${escapeHtml(labels[forecastBalanceKey])}</span><strong>${escapeHtml(formatPower(forecast.surplus_w, locale, true))}</strong></div>`);
        }
      }
      if (rows.length === 0) return;
      tooltip.innerHTML = `<div class="tooltip-title">${escapeHtml(formatDateTime(reference.time_utc, timezone, locale))}</div>${rows.join("")}`;
      tooltip.classList.add("visible");
      hoverLine.setAttribute("x1", boundedX);
      hoverLine.setAttribute("x2", boundedX);
      hoverLine.setAttribute("visibility", "visible");
      const wrapRect = wrap.getBoundingClientRect();
      const tooltipWidth = 230;
      const pointerX = event.clientX - wrapRect.left;
      const leftPosition = Math.max(4, Math.min(wrapRect.width - tooltipWidth - 4, pointerX + 12));
      tooltip.style.left = `${leftPosition}px`;
    });
    hitArea.addEventListener("pointerleave", () => {
      tooltip.classList.remove("visible");
      hoverLine.setAttribute("visibility", "hidden");
    });
  }
}

const EDITOR_STYLES = `
  :host { display: block; }
  .editor { display: grid; gap: 14px; padding: 8px 0; }
  label { color: var(--primary-text-color); display: grid; font-size: 0.9rem; gap: 6px; }
  input, select {
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, #d8d8d8);
    border-radius: 8px;
    box-sizing: border-box;
    color: var(--primary-text-color);
    font: inherit;
    min-height: 42px;
    padding: 0 10px;
    width: 100%;
  }
  .help { color: var(--secondary-text-color); font-size: 0.78rem; }
  .error { color: var(--error-color, #db4437); }
`;

class SmaSunnyPortalEnergyCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._entries = [];
    this._entriesRequested = false;
    this._error = false;
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(value) {
    this._hass = value;
    this._render();
    this._loadEntries();
  }

  async _loadEntries() {
    if (!this._hass || this._entriesRequested) return;
    this._entriesRequested = true;
    try {
      const result = await this._hass.callWS({ type: ENTRIES_COMMAND });
      this._entries = Array.isArray(result?.entries) ? result.entries : [];
    } catch (_error) {
      this._error = true;
    }
    this._render();
  }

  _update(key, value, defaultValue = "") {
    const config = { ...this._config };
    if (value === defaultValue || value === "") delete config[key];
    else config[key] = value;
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        bubbles: true,
        composed: true,
        detail: { config },
      }),
    );
  }

  _render() {
    if (!this.shadowRoot) return;
    const labels = stringsFor(this._hass);
    const selectedEntry = this._config.config_entry_id ?? "";
    const selectedMode = this._config.default_mode ?? "latest";
    this.shadowRoot.innerHTML = `
      <style>${EDITOR_STYLES}</style>
      <div class="editor">
        <label>
          ${escapeHtml(labels.entry)}
          <select class="entry">
            <option value="">${escapeHtml(labels.automatic)}</option>
            ${this._entries
              .map(
                (entry) =>
                  `<option value="${escapeHtml(entry.entry_id)}" ${selectedEntry === entry.entry_id ? "selected" : ""}>${escapeHtml(entry.title)} (${escapeHtml(entry.loaded ? labels.loaded : labels.unavailable)})</option>`,
              )
              .join("")}
          </select>
        </label>
        <label>
          ${escapeHtml(labels.customTitle)}
          <input class="title" type="text" value="${escapeHtml(this._config.title ?? "")}" placeholder="${escapeHtml(labels.title)}" />
        </label>
        <label>
          ${escapeHtml(labels.defaultMode)}
          <select class="mode">
            ${FORECAST_MODES.map((mode) => `<option value="${mode}" ${selectedMode === mode ? "selected" : ""}>${escapeHtml(labels[mode])}</option>`).join("")}
          </select>
        </label>
        <div class="help ${this._error ? "error" : ""}">${escapeHtml(this._error ? labels.error : labels.editorHelp)}</div>
      </div>`;
    this.shadowRoot.querySelector(".entry")?.addEventListener("change", (event) =>
      this._update("config_entry_id", event.target.value),
    );
    this.shadowRoot.querySelector(".title")?.addEventListener("change", (event) =>
      this._update("title", event.target.value.trim()),
    );
    this.shadowRoot.querySelector(".mode")?.addEventListener("change", (event) =>
      this._update("default_mode", event.target.value, "latest"),
    );
  }
}

globalThis.customCards = globalThis.customCards ?? [];
if (!globalThis.customCards.some((card) => card.type === CARD_TAG)) {
  globalThis.customCards.push({
    type: CARD_TAG,
    name: "SMA Energy Live",
    description: "Actual and archived SMA PV, consumption, and surplus forecast curves",
    preview: false,
  });
}

const registerCustomElements = () => {
  const registry = globalThis.customElements;
  if (!registry?.get(HA_ROOT_TAG)) return false;
  if (!registry.get(EDITOR_TAG)) {
    registry.define(EDITOR_TAG, SmaSunnyPortalEnergyCardEditor);
  }
  if (!registry.get(CARD_TAG)) {
    registry.define(CARD_TAG, SmaSunnyPortalEnergyCard);
  }
  return true;
};

const registerCustomElementsWhenReady = (attempt = 0) => {
  if (registerCustomElements()) return;
  if (attempt >= 1200) {
    console.error("SMA Energy Live could not find the Home Assistant custom-element registry");
    return;
  }
  globalThis.setTimeout(() => registerCustomElementsWhenReady(attempt + 1), 25);
};

registerCustomElementsWhenReady();
