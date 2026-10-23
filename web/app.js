"use strict";

/* ==========================================================================
   FFT-Glättung – Frontend
   Reines Vanilla-JavaScript, kein Build-Schritt, keine externen Bibliotheken.

   Aufbau:
   1. Formatierung und kleine Helfer
   2. Canvas-Diagramm (zwei Panels, Zoom, Pan, Hover)
   3. Anwendungszustand, API und Steuerung
   4. Initialisierung und Events
   ========================================================================== */

/* --------------------------------------------------------------------------
   1. Formatierung und Helfer
   -------------------------------------------------------------------------- */

const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("de-DE", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const nf2 = new Intl.NumberFormat("de-DE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const nfMax1 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
const nfMax2 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });
const nfSig = new Intl.NumberFormat("de-DE", {
  maximumSignificantDigits: 3,
});

const dateTimeFmt = new Intl.DateTimeFormat("de-DE", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

const dateFmt = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});

function $(id) {
  return document.getElementById(id);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function clampInt(value, min, max, fallback) {
  const number = parseInt(value, 10);
  return Number.isFinite(number) ? clamp(number, min, max) : fallback;
}

function clampFloat(value, min, max, fallback) {
  const number = parseFloat(value);
  return Number.isFinite(number) ? clamp(number, min, max) : fallback;
}

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function toFinite(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : NaN;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const number = Number(value);
    return Number.isFinite(number) ? number : NaN;
  }
  return NaN;
}

function displayUnit(unit) {
  if (typeof unit !== "string") return "";
  const trimmed = unit.trim();
  if (!trimmed || trimmed.toLowerCase() === "keine") return "";
  return trimmed;
}

function formatStatNumber(value) {
  if (!Number.isFinite(value)) return "–";
  const absolute = Math.abs(value);
  if (absolute >= 10000) return nf0.format(value);
  if (absolute >= 100) return nfMax1.format(value);
  if (absolute >= 1) return nfMax2.format(value);
  return nfSig.format(value);
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return "–";
  return `${nf1.format(value)} %`;
}

function formatDuration(hours) {
  if (!Number.isFinite(hours) || hours < 0) return "–";
  if (hours === 0) return "0 min";
  if (hours < 1 / 60) return `${nfMax1.format(hours * 3600)} s`;
  if (hours < 1) return `${nf0.format(hours * 60)} min`;
  if (hours < 48) {
    return `${hours < 10 ? nfMax2.format(hours) : nfMax1.format(hours)} h`;
  }
  return `${nfMax1.format(hours / 24)} d`;
}

function formatHz(value) {
  if (!Number.isFinite(value) || value <= 0) return "–";
  if (value < 1e-3) return `${value.toExponential(2)} Hz`;
  return `${nfSig.format(value)} Hz`;
}

function formatPeriodFromHz(hz) {
  if (!Number.isFinite(hz) || hz <= 0) return "–";
  return formatDuration(1 / (hz * 3600));
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${nf0.format(bytes)} B`;
  if (bytes < 1024 * 1024) return `${nfMax1.format(bytes / 1024)} KB`;
  return `${nfMax1.format(bytes / (1024 * 1024))} MB`;
}

function parseDate(value) {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time) : null;
}

function formatDateTime(value) {
  const date = value instanceof Date ? value : parseDate(value);
  return date ? `${dateTimeFmt.format(date)} UTC` : "–";
}

function formatDateRange(start, end) {
  if (!start && !end) return "–";
  if (start && end) return `${formatDateTime(start)} – ${formatDateTime(end)}`;
  return formatDateTime(start || end);
}

function formatShortDateRange(start, end) {
  const first = parseDate(start);
  const last = parseDate(end);
  if (first && last) return `${dateFmt.format(first)} – ${dateFmt.format(last)}`;
  if (first) return dateFmt.format(first);
  if (last) return dateFmt.format(last);
  return "–";
}

function formatShortDate(value) {
  const date = parseDate(value);
  return date ? dateFmt.format(date) : "";
}

function formatTooltipValue(value, unit) {
  if (!Number.isFinite(value)) return "–";
  const suffix = displayUnit(unit);
  return `${nfSig.format(value)}${suffix ? ` ${suffix}` : ""}`;
}

function formatXAxisTick(value, axis) {
  const converted = axis.toUnit(value);
  if (Math.abs(converted) < Math.pow(10, -axis.digits) / 2) {
    return (0).toFixed(axis.digits);
  }
  return converted.toFixed(axis.digits);
}

function formatCompactNumber(value) {
  if (!Number.isFinite(value)) return "";
  if (value === 0) return "0";
  const absolute = Math.abs(value);
  if (absolute >= 100000 || absolute < 0.001) {
    return value.toExponential(1).replace("e+", "e");
  }
  let digits = 0;
  if (absolute < 1) digits = 3;
  else if (absolute < 10) digits = 2;
  else if (absolute < 100) digits = 1;
  let text = value.toFixed(digits);
  if (text.includes(".")) {
    text = text.replace(/0+$/, "").replace(/\.$/, "");
  }
  return text === "-0" ? "0" : text;
}

function niceStep(range, target) {
  if (!(range > 0)) return 1;
  const rough = range / Math.max(1, target);
  const power = Math.pow(10, Math.floor(Math.log10(rough)));
  const fraction = rough / power;
  let nice = 10;
  if (fraction <= 1) nice = 1;
  else if (fraction <= 2) nice = 2;
  else if (fraction <= 5) nice = 5;
  return nice * power;
}

function niceTicks(low, high, target) {
  if (!Number.isFinite(low) || !Number.isFinite(high) || high <= low) {
    return [low];
  }
  const step = niceStep(high - low, target);
  const start = Math.ceil((low - step * 1e-9) / step) * step;
  const ticks = [];
  for (let value = start; value <= high + step * 1e-9; value += step) {
    ticks.push(Math.abs(value) < step * 1e-9 ? 0 : value);
    if (ticks.length > 30) break;
  }
  return ticks;
}

function lowerBound(values, target) {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (values[middle] < target) low = middle + 1;
    else high = middle;
  }
  return low;
}

function nearestIndex(values, target) {
  if (!values.length) return -1;
  let index = lowerBound(values, target);
  if (index >= values.length) index = values.length - 1;
  if (
    index > 0 &&
    Math.abs(values[index - 1] - target) < Math.abs(values[index] - target)
  ) {
    index -= 1;
  }
  return index;
}

function getXAxis(meta, span) {
  let rawUnit =
    meta && typeof meta.x_unit === "string" ? meta.x_unit.trim() : "";
  if (!rawUnit) {
    if (meta && meta.kind === "ndbc") rawUnit = "h";
    else if (meta && meta.kind === "demo") rawUnit = "s";
    else rawUnit = "x";
  }

  if (rawUnit === "s") {
    return {
      label: "Zeit [s]",
      unit: "s",
      digits: span <= 120 ? 1 : 0,
      toUnit: (value) => value,
    };
  }
  if (rawUnit === "min") {
    return {
      label: "Zeit [min]",
      unit: "min",
      digits: span <= 120 ? 1 : 0,
      toUnit: (value) => value,
    };
  }
  if (rawUnit === "x") {
    return {
      label: "Zeit [x]",
      unit: "x",
      digits: span <= 120 ? 1 : 0,
      toUnit: (value) => value,
    };
  }
  if (span <= 48) {
    return {
      label: "Zeit [h]",
      unit: "h",
      digits: 1,
      toUnit: (value) => value,
    };
  }
  const days = span / 24;
  return {
    label: "Zeit [d]",
    unit: "d",
    digits: days <= 60 ? 1 : 0,
    toUnit: (value) => value / 24,
  };
}

function formatTooltipX(value, axis) {
  if (axis.unit === "d") return `${nfMax2.format(value / 24)} d`;
  if (axis.unit === "x") return nfMax2.format(value);
  return `${nfMax2.format(value)} ${axis.unit}`;
}

function formatTooltipTime(value, meta) {
  if (!meta || !meta.start) return "";
  const unit = meta.x_unit;
  if (unit !== "h" && unit !== "min" && unit !== "s") return "";
  const start = Date.parse(meta.start);
  if (!Number.isFinite(start)) return "";
  let milliseconds = value * 1000;
  if (unit === "h") milliseconds = value * 3600 * 1000;
  else if (unit === "min") milliseconds = value * 60 * 1000;
  const date = new Date(start + milliseconds);
  return Number.isFinite(date.getTime()) ? formatDateTime(date) : "";
}

/* --------------------------------------------------------------------------
   2. Canvas-Diagramm
   -------------------------------------------------------------------------- */

const CHART_COLORS = {
  background: "#ffffff",
  original: "#aab0bb",
  smoothed: "#1769aa",
  residual: "#d2691e",
  grid: "#e4e7ec",
  text: "#555555",
  muted: "#7b8794",
  border: "#cfd5df",
  zero: "#98a2b3",
  axisText: "#444444",
  emptyTitle: "#6b7280",
  emptyText: "#9aa3af",
};

// Zuordnung der Canvas-Farben zu den CSS-Variablen. So folgt das Diagramm
// automatisch dem hellen oder dunklen Design.
const CHART_COLOR_VARS = {
  background: "--chart-bg",
  original: "--original",
  smoothed: "--smoothed",
  residual: "--residual",
  grid: "--grid",
  text: "--chart-text",
  muted: "--muted",
  border: "--border",
  zero: "--chart-zero",
  axisText: "--chart-axis",
  emptyTitle: "--chart-empty-title",
  emptyText: "--chart-empty-text",
};

function refreshChartColors() {
  const styles = getComputedStyle(document.documentElement);
  for (const [key, variable] of Object.entries(CHART_COLOR_VARS)) {
    const value = styles.getPropertyValue(variable).trim();
    if (value) CHART_COLORS[key] = value;
  }
}

const CHART_FONT =
  '11px system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
const CHART_FONT_SMALL =
  '10px system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

function createChart(canvas, tooltip) {
  const context = canvas.getContext("2d");
  const state = {
    data: null,
    meta: {},
    full: { x0: 0, x1: 1 },
    view: { x0: 0, x1: 1 },
    visible: { original: true, smoothed: true, residual: true },
    width: 0,
    height: 0,
    dpr: 1,
    layout: null,
    scaleCache: null,
    pointCache: null,
    frame: 0,
    hover: null,
    drag: null,
  };

  function requestDraw() {
    if (state.frame) return;
    state.frame = requestAnimationFrame(() => {
      state.frame = 0;
      draw();
    });
  }

  function invalidate() {
    state.scaleCache = null;
    state.pointCache = null;
  }

  function hideTooltip() {
    if (tooltip && tooltip.root) tooltip.root.hidden = true;
  }

  function resize() {
    const parent = canvas.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width || canvas.clientWidth || 0));
    const height = Math.max(
      1,
      Math.round(rect.height || canvas.clientHeight || 0)
    );
    if (width < 40 || height < 40) return;

    const dpr = clamp(window.devicePixelRatio || 1, 1, 3);
    state.width = width;
    state.height = height;
    state.dpr = dpr;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    state.hover = null;
    hideTooltip();
    invalidate();
    requestDraw();
  }

  function computeLayout() {
    const width = state.width;
    const height = state.height;
    const compact = width < 560;
    const left = compact ? 48 : 62;
    const right = compact ? 10 : 18;
    const top = compact ? 24 : 28;
    const bottom = compact ? 40 : 46;
    const gap = compact ? 26 : 32;
    const plotWidth = Math.max(10, width - left - right);
    const plotHeight = Math.max(20, height - top - bottom - gap);
    const topHeight = plotHeight * 0.63;
    const topRect = { x: left, y: top, w: plotWidth, h: topHeight };
    const bottomRect = {
      x: left,
      y: top + topHeight + gap,
      w: plotWidth,
      h: plotHeight - topHeight,
    };
    return {
      width,
      height,
      compact,
      left,
      right,
      top,
      bottom,
      gap,
      plotWidth,
      topRect,
      bottomRect,
    };
  }

  function xToPixel(value) {
    const layout = state.layout;
    if (!layout) return 0;
    const span = state.view.x1 - state.view.x0;
    if (!(span > 0)) return layout.left;
    return (
      layout.left +
      ((value - state.view.x0) / span) * layout.plotWidth
    );
  }

  function yToPixel(value, range, rect) {
    const span = range[1] - range[0];
    if (!(span > 0)) return rect.y + rect.h / 2;
    return rect.y + rect.h - ((value - range[0]) / span) * rect.h;
  }

  function visibleIndexRange() {
    const data = state.data;
    if (!data || data.n < 2) return { i0: 0, i1: 0 };
    let i0 = lowerBound(data.x, state.view.x0);
    if (i0 > 0) i0 -= 1;
    let i1 = lowerBound(data.x, state.view.x1);
    if (i1 < data.n) i1 += 1;
    i1 = Math.min(data.n - 1, i1);
    if (i1 <= i0) i1 = Math.min(data.n - 1, i0 + 1);
    return { i0, i1 };
  }

  function ensureScales() {
    if (state.scaleCache) return state.scaleCache;
    const data = state.data;
    const range = visibleIndexRange();
    let minimum = Infinity;
    let maximum = -Infinity;

    function scan(values) {
      for (let index = range.i0; index <= range.i1; index += 1) {
        const value = values[index];
        if (Number.isFinite(value)) {
          if (value < minimum) minimum = value;
          if (value > maximum) maximum = value;
        }
      }
    }

    if (state.visible.original) scan(data.original);
    if (state.visible.smoothed) scan(data.smoothed);
    if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) {
      minimum = 0;
      maximum = 1;
    }
    const signalSpan = maximum - minimum;
    const signalPadding =
      signalSpan > 0
        ? signalSpan * 0.08
        : Math.max(Math.abs(minimum) * 0.1, 1);
    const signal = [minimum - signalPadding, maximum + signalPadding];

    let residualMinimum = Infinity;
    let residualMaximum = -Infinity;
    if (state.visible.residual) {
      for (let index = range.i0; index <= range.i1; index += 1) {
        const value = data.residual[index];
        if (Number.isFinite(value)) {
          if (value < residualMinimum) residualMinimum = value;
          if (value > residualMaximum) residualMaximum = value;
        }
      }
    }
    residualMinimum = Math.min(residualMinimum, 0);
    residualMaximum = Math.max(residualMaximum, 0);
    if (
      !Number.isFinite(residualMinimum) ||
      !Number.isFinite(residualMaximum)
    ) {
      residualMinimum = -1;
      residualMaximum = 1;
    }
    const residualMagnitude = Math.max(
      Math.abs(residualMinimum),
      Math.abs(residualMaximum)
    );
    const residualPadding = residualMagnitude * 0.15 || 1;
    const residual = [
      -residualMagnitude - residualPadding,
      residualMagnitude + residualPadding,
    ];

    state.scaleCache = {
      i0: range.i0,
      i1: range.i1,
      signal,
      residual,
    };
    return state.scaleCache;
  }

  function buildPoints(values, i0, i1, rect, yRange) {
    const data = state.data;
    const view = state.view;
    const span = view.x1 - view.x0;
    if (!(span > 0) || i1 <= i0) return [];
    const width = Math.max(1, rect.w);
    const xScale = width / span;
    const yScale = rect.h / (yRange[1] - yRange[0] || 1);
    const points = [];
    const count = i1 - i0 + 1;

    if (count <= width * 2) {
      for (let index = i0; index <= i1; index += 1) {
        const value = values[index];
        if (!Number.isFinite(value)) continue;
        points.push(
          rect.x + (data.x[index] - view.x0) * xScale,
          rect.y + rect.h - (value - yRange[0]) * yScale
        );
      }
      return points;
    }

    let bucket = -1;
    let first = 0;
    let last = 0;
    let minimum = Infinity;
    let maximum = -Infinity;
    let minimumIndex = -1;
    let maximumIndex = -1;
    let bucketCount = 0;
    let lastPushedY = NaN;

    function push(pointX, pointY) {
      if (pointY === lastPushedY) return;
      points.push(pointX, pointY);
      lastPushedY = pointY;
    }

    function flush() {
      if (!bucketCount) return;
      const center = rect.x + bucket + 0.5;
      const sequence =
        minimumIndex <= maximumIndex
          ? [first, minimum, maximum, last]
          : [first, maximum, minimum, last];
      for (const pointY of sequence) push(center, pointY);
    }

    for (let index = i0; index <= i1; index += 1) {
      const value = values[index];
      if (!Number.isFinite(value)) continue;
      const relativeX = (data.x[index] - view.x0) * xScale;
      const nextBucket = Math.floor(relativeX);
      if (nextBucket !== bucket) {
        flush();
        bucket = nextBucket;
        bucketCount = 0;
        minimum = Infinity;
        maximum = -Infinity;
      }
      const pointY = rect.y + rect.h - (value - yRange[0]) * yScale;
      if (bucketCount === 0) first = pointY;
      last = pointY;
      if (pointY < minimum) {
        minimum = pointY;
        minimumIndex = index;
      }
      if (pointY > maximum) {
        maximum = pointY;
        maximumIndex = index;
      }
      bucketCount += 1;
    }
    flush();
    return points;
  }

  function ensurePoints() {
    if (state.pointCache) return state.pointCache;
    const scales = ensureScales();
    const layout = state.layout;
    const data = state.data;
    const cache = {};
    if (layout && data) {
      if (state.visible.original) {
        cache.original = buildPoints(
          data.original,
          scales.i0,
          scales.i1,
          layout.topRect,
          scales.signal
        );
      }
      if (state.visible.smoothed) {
        cache.smoothed = buildPoints(
          data.smoothed,
          scales.i0,
          scales.i1,
          layout.topRect,
          scales.signal
        );
      }
      if (state.visible.residual) {
        cache.residual = buildPoints(
          data.residual,
          scales.i0,
          scales.i1,
          layout.bottomRect,
          scales.residual
        );
      }
    }
    state.pointCache = cache;
    return cache;
  }

  function drawPath(points, color, lineWidth, alpha) {
    if (!points || points.length < 2) return;
    context.beginPath();
    context.moveTo(points[0], points[1]);
    for (let index = 2; index < points.length; index += 2) {
      context.lineTo(points[index], points[index + 1]);
    }
    context.strokeStyle = color;
    context.lineWidth = lineWidth;
    context.globalAlpha = alpha;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.stroke();
    context.globalAlpha = 1;
  }

  function drawDot(x, y, color) {
    context.beginPath();
    context.arc(x, y, 3.2, 0, Math.PI * 2);
    context.fillStyle = color;
    context.fill();
    context.lineWidth = 1.5;
    context.strokeStyle = CHART_COLORS.background;
    context.stroke();
  }

  function drawEmpty() {
    const width = state.width;
    const height = state.height;
    context.fillStyle = CHART_COLORS.background;
    context.fillRect(0, 0, width, height);
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillStyle = CHART_COLORS.emptyTitle;
    context.font =
      '600 15px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    context.fillText("Keine Daten", width / 2, height / 2 - 11);
    context.fillStyle = CHART_COLORS.emptyText;
    context.font =
      '12px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    context.fillText(
      "Bitte Station und Messgröße wählen oder eine CSV laden.",
      width / 2,
      height / 2 + 14
    );
  }

  function drawHorizontalGrid(rect, ticks, range) {
    context.beginPath();
    for (const tick of ticks) {
      const y = yToPixel(tick, range, rect);
      context.moveTo(rect.x, y);
      context.lineTo(rect.x + rect.w, y);
    }
    context.strokeStyle = CHART_COLORS.grid;
    context.lineWidth = 1;
    context.stroke();

    context.font = CHART_FONT_SMALL;
    context.fillStyle = CHART_COLORS.text;
    context.textAlign = "right";
    context.textBaseline = "middle";
    for (const tick of ticks) {
      const y = yToPixel(tick, range, rect);
      context.fillText(formatCompactNumber(tick), rect.x - 8, y);
    }
  }

  function draw() {
    const width = state.width;
    const height = state.height;
    if (width < 40 || height < 40) return;

    context.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
    context.fillStyle = CHART_COLORS.background;
    context.fillRect(0, 0, width, height);

    if (!state.data) {
      drawEmpty();
      return;
    }

    const layout = computeLayout();
    state.layout = layout;
    const scales = ensureScales();
    const axis = getXAxis(state.meta, state.view.x1 - state.view.x0);
    const xTickTarget = Math.max(
      3,
      Math.min(7, Math.floor(layout.plotWidth / 105))
    );
    const xTicks = niceTicks(state.view.x0, state.view.x1, xTickTarget);
    const yTicksTop = niceTicks(
      scales.signal[0],
      scales.signal[1],
      layout.compact ? 4 : 5
    );
    const yTicksBottom = niceTicks(
      scales.residual[0],
      scales.residual[1],
      layout.compact ? 3 : 4
    );

    // Vertikale Gitterlinien über beide Panels
    context.beginPath();
    for (const tick of xTicks) {
      const x = xToPixel(tick);
      context.moveTo(x, layout.topRect.y);
      context.lineTo(x, layout.bottomRect.y + layout.bottomRect.h);
    }
    context.strokeStyle = CHART_COLORS.grid;
    context.lineWidth = 1;
    context.stroke();

    drawHorizontalGrid(layout.topRect, yTicksTop, scales.signal);
    drawHorizontalGrid(layout.bottomRect, yTicksBottom, scales.residual);

    // Rahmen und Panelüberschriften
    context.strokeStyle = CHART_COLORS.border;
    context.lineWidth = 1;
    context.strokeRect(
      layout.topRect.x,
      layout.topRect.y,
      layout.topRect.w,
      layout.topRect.h
    );
    context.strokeRect(
      layout.bottomRect.x,
      layout.bottomRect.y,
      layout.bottomRect.w,
      layout.bottomRect.h
    );

    const unit = displayUnit(state.meta.unit);
    const unitSuffix = unit ? ` [${unit}]` : "";
    context.font =
      '600 11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    context.fillStyle = "#444444";
    context.textAlign = "left";
    context.textBaseline = "alphabetic";
    context.fillText(
      `Signal${unitSuffix}`,
      layout.topRect.x,
      layout.topRect.y - 8
    );
    context.fillText(
      `Rest (Original − geglättet)${unitSuffix}`,
      layout.bottomRect.x,
      layout.bottomRect.y - 8
    );

    // Nullinie im Rest-Panel
    const zeroY = yToPixel(0, scales.residual, layout.bottomRect);
    if (
      zeroY >= layout.bottomRect.y &&
      zeroY <= layout.bottomRect.y + layout.bottomRect.h
    ) {
      context.save();
      context.setLineDash([4, 4]);
      context.strokeStyle = CHART_COLORS.zero;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(layout.bottomRect.x, zeroY);
      context.lineTo(layout.bottomRect.x + layout.bottomRect.w, zeroY);
      context.stroke();
      context.restore();
    }

    const points = ensurePoints();

    // Signal-Panel
    context.save();
    context.beginPath();
    context.rect(
      layout.topRect.x,
      layout.topRect.y,
      layout.topRect.w,
      layout.topRect.h
    );
    context.clip();
    if (points.original) {
      drawPath(points.original, CHART_COLORS.original, 1.2, 0.8);
    }
    if (points.smoothed) {
      drawPath(points.smoothed, CHART_COLORS.smoothed, 1.8, 1);
    }
    context.restore();

    // Rest-Panel
    context.save();
    context.beginPath();
    context.rect(
      layout.bottomRect.x,
      layout.bottomRect.y,
      layout.bottomRect.w,
      layout.bottomRect.h
    );
    context.clip();
    if (points.residual) {
      drawPath(points.residual, CHART_COLORS.residual, 1.2, 1);
    }
    context.restore();

    // X-Achsen-Beschriftung
    context.font = CHART_FONT_SMALL;
    context.fillStyle = CHART_COLORS.text;
    context.textBaseline = "top";
    for (const tick of xTicks) {
      const x = xToPixel(tick);
      if (x < layout.left - 1 || x > layout.left + layout.plotWidth + 1) {
        continue;
      }
      context.textAlign =
        x < layout.left + 22
          ? "left"
          : x > layout.left + layout.plotWidth - 22
            ? "right"
            : "center";
      context.fillText(
        formatXAxisTick(tick, axis),
        x,
        layout.bottomRect.y + layout.bottomRect.h + 6
      );
    }

    context.textAlign = "center";
    context.textBaseline = "alphabetic";
    context.fillStyle = "#444444";
    context.font =
      '11px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    context.fillText(
      axis.label,
      layout.bottomRect.x + layout.bottomRect.w / 2,
      height - 9
    );

    // Fadenkreuz und Punkte beim Hover
    if (
      state.hover &&
      state.hover.index >= scales.i0 &&
      state.hover.index <= scales.i1
    ) {
      const index = state.hover.index;
      const x = xToPixel(state.data.x[index]);
      context.save();
      context.setLineDash([4, 4]);
      context.strokeStyle = CHART_COLORS.muted;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(x, layout.topRect.y);
      context.lineTo(x, layout.bottomRect.y + layout.bottomRect.h);
      context.stroke();
      context.restore();

      if (state.visible.original) {
        drawDot(
          x,
          yToPixel(state.data.original[index], scales.signal, layout.topRect),
          CHART_COLORS.original
        );
      }
      if (state.visible.smoothed) {
        drawDot(
          x,
          yToPixel(state.data.smoothed[index], scales.signal, layout.topRect),
          CHART_COLORS.smoothed
        );
      }
      if (state.visible.residual) {
        drawDot(
          x,
          yToPixel(state.data.residual[index], scales.residual, layout.bottomRect),
          CHART_COLORS.residual
        );
      }
    }
  }

  function setData(data, meta) {
    state.meta = meta && typeof meta === "object" ? meta : {};
    if (data && data.n >= 2) {
      state.data = data;
      const x0 = data.x[0];
      const x1 = data.x[data.n - 1];
      state.full = { x0, x1: x1 > x0 ? x1 : x0 + 1 };
      state.view = { x0: state.full.x0, x1: state.full.x1 };
    } else {
      state.data = null;
      state.full = { x0: 0, x1: 1 };
      state.view = { x0: 0, x1: 1 };
    }
    state.hover = null;
    hideTooltip();
    invalidate();
    requestDraw();
  }

  function setVisible(key, visible) {
    if (!(key in state.visible)) return;
    state.visible[key] = Boolean(visible);
    invalidate();
    requestDraw();
  }

  function updateTooltip(index, mouseX, mouseY) {
    if (!tooltip || !tooltip.root || !state.data) return;
    const data = state.data;
    const axis = getXAxis(state.meta, state.view.x1 - state.view.x0);
    const xValue = data.x[index];

    tooltip.root.hidden = false;
    if (tooltip.x) {
      tooltip.x.textContent = formatTooltipX(xValue, axis);
    }
    if (tooltip.time) {
      const timeText = formatTooltipTime(xValue, state.meta);
      tooltip.time.hidden = !timeText;
      tooltip.time.textContent = timeText;
    }
    if (tooltip.original) {
      tooltip.original.textContent = formatTooltipValue(
        data.original[index],
        state.meta.unit
      );
    }
    if (tooltip.smoothed) {
      tooltip.smoothed.textContent = formatTooltipValue(
        data.smoothed[index],
        state.meta.unit
      );
    }
    if (tooltip.residual) {
      tooltip.residual.textContent = formatTooltipValue(
        data.residual[index],
        state.meta.unit
      );
    }

    const tooltipWidth = tooltip.root.offsetWidth;
    const tooltipHeight = tooltip.root.offsetHeight;
    let left = mouseX + 16;
    let top = mouseY - tooltipHeight / 2;
    if (left + tooltipWidth > state.width - 8) {
      left = mouseX - tooltipWidth - 16;
    }
    if (left < 8) left = 8;
    if (top + tooltipHeight > state.height - 8) {
      top = state.height - tooltipHeight - 8;
    }
    if (top < 8) top = 8;
    tooltip.root.style.left = `${left}px`;
    tooltip.root.style.top = `${top}px`;
  }

  function clearHover() {
    if (state.hover) {
      state.hover = null;
      requestDraw();
    }
    hideTooltip();
  }

  function updateHover(clientX, clientY) {
    if (!state.data || !state.layout) {
      clearHover();
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const mouseX = clientX - rect.left;
    const mouseY = clientY - rect.top;
    const layout = state.layout;
    if (
      mouseX < layout.left ||
      mouseX > layout.left + layout.plotWidth ||
      mouseY < layout.topRect.y ||
      mouseY > layout.bottomRect.y + layout.bottomRect.h
    ) {
      clearHover();
      return;
    }
    const span = state.view.x1 - state.view.x0;
    const xValue =
      state.view.x0 + ((mouseX - layout.left) / layout.plotWidth) * span;
    const index = nearestIndex(state.data.x, xValue);
    if (index < 0) {
      clearHover();
      return;
    }
    state.hover = { index };
    updateTooltip(index, mouseX, mouseY);
    requestDraw();
  }

  function minSpan() {
    const fullSpan = state.full.x1 - state.full.x0;
    const count = state.data ? state.data.n : 0;
    if (count < 2) return fullSpan;
    const step = fullSpan / (count - 1);
    return Math.min(fullSpan, Math.max(step * 3, fullSpan * 1e-9));
  }

  function zoomAt(anchor, factor) {
    if (!state.data) return;
    const fullSpan = state.full.x1 - state.full.x0;
    const span = state.view.x1 - state.view.x0;
    if (!(span > 0) || !(fullSpan > 0)) return;
    const newSpan = clamp(span * factor, minSpan(), fullSpan);
    if (newSpan >= fullSpan) {
      state.view = { x0: state.full.x0, x1: state.full.x1 };
    } else {
      let x0 = anchor - (anchor - state.view.x0) * (newSpan / span);
      let x1 = x0 + newSpan;
      if (x0 < state.full.x0) {
        x0 = state.full.x0;
        x1 = x0 + newSpan;
      }
      if (x1 > state.full.x1) {
        x1 = state.full.x1;
        x0 = x1 - newSpan;
      }
      state.view = { x0, x1 };
    }
    invalidate();
    requestDraw();
  }

  function panBy(deltaX) {
    if (!state.data) return;
    const fullSpan = state.full.x1 - state.full.x0;
    const span = state.view.x1 - state.view.x0;
    if (span >= fullSpan) return;
    let x0 = state.view.x0 + deltaX;
    x0 = clamp(x0, state.full.x0, state.full.x1 - span);
    state.view = { x0, x1: x0 + span };
    invalidate();
    requestDraw();
  }

  function resetView() {
    if (!state.data) return;
    state.view = { x0: state.full.x0, x1: state.full.x1 };
    state.hover = null;
    hideTooltip();
    invalidate();
    requestDraw();
  }

  function onWheel(event) {
    if (!state.data || !state.layout || !event.deltaY) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const layout = state.layout;
    if (
      mouseX < layout.left ||
      mouseX > layout.left + layout.plotWidth
    ) {
      return;
    }
    event.preventDefault();
    const fraction = clamp(
      (mouseX - layout.left) / layout.plotWidth,
      0,
      1
    );
    const anchor =
      state.view.x0 + fraction * (state.view.x1 - state.view.x0);
    const factor = event.deltaY < 0 ? 1 / 1.15 : 1.15;
    zoomAt(anchor, factor);
    updateHover(event.clientX, event.clientY);
  }

  function onPointerDown(event) {
    if (!state.data || !state.layout || state.drag) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    const layout = state.layout;
    if (
      mouseX < layout.left ||
      mouseX > layout.left + layout.plotWidth ||
      mouseY < layout.topRect.y ||
      mouseY > layout.bottomRect.y + layout.bottomRect.h
    ) {
      return;
    }
    try {
      canvas.focus({ preventScroll: true });
    } catch (error) {
      canvas.focus();
    }
    state.drag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startView: { ...state.view },
      moved: false,
    };
    try {
      canvas.setPointerCapture(event.pointerId);
    } catch (error) {
      /* Pointer-Capture ist nicht überall verfügbar. */
    }
    canvas.classList.add("is-dragging");
    clearHover();
    event.preventDefault();
  }

  function onPointerMove(event) {
    if (state.drag && event.pointerId === state.drag.pointerId) {
      const deltaX = event.clientX - state.drag.startX;
      if (Math.abs(deltaX) > 2) state.drag.moved = true;
      if (!state.drag.moved) return;
      const layout = state.layout;
      if (!layout) return;
      const span = state.drag.startView.x1 - state.drag.startView.x0;
      const shift = -(deltaX / layout.plotWidth) * span;
      const x0 = clamp(
        state.drag.startView.x0 + shift,
        state.full.x0,
        state.full.x1 - span
      );
      state.view = { x0, x1: x0 + span };
      invalidate();
      requestDraw();
      return;
    }
    if (state.drag) return;
    updateHover(event.clientX, event.clientY);
  }

  function onPointerUp(event) {
    if (!state.drag || event.pointerId !== state.drag.pointerId) return;
    const moved = state.drag.moved;
    state.drag = null;
    canvas.classList.remove("is-dragging");
    try {
      canvas.releasePointerCapture(event.pointerId);
    } catch (error) {
      /* ignorieren */
    }
    if (!moved && event.pointerType === "mouse") {
      updateHover(event.clientX, event.clientY);
    } else {
      clearHover();
    }
  }

  function onPointerCancel(event) {
    if (!state.drag || event.pointerId !== state.drag.pointerId) return;
    state.drag = null;
    canvas.classList.remove("is-dragging");
    clearHover();
  }

  function onDoubleClick(event) {
    if (!state.data) return;
    event.preventDefault();
    resetView();
    updateHover(event.clientX, event.clientY);
  }

  function onKeyDown(event) {
    if (!state.data) return;
    const span = state.view.x1 - state.view.x0;
    let handled = true;
    if (event.key === "ArrowLeft") {
      panBy(-span * 0.1);
    } else if (event.key === "ArrowRight") {
      panBy(span * 0.1);
    } else if (event.key === "+" || event.key === "=") {
      zoomAt(state.view.x0 + span / 2, 1 / 1.15);
    } else if (event.key === "-" || event.key === "_") {
      zoomAt(state.view.x0 + span / 2, 1.15);
    } else if (event.key === "Home" || event.key === "0") {
      resetView();
    } else {
      handled = false;
    }
    if (handled) {
      event.preventDefault();
      clearHover();
    }
  }

  canvas.addEventListener("wheel", onWheel, { passive: false });
  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerCancel);
  canvas.addEventListener("pointerleave", () => {
    if (!state.drag) clearHover();
  });
  canvas.addEventListener("dblclick", onDoubleClick);
  canvas.addEventListener("keydown", onKeyDown);

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => resize());
    observer.observe(canvas.parentElement);
  } else {
    window.addEventListener("resize", resize);
  }
  resize();

  return {
    setData,
    setVisible,
    resetView,
    resize,
    redraw() {
      invalidate();
      requestDraw();
    },
    hasData: () => Boolean(state.data),
  };
}

/* --------------------------------------------------------------------------
   3. Anwendungszustand, API und Oberfläche
   -------------------------------------------------------------------------- */

const FILTERS = ["butterworth", "gaussian", "ideal"];

const state = {
  stations: [],
  stationInfo: null,
  stationId: "46001",
  variableId: "WVHT",
  variables: [],
  tiltDatasets: [],
  tiltDataset: null,
  catalog: null,
  catalogLoading: false,
  catalogWarning: "",
  catalogError: "",
  browserFilter: "all",
  source: "ndbc",
  data: null,
  meta: null,
  currentInfo: null,
  busy: false,
  lastUpload: null,
  startDemo: false,
  startTilt: null,
  activeAbort: null,
  loadSeq: 0,
  chart: null,
  pendingYear: null,
};

const els = {};

const THEME_KEY = "fft-smoothing-theme";
const themeMedia =
  typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

function storedTheme() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "dark" || value === "light" ? value : null;
  } catch (error) {
    return null;
  }
}

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function updateThemeButton() {
  if (!els.themeToggle) return;
  const dark = currentTheme() === "dark";
  els.themeToggle.setAttribute("aria-pressed", String(dark));
  const label = dark ? "Helles Design aktivieren" : "Dunkles Design aktivieren";
  els.themeToggle.setAttribute("aria-label", label);
  els.themeToggle.title = label;
}

function updateThemeMeta(theme) {
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", theme === "dark" ? "#161b22" : "#1769aa");
  }
}

function applyTheme(theme, { persist = true } = {}) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch (error) {
      // Privater Modus o. Ä.: Auswahl gilt dann nur für diese Sitzung.
    }
  }
  refreshChartColors();
  updateThemeButton();
  updateThemeMeta(next);
  if (state.chart) state.chart.redraw();
}

function toggleTheme() {
  applyTheme(currentTheme() === "dark" ? "light" : "dark");
}

function cacheDom() {
  els.themeToggle = $("themeToggle");
  els.browserButton = $("browserButton");
  els.browserDialog = $("browserDialog");
  els.browserClose = $("browserClose");
  els.browserSearch = $("browserSearch");
  els.browserFilters = $("browserFilters");
  els.browserCount = $("browserCount");
  els.browserList = $("browserList");
  els.browserEmpty = $("browserEmpty");
  els.browserNote = $("browserNote");
  els.controls = document.querySelector(".controls");
  els.stationSelect = $("stationSelect");
  els.stationInput = $("stationInput");
  els.stationLoad = $("stationLoad");
  els.variableSelect = $("variableSelect");
  els.tiltSelect = $("tiltSelect");
  els.daysField = $("daysField");
  els.daysInput = $("daysInput");
  els.daysHint = $("daysHint");
  els.yearField = $("yearField");
  els.yearInput = $("yearInput");
  els.yearHint = $("yearHint");
  els.cutoffRange = $("cutoffRange");
  els.cutoffValue = $("cutoffValue");
  els.filterSelect = $("filterSelect");
  els.orderField = $("orderField");
  els.orderInput = $("orderInput");
  els.orderValue = $("orderValue");
  els.detrendInput = $("detrendInput");
  els.padRange = $("padRange");
  els.padValue = $("padValue");
  els.loadButton = $("loadButton");
  els.resetZoom = $("resetZoom");
  els.demoButton = $("demoButton");
  els.dropZone = $("dropZone");
  els.fileInput = $("fileInput");
  els.uploadFilename = $("uploadFilename");
  els.status = $("status");
  els.statusText = $("statusText");
  els.chart = $("chart");
  els.chartTitle = $("chartTitle");
  els.chartSubtitle = $("chartSubtitle");
  els.showOriginal = $("showOriginal");
  els.showSmoothed = $("showSmoothed");
  els.showResidual = $("showResidual");
  els.statRmsOriginal = $("statRmsOriginal");
  els.statRmsOriginalUnit = $("statRmsOriginalUnit");
  els.statRmsSmoothed = $("statRmsSmoothed");
  els.statRmsSmoothedUnit = $("statRmsSmoothedUnit");
  els.statRemoved = $("statRemoved");
  els.statPoints = $("statPoints");
  els.statSkipped = $("statSkipped");
  els.statSampling = $("statSampling");
  els.statDuration = $("statDuration");
  els.statDurationDetail = $("statDurationDetail");
  els.metadata = $("metadata");
  els.timeRadios = Array.from(
    document.querySelectorAll('input[name="timeMode"]')
  );
  els.tooltip = {
    root: $("tooltip"),
    x: $("tooltipX"),
    time: $("tooltipTime"),
    original: $("tooltipOriginal"),
    smoothed: $("tooltipSmoothed"),
    residual: $("tooltipResidual"),
  };
}

function getTimeMode() {
  const checked = els.timeRadios.find((radio) => radio.checked);
  return checked && checked.value === "year" ? "year" : "realtime";
}

function findVariable(variableId) {
  return (
    state.variables.find(
      (variable) => variable && variable.id === variableId
    ) || null
  );
}

function realtimeRange(variableId = state.variableId) {
  const variable = findVariable(variableId);
  const range = variable && variable.range;
  return range && typeof range === "object" ? range : null;
}

function availableYears() {
  if (state.source !== "ndbc" || !state.stationInfo) return [];
  return Array.isArray(state.stationInfo.years) ? state.stationInfo.years : [];
}

function availabilityIsKnown() {
  return state.source === "ndbc" && Boolean(state.stationInfo);
}

function realtimeMaxDays() {
  if (state.tiltDataset) return 1000;
  const range = realtimeRange();
  const value = range ? Number(range.max_days) : NaN;
  if (!Number.isFinite(value)) return 365;
  return Math.max(1, Math.min(1000, Math.ceil(value)));
}

function setTimeMode(mode) {
  for (const radio of els.timeRadios) {
    radio.checked = radio.value === mode;
  }
}

function populateYearOptions() {
  const years = availableYears();
  const previous = els.yearInput.value;
  const pending = state.pendingYear;
  els.yearInput.textContent = "";

  if (!years.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Keine Jahresdaten";
    els.yearInput.appendChild(option);
    state.pendingYear = null;
    return;
  }

  for (const year of years) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    els.yearInput.appendChild(option);
  }

  // Vorherige Auswahl behalten, sonst die Jahresangabe aus der URL, sonst
  // das neueste verfügbare Jahr.
  const candidates = [previous, pending, years[0]];
  let chosen = years[0];
  for (const candidate of candidates) {
    const numeric = Number(candidate);
    if (years.includes(numeric)) {
      chosen = numeric;
      break;
    }
  }
  els.yearInput.value = String(chosen);
  state.pendingYear = null;
}

function updateRealtimeHint() {
  if (state.tiltDataset) {
    els.daysInput.max = "1000";
    els.daysHint.textContent =
      "Stündliche Neigungswerte · 0 = alle verfügbaren Daten";
    return;
  }
  if (!availabilityIsKnown()) {
    els.daysInput.max = "365";
    els.daysHint.textContent = "0 = alle verfügbaren Daten";
    return;
  }

  const range = realtimeRange();
  if (!range) {
    els.daysInput.max = "1";
    els.daysHint.textContent =
      "Für diese Messgröße gibt es aktuell keine Echtzeitdaten.";
    return;
  }

  const maxDays = realtimeMaxDays();
  els.daysInput.max = String(maxDays);
  const current = Number(els.daysInput.value);
  if (Number.isFinite(current) && current > maxDays) {
    els.daysInput.value = String(maxDays);
  }
  els.daysHint.textContent = `Verfügbar: ${formatShortDateRange(
    range.start,
    range.end
  )} · max. ${maxDays} Tage (0 = alles)`;
}

function updateYearHint() {
  if (!availabilityIsKnown()) {
    els.yearHint.textContent = "Historisches Archiv der Station";
    return;
  }

  const years = availableYears();
  if (!years.length) {
    els.yearHint.textContent =
      "Für diese Station sind keine Jahresdaten verfügbar.";
    return;
  }

  const newest = years[0];
  const oldest = years[years.length - 1];
  els.yearHint.textContent =
    newest === oldest
      ? `Verfügbar: ${newest}`
      : `Verfügbar: ${oldest}–${newest} (${years.length} Jahre)`;
}

function applyAvailabilityFor(variableId) {
  if (!availabilityIsKnown()) {
    updateRealtimeHint();
    updateYearHint();
    updateControlStates();
    return;
  }

  populateYearOptions();
  updateRealtimeHint();
  updateYearHint();

  const hasRealtime = Boolean(realtimeRange(variableId));
  const hasYears = availableYears().length > 0;
  const mode = getTimeMode();
  let changed = false;
  if (mode === "realtime" && !hasRealtime && hasYears) {
    setTimeMode("year");
    changed = true;
  } else if (mode === "year" && !hasYears && hasRealtime) {
    setTimeMode("realtime");
    changed = true;
  }
  updateControlStates();
  if (changed) syncHash();
}

function resetAvailabilityControls() {
  state.pendingYear = null;
  els.daysInput.max = "365";
  els.daysHint.textContent = "0 = alle verfügbaren Daten";
  els.yearHint.textContent = "Historisches Archiv der Station";
  updateControlStates();
}

function readSettings() {
  const selectedStation = els.stationSelect.value;
  const station =
    selectedStation && selectedStation !== "__upload__"
      ? selectedStation
      : state.stationId;
  const filter = FILTERS.includes(els.filterSelect.value)
    ? els.filterSelect.value
    : "butterworth";
  const maxDays = realtimeMaxDays();
  const days = clampInt(els.daysInput.value, 0, maxDays, 30);
  if (els.daysInput.value !== String(days)) {
    els.daysInput.value = String(days);
  }
  const year = clampInt(els.yearInput.value, 1900, 2100, 2025);
  if (els.yearInput.value !== String(year)) {
    els.yearInput.value = String(year);
  }
  return {
    station,
    variable: els.variableSelect.value || state.variableId,
    mode: getTimeMode(),
    days,
    year,
    cutoff: clampFloat(els.cutoffRange.value, 0.01, 0.5, 0.1),
    filter,
    order: clampInt(els.orderInput.value, 1, 8, 4),
    detrend: els.detrendInput.checked,
    pad: clampFloat(els.padRange.value, 0, 0.5, 0.1),
  };
}

function buildDataParams(settings, options = {}) {
  const params = new URLSearchParams();
  const demo = Boolean(options.demo);
  if (demo) {
    params.set("demo", "1");
  } else if (options.tilt) {
    params.set("tilt", "1");
    params.set("dataset", String(options.tilt).toUpperCase());
    params.set("days", String(settings.days));
  } else {
    params.set("station", settings.station);
    params.set("variable", settings.variable);
    if (settings.mode === "year") {
      params.set("year", String(settings.year));
      // Ohne days=0 würde der Server nur die letzten 30 Tage des Jahres liefern.
      params.set("days", "0");
    } else {
      params.set("days", String(settings.days));
    }
  }
  params.set("cutoff", settings.cutoff.toFixed(2));
  params.set("filter", settings.filter);
  params.set("order", String(settings.order));
  params.set("detrend", settings.detrend ? "1" : "0");
  params.set("pad", settings.pad.toFixed(2));
  return params;
}

function beginLoad() {
  if (state.activeAbort) state.activeAbort.abort();
  const controller = new AbortController();
  state.activeAbort = controller;
  const sequence = ++state.loadSeq;
  return {
    controller,
    signal: controller.signal,
    isCurrent: () =>
      sequence === state.loadSeq && !controller.signal.aborted,
  };
}

function isAbortError(error) {
  return Boolean(
    error &&
      (error.name === "AbortError" ||
        error.code === 20 ||
        (error.message && error.message.includes("aborted")))
  );
}

function errorMessage(error) {
  if (error && typeof error.message === "string" && error.message.trim()) {
    return error.message;
  }
  return "Unbekannter Fehler.";
}

async function fetchJSON(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new Error(
      "Server nicht erreichbar. Läuft python3 webui.py im Projektordner?"
    );
  }

  let raw = "";
  try {
    raw = await response.text();
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new Error("Die Antwort des Servers konnte nicht gelesen werden.");
  }

  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (error) {
      payload = null;
    }
  }

  if (!response.ok) {
    const message =
      payload && typeof payload.error === "string" && payload.error.trim()
        ? payload.error
        : `HTTP ${response.status}${
            response.statusText ? ` – ${response.statusText}` : ""
          }`;
    throw new Error(message);
  }
  if (!payload || typeof payload !== "object") {
    throw new Error(
      "Der Server hat keine gültige JSON-Antwort geliefert."
    );
  }
  return payload;
}

function setStatus(kind, message) {
  if (!els.status || !els.statusText) return;
  els.status.dataset.kind = kind;
  els.statusText.textContent = message;
}

function showError(message) {
  const text = message ? String(message) : "Unbekannter Fehler.";
  setStatus("error", text.startsWith("Fehler") ? text : `Fehler: ${text}`);
}

function setBusy(busy) {
  state.busy = Boolean(busy);
  if (els.controls) {
    els.controls.setAttribute("aria-busy", state.busy ? "true" : "false");
  }
  if (els.loadButton) {
    els.loadButton.textContent = state.busy
      ? "Lädt …"
      : "Daten laden & glätten";
  }
  updateControlStates();
}

function updateControlStates() {
  if (!els.stationSelect) return;
  const busy = state.busy;
  const mode = getTimeMode();
  const butterworth = els.filterSelect.value === "butterworth";
  const uploadMode = state.source === "upload";
  const tiltMode = Boolean(state.tiltDataset);
  const known = availabilityIsKnown();
  const hasRealtime = !known || Boolean(realtimeRange());
  const hasYears = !known || availableYears().length > 0;

  els.stationSelect.disabled = busy || tiltMode;
  els.stationInput.disabled = busy || tiltMode;
  els.stationLoad.disabled = busy || tiltMode;
  els.tiltSelect.disabled = busy;
  els.variableSelect.disabled =
    busy || tiltMode || !state.variables.length || uploadMode;
  els.timeRadios.forEach((radio) => {
    const unavailable =
      tiltMode && radio.value === "year"
        ? true
        : radio.value === "realtime"
          ? !hasRealtime
          : !hasYears;
    radio.disabled = busy || unavailable;
  });
  els.daysField.hidden = mode === "year";
  els.yearField.hidden = mode !== "year";
  els.daysInput.disabled = busy || mode === "year" || !hasRealtime;
  els.yearInput.disabled = busy || mode !== "year" || !hasYears;
  els.cutoffRange.disabled = busy;
  els.filterSelect.disabled = busy;
  els.orderField.hidden = !butterworth;
  els.orderInput.disabled = busy || !butterworth;
  els.detrendInput.disabled = busy;
  els.padRange.disabled = busy;
  els.loadButton.disabled = busy;
  els.demoButton.disabled = busy;
  els.resetZoom.disabled = busy || !state.chart || !state.chart.hasData();
  els.fileInput.disabled = busy;
  els.dropZone.setAttribute("aria-disabled", busy ? "true" : "false");
}

function updateCutoffLabel() {
  const value = clampFloat(els.cutoffRange.value, 0.01, 0.5, 0.1);
  els.cutoffValue.textContent = `${nf2.format(value)} × Nyquist`;
}

function updateOrderLabel() {
  els.orderValue.textContent = String(
    clampInt(els.orderInput.value, 1, 8, 4)
  );
}

function updatePadLabel() {
  const value = clampFloat(els.padRange.value, 0, 0.5, 0.1);
  els.padValue.textContent = `${nf0.format(value * 100)} %`;
}

function updateTimeMode() {
  updateControlStates();
  if (state.stationInfo) syncHash();
}

function updateFilterMode() {
  updateControlStates();
}

/* --------------------------------------------------------------------------
   Stations- und Variablenlisten
   -------------------------------------------------------------------------- */

function findStationOption(value) {
  return (
    Array.from(els.stationSelect.options).find(
      (option) => option.value === value
    ) || null
  );
}

function ensureStationOption(id, name) {
  if (!id) return null;
  let option = findStationOption(id);
  if (!option) {
    option = document.createElement("option");
    option.value = id;
    option.textContent = id;
    els.stationSelect.appendChild(option);
  }
  if (name) {
    option.textContent = `${id} – ${name}`;
  } else if (!option.textContent) {
    option.textContent = id;
  }
  return option;
}

function removeUploadOption() {
  const option = findStationOption("__upload__");
  if (option) option.remove();
}

function markUploadOption(filename) {
  let option = findStationOption("__upload__");
  if (!option) {
    option = document.createElement("option");
    option.value = "__upload__";
    els.stationSelect.appendChild(option);
  }
  option.textContent = filename
    ? `Eigene CSV – ${filename}`
    : "Eigene CSV";
  els.stationSelect.value = "__upload__";
  updateControlStates();
}

function populateStations() {
  els.stationSelect.textContent = "";
  const groups = new Map();
  for (const station of state.stations) {
    if (!station || !station.id) continue;
    const region = station.region || "Weitere Stationen";
    if (!groups.has(region)) groups.set(region, []);
    groups.get(region).push(station);
  }

  if (!groups.size) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Keine Stationen verfügbar";
    els.stationSelect.appendChild(placeholder);
  }

  for (const [region, stations] of groups) {
    const group = document.createElement("optgroup");
    group.label = region;
    for (const station of stations) {
      const option = document.createElement("option");
      option.value = station.id;
      option.textContent = `${station.id} – ${
        station.name || "Unbenannte Station"
      }`;
      if (station.position) option.title = station.position;
      group.appendChild(option);
    }
    els.stationSelect.appendChild(group);
  }

  ensureStationOption(
    state.stationId,
    state.stationInfo && state.stationInfo.name
  );
  els.stationSelect.value = state.stationId;
}

function populateVariables() {
  els.variableSelect.textContent = "";
  if (!state.variables.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Keine Messgrößen verfügbar";
    els.variableSelect.appendChild(option);
    els.variableSelect.disabled = true;
    return;
  }

  for (const variable of state.variables) {
    if (!variable || !variable.id) continue;
    const option = document.createElement("option");
    option.value = variable.id;
    const parts = [variable.id];
    if (variable.description) parts.push(variable.description);
    let label = parts.join(" – ");
    const unit = displayUnit(variable.unit);
    if (unit) label += ` (${unit})`;
    option.textContent = label;
    if (variable.description) {
      option.title = `${variable.id} – ${variable.description}${
        unit ? ` (${unit})` : ""
      }`;
    }
    els.variableSelect.appendChild(option);
  }

  const available = state.variables.some(
    (variable) => variable.id === state.variableId
  );
  if (!available) {
    state.variableId = state.variables[0].id;
  }
  els.variableSelect.value = state.variableId;
  updateControlStates();
}

/* --------------------------------------------------------------------------
   Kipp-Daten und Datenbrowser
   -------------------------------------------------------------------------- */

function populateTiltOptions() {
  const previous = state.tiltDataset || els.tiltSelect.value;
  els.tiltSelect.textContent = "";

  const off = document.createElement("option");
  off.value = "";
  off.textContent = "Aus – NDBC-Station verwenden";
  els.tiltSelect.appendChild(off);

  for (const dataset of state.tiltDatasets) {
    if (!dataset || !dataset.id) continue;
    const option = document.createElement("option");
    option.value = dataset.id;
    const region = dataset.region ? ` · ${dataset.region}` : "";
    const period = dataset.period ? ` · ${dataset.period}` : "";
    option.textContent = `${dataset.id}${region}${period}`;
    option.title = dataset.detail || dataset.name || dataset.id;
    els.tiltSelect.appendChild(option);
  }

  if (
    previous &&
    state.tiltDatasets.some((dataset) => dataset.id === previous)
  ) {
    els.tiltSelect.value = previous;
  }
}

function catalogEntries() {
  if (!state.catalog || !Array.isArray(state.catalog.entries)) return [];
  return state.catalog.entries;
}

async function loadCatalog(options = {}) {
  if (state.catalog) return state.catalog;
  if (state.catalogLoading) return null;

  state.catalogLoading = true;
  els.browserCount.textContent = "Datenquellen werden geladen …";
  try {
    const payload = await fetchJSON("/api/catalog");
    state.catalog = payload;
    state.tiltDatasets = (Array.isArray(payload.entries) ? payload.entries : [])
      .filter((entry) => entry && entry.kind === "tilt");
    state.catalogWarning =
      typeof payload.warning === "string" ? payload.warning.trim() : "";
    state.catalogError = "";
    populateTiltOptions();
    renderBrowser();
    return payload;
  } catch (error) {
    state.catalogError = errorMessage(error);
    els.browserCount.textContent = "Katalog nicht erreichbar.";
    els.browserNote.textContent = state.catalogError;
    if (!options.silent) showError(state.catalogError);
    return null;
  } finally {
    state.catalogLoading = false;
  }
}

function syncBrowserFilters() {
  const buttons = els.browserFilters.querySelectorAll("button[data-kind]");
  buttons.forEach((button) => {
    const active = button.dataset.kind === state.browserFilter;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function browserEntryMatches(entry, query) {
  if (!query) return true;
  const parts = [
    entry.id,
    entry.name,
    entry.region,
    entry.position,
    entry.detail,
    entry.period,
    entry.type,
  ];
  if (Array.isArray(entry.tags)) parts.push(...entry.tags);
  return parts
    .filter((part) => typeof part === "string")
    .join(" ")
    .toLowerCase()
    .includes(query);
}

function browserEntryNode(entry) {
  const item = document.createElement("li");
  item.className = "browser-item";

  const isLink = entry.kind === "link";
  const node = document.createElement(isLink ? "a" : "button");
  node.className = "browser-entry";
  if (isLink) {
    node.href = entry.url || "#";
    node.target = "_blank";
    node.rel = "noopener";
  } else {
    node.type = "button";
  }

  const title = document.createElement("span");
  title.className = "browser-entry-title";
  if (entry.kind === "ndbc" || entry.kind === "tilt") {
    const id = document.createElement("span");
    id.className = "browser-entry-id";
    id.textContent = entry.id;
    title.appendChild(id);
  }
  const name = document.createElement("span");
  name.textContent = entry.name || entry.id || "Eintrag";
  title.appendChild(name);
  node.appendChild(title);

  const detailText = [entry.position, entry.detail || entry.region]
    .filter((part) => typeof part === "string" && part.trim())
    .join(" · ");
  if (detailText) {
    const detail = document.createElement("span");
    detail.className = "browser-entry-detail";
    detail.textContent = detailText;
    node.appendChild(detail);
  }

  if (Array.isArray(entry.tags) && entry.tags.length) {
    const tags = document.createElement("span");
    tags.className = "browser-tags";
    for (const tag of entry.tags) {
      const badge = document.createElement("span");
      badge.className = `browser-tag is-${entry.kind}`;
      badge.textContent = tag;
      tags.appendChild(badge);
    }
    node.appendChild(tags);
  }

  if (!isLink) {
    node.addEventListener("click", () => chooseBrowserEntry(entry));
  }
  item.appendChild(node);
  return item;
}

function renderBrowser() {
  if (!els.browserList) return;
  const query = els.browserSearch.value.trim().toLowerCase();
  const matched = catalogEntries().filter((entry) => {
    if (!entry) return false;
    if (state.browserFilter !== "all" && entry.kind !== state.browserFilter) {
      return false;
    }
    return browserEntryMatches(entry, query);
  });

  const limit = 250;
  const entries = matched.slice(0, limit);
  const fragment = document.createDocumentFragment();
  for (const entry of entries) fragment.appendChild(browserEntryNode(entry));
  els.browserList.replaceChildren(fragment);
  els.browserEmpty.hidden = matched.length > 0;

  const total = catalogEntries().length;
  if (!total) {
    els.browserCount.textContent = "Keine Einträge verfügbar";
  } else if (matched.length > entries.length) {
    els.browserCount.textContent =
      `${nf0.format(entries.length)} von ${nf0.format(matched.length)} Treffern ` +
      `(${nf0.format(total)} gesamt) · Suche eingrenzen`;
  } else {
    els.browserCount.textContent =
      `${nf0.format(matched.length)} von ${nf0.format(total)} Einträgen`;
  }

  const sourceNote =
    "NDBC: NOAA (öffentlich) · Kipp-Daten: GoMOOS/NERACOOS (University of Maine)";
  els.browserNote.textContent = state.catalogWarning
    ? `${state.catalogWarning} · ${sourceNote}`
    : sourceNote;
}

function chooseBrowserEntry(entry) {
  closeBrowser();
  if (entry.kind === "tilt") {
    loadTilt(entry.id);
  } else if (entry.kind === "ndbc") {
    state.variableId = els.variableSelect.value || state.variableId;
    loadStation(entry.id);
  }
}

function openBrowser() {
  if (!els.browserDialog) return;
  els.browserSearch.value = "";
  state.browserFilter = "all";
  syncBrowserFilters();

  if (typeof els.browserDialog.showModal === "function") {
    els.browserDialog.showModal();
  } else {
    els.browserDialog.setAttribute("open", "");
  }

  if (state.catalog) renderBrowser();
  else loadCatalog();
  els.browserSearch.focus();
}

function closeBrowser() {
  if (!els.browserDialog) return;
  if (typeof els.browserDialog.close === "function") {
    els.browserDialog.close();
  } else {
    els.browserDialog.removeAttribute("open");
  }
}

function handleTiltSelectChange() {
  if (state.busy) return;
  const value = els.tiltSelect.value;
  if (value) {
    loadTilt(value);
    return;
  }

  state.tiltDataset = null;
  updateRealtimeHint();
  updateControlStates();
  if (state.stationId) loadStation(state.stationId);
}

/* --------------------------------------------------------------------------
   Daten normalisieren und auswerten
   -------------------------------------------------------------------------- */

function emptySeries() {
  return {
    n: 0,
    x: new Float64Array(0),
    original: new Float64Array(0),
    smoothed: new Float64Array(0),
    residual: new Float64Array(0),
  };
}

function normalizeSeries(series) {
  if (
    !series ||
    !Array.isArray(series.x) ||
    !Array.isArray(series.original) ||
    !Array.isArray(series.smoothed) ||
    !Array.isArray(series.residual)
  ) {
    throw new Error("Die Antwort enthält keine gültigen Datenreihen.");
  }

  const length = Math.min(
    series.x.length,
    series.original.length,
    series.smoothed.length,
    series.residual.length
  );
  if (!Number.isFinite(length) || length <= 0) return emptySeries();

  let x = new Float64Array(length);
  let original = new Float64Array(length);
  let smoothed = new Float64Array(length);
  let residual = new Float64Array(length);
  let count = 0;

  for (let index = 0; index < length; index += 1) {
    const xValue = toFinite(series.x[index]);
    const originalValue = toFinite(series.original[index]);
    const smoothedValue = toFinite(series.smoothed[index]);
    const residualValue = toFinite(series.residual[index]);
    if (
      Number.isFinite(xValue) &&
      Number.isFinite(originalValue) &&
      Number.isFinite(smoothedValue) &&
      Number.isFinite(residualValue)
    ) {
      x[count] = xValue;
      original[count] = originalValue;
      smoothed[count] = smoothedValue;
      residual[count] = residualValue;
      count += 1;
    }
  }

  if (count < 2) return emptySeries();
  if (count < length) {
    x = x.slice(0, count);
    original = original.slice(0, count);
    smoothed = smoothed.slice(0, count);
    residual = residual.slice(0, count);
  }

  let ascending = true;
  for (let index = 1; index < count; index += 1) {
    if (x[index] < x[index - 1]) {
      ascending = false;
      break;
    }
  }
  if (!ascending) {
    const order = Array.from({ length: count }, (_, index) => index).sort(
      (a, b) => x[a] - x[b]
    );
    const sortedX = new Float64Array(count);
    const sortedOriginal = new Float64Array(count);
    const sortedSmoothed = new Float64Array(count);
    const sortedResidual = new Float64Array(count);
    for (let index = 0; index < count; index += 1) {
      const source = order[index];
      sortedX[index] = x[source];
      sortedOriginal[index] = original[source];
      sortedSmoothed[index] = smoothed[source];
      sortedResidual[index] = residual[source];
    }
    x = sortedX;
    original = sortedOriginal;
    smoothed = sortedSmoothed;
    residual = sortedResidual;
  }

  return { n: count, x, original, smoothed, residual };
}

function rms(values) {
  if (!values || !values.length) return null;
  let sum = 0;
  let count = 0;
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (Number.isFinite(value)) {
      sum += value * value;
      count += 1;
    }
  }
  return count ? Math.sqrt(sum / count) : null;
}

function durationHours(meta, data) {
  const unit = meta && typeof meta.x_unit === "string" ? meta.x_unit : "";
  if (
    data &&
    data.n >= 2 &&
    (unit === "h" || unit === "min" || unit === "s")
  ) {
    const span = data.x[data.n - 1] - data.x[0];
    if (unit === "h") return span;
    if (unit === "min") return span / 60;
    return span / 3600;
  }
  if (isFiniteNumber(meta.duration_h) && meta.duration_h >= 0) {
    return meta.duration_h;
  }
  return null;
}

function formatSampling(meta, data) {
  if (isFiniteNumber(meta.sampling_value)) {
    const unit =
      typeof meta.sampling_unit === "string"
        ? meta.sampling_unit.trim()
        : "";
    if (unit) {
      return `${formatStatNumber(meta.sampling_value)} ${unit}`;
    }
    if (meta.x_unit) {
      return `${formatStatNumber(meta.sampling_value)} ${meta.x_unit}`;
    }
    return formatStatNumber(meta.sampling_value);
  }
  if (isFiniteNumber(meta.sampling_min)) {
    return `${formatStatNumber(meta.sampling_min)} min`;
  }
  if (!data || data.n < 2) return "–";
  const unit = meta && typeof meta.x_unit === "string" ? meta.x_unit : "";
  if (!unit) return "–";
  const step = (data.x[data.n - 1] - data.x[0]) / (data.n - 1);
  if (unit === "h") return `${formatStatNumber(step * 60)} min`;
  if (unit === "min") return `${formatStatNumber(step)} min`;
  if (unit === "s") return `${formatStatNumber(step)} s`;
  return "–";
}

function formatCutoff(meta, info) {
  const parts = [];
  const cutoff = isFiniteNumber(meta.cutoff)
    ? meta.cutoff
    : info && info.settings
      ? info.settings.cutoff
      : null;
  if (cutoff !== null) {
    parts.push(`${nfMax2.format(cutoff)} × Nyquist`);
  }
  if (isFiniteNumber(meta.cutoff_hz) && meta.cutoff_hz > 0) {
    parts.push(formatHz(meta.cutoff_hz));
    parts.push(`Periode ${formatPeriodFromHz(meta.cutoff_hz)}`);
  }
  return parts.length ? parts.join(" · ") : "–";
}

function formatNyquist(meta) {
  if (!isFiniteNumber(meta.nyquist_hz) || meta.nyquist_hz <= 0) {
    return "–";
  }
  return `${formatHz(meta.nyquist_hz)} · Periode ${formatPeriodFromHz(
    meta.nyquist_hz
  )}`;
}

function sourceNode(meta) {
  const wrapper = document.createElement("span");
  const url =
    typeof meta.source_url === "string" ? meta.source_url.trim() : "";
  const license =
    typeof meta.license === "string" ? meta.license.trim() : "";
  let hasContent = false;

  if (/^https?:\/\//i.test(url)) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = url;
    wrapper.appendChild(link);
    hasContent = true;
  }
  if (license) {
    if (hasContent) wrapper.appendChild(document.createTextNode(" · "));
    wrapper.appendChild(document.createTextNode(license));
    hasContent = true;
  }
  if (!hasContent) wrapper.textContent = "–";
  return wrapper;
}

function updateChartHeader(meta, info) {
  const source = info.source || meta.kind || "ndbc";
  let title = "Signal";
  if (source === "upload") {
    title = info.filename ? `Eigene CSV – ${info.filename}` : "Eigene CSV";
  } else if (source === "demo") {
    title = "Demo – 3 Hz + 8 Hz mit Rauschen";
  } else if (source === "tilt") {
    title = `Kipp-Daten · ${meta.dataset || meta.station || "Boje"}`;
  } else {
    title = meta.station ? `Station ${meta.station}` : "Signal";
    if (meta.variable) title += ` · ${meta.variable}`;
  }
  els.chartTitle.textContent = title;

  const subtitleParts = [];
  if (meta.station_name) subtitleParts.push(meta.station_name);
  if (source === "tilt" && meta.deployment) {
    subtitleParts.push(`Verankerung ${meta.deployment}`);
  }
  if (meta.description) subtitleParts.push(meta.description);
  if (meta.filter_label) subtitleParts.push(meta.filter_label);
  if (isFiniteNumber(meta.cutoff_hz) && meta.cutoff_hz > 0) {
    subtitleParts.push(
      `${formatHz(meta.cutoff_hz)} · Periode ${formatPeriodFromHz(
        meta.cutoff_hz
      )}`
    );
  }
  els.chartSubtitle.textContent =
    subtitleParts.join(" · ") || "Keine weiteren Metadaten.";
  els.chart.setAttribute(
    "aria-label",
    `${title}. ${els.chartSubtitle.textContent}. Zwei Panels: Signal und Rest. Pfeiltasten verschieben, Plus und Minus zoomen, Home setzt zurück.`
  );
}

function updateStats(meta, data) {
  const stats = meta.stats && typeof meta.stats === "object" ? meta.stats : {};
  let rmsOriginal = isFiniteNumber(stats.rms_original)
    ? stats.rms_original
    : null;
  let rmsSmoothed = isFiniteNumber(stats.rms_smoothed)
    ? stats.rms_smoothed
    : null;
  let rmsResidual = isFiniteNumber(stats.rms_residual)
    ? stats.rms_residual
    : null;

  if (rmsOriginal === null) rmsOriginal = rms(data.original);
  if (rmsSmoothed === null) rmsSmoothed = rms(data.smoothed);
  if (rmsResidual === null) rmsResidual = rms(data.residual);

  const removed = isFiniteNumber(stats.removed_percent)
    ? stats.removed_percent
    : rmsOriginal && rmsResidual !== null
      ? (100 * rmsResidual) / rmsOriginal
      : null;

  const unit = displayUnit(meta.unit);
  els.statRmsOriginal.textContent =
    rmsOriginal !== null ? formatStatNumber(rmsOriginal) : "–";
  els.statRmsOriginalUnit.textContent = unit;
  els.statRmsSmoothed.textContent =
    rmsSmoothed !== null ? formatStatNumber(rmsSmoothed) : "–";
  els.statRmsSmoothedUnit.textContent = unit;
  els.statRemoved.textContent = formatPercent(removed);

  const points = isFiniteNumber(meta.points) ? meta.points : data.n;
  els.statPoints.textContent = points ? nf0.format(points) : "–";
  els.statSkipped.textContent =
    isFiniteNumber(meta.skipped) && meta.skipped > 0
      ? `${nf0.format(meta.skipped)} übersprungen`
      : data.n
        ? "gültige Werte"
        : "";

  els.statSampling.textContent = formatSampling(meta, data);

  const duration = durationHours(meta, data);
  els.statDuration.textContent =
    duration !== null ? formatDuration(duration) : "–";
  els.statDurationDetail.textContent =
    meta.start && meta.end
      ? `${formatShortDate(meta.start)} – ${formatShortDate(meta.end)}`
      : "";
}

function updateMetadata(meta, info, data) {
  const fragment = document.createDocumentFragment();
  function addRow(label, value) {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    if (value instanceof Node) description.appendChild(value);
    else description.textContent = value == null || value === "" ? "–" : value;
    fragment.appendChild(term);
    fragment.appendChild(description);
  }

  let stationText = "–";
  if (meta.station) {
    stationText = `${meta.station}${
      meta.station_name ? ` – ${meta.station_name}` : ""
    }`;
  } else if (meta.station_name) {
    stationText = meta.station_name;
  } else if (info.source === "upload") {
    stationText = "Eigene CSV";
  }
  addRow("Station", stationText);
  addRow("Position", meta.position || "–");
  addRow("Stationstyp", meta.station_type || "–");
  if (meta.deployment) addRow("Verankerung", meta.deployment);

  let variableText = meta.variable || "–";
  if (meta.variable && meta.description) {
    variableText = `${meta.variable} – ${meta.description}`;
  } else if (!meta.variable && meta.description) {
    variableText = meta.description;
  }
  addRow("Messgröße", variableText);
  addRow("Einheit", displayUnit(meta.unit) || "–");

  let period = formatDateRange(meta.start, meta.end);
  const duration = durationHours(meta, data);
  if (period !== "–" && duration !== null) {
    period += ` · ${formatDuration(duration)}`;
  } else if (period === "–" && duration !== null) {
    period = formatDuration(duration);
  }
  addRow("Zeitraum", period);
  addRow("Abtastung", formatSampling(meta, data));
  addRow("Quelle / Lizenz", sourceNode(meta));

  let filterText = meta.filter_label || meta.filter || "–";
  if (
    !meta.filter_label &&
    meta.filter === "butterworth" &&
    isFiniteNumber(meta.order)
  ) {
    filterText += ` (Ordnung ${meta.order})`;
  }
  addRow("Filter", filterText);
  addRow("Grenzfrequenz", formatCutoff(meta, info));
  addRow("Nyquist", formatNyquist(meta));

  const detrendText =
    meta.detrend === true ? "ja" : meta.detrend === false ? "nein" : "–";
  const paddingText = isFiniteNumber(meta.pad)
    ? `${nf0.format(meta.pad * 100)} %`
    : "–";
  addRow(
    "Verarbeitung",
    `Detrending: ${detrendText} · Padding: ${paddingText}${
      meta.resampled ? " · Raster interpoliert" : ""
    }`
  );

  if (info.filename) addRow("Datei", info.filename);

  els.metadata.replaceChildren(fragment);
}

function successMessage(meta, info, data) {
  const parts = [];
  const source = info.source || meta.kind || "ndbc";
  if (source === "upload") {
    parts.push(
      `„${info.filename || meta.station_name || "Datei"}“ verarbeitet`
    );
  } else if (source === "demo") {
    parts.push("Demo geladen");
  } else if (source === "tilt") {
    parts.push(`Kipp-Daten ${meta.dataset || state.tiltDataset} geladen`);
  } else {
    const station = meta.station || state.stationId;
    parts.push(`Station ${station} geladen`);
    if (meta.variable) parts.push(meta.variable);
  }

  const points = isFiniteNumber(meta.points) ? meta.points : data.n;
  parts.push(`${nf0.format(points)} Punkte`);
  const duration = durationHours(meta, data);
  if (duration !== null) parts.push(formatDuration(duration));
  if (isFiniteNumber(meta.skipped) && meta.skipped > 0) {
    parts.push(`${nf0.format(meta.skipped)} ungültige Werte übersprungen`);
  }
  return `${parts.join(" · ")}.`;
}

function applyPayload(payload, info = {}) {
  const meta =
    payload && payload.meta && typeof payload.meta === "object"
      ? payload.meta
      : {};
  const data = normalizeSeries(payload && payload.series);

  state.meta = meta;
  state.data = data;
  state.currentInfo = info;
  state.source = info.source || meta.kind || "ndbc";
  state.chart.setData(data, meta);
  updateChartHeader(meta, info);
  updateStats(meta, data);
  updateMetadata(meta, info, data);
  updateControlStates();
  syncHash();

  if (data.n === 0) {
    setStatus(
      "info",
      "Die Antwort enthielt keine gültigen Datenpunkte. Bitte Zeitraum oder Messgröße prüfen."
    );
  } else {
    setStatus("success", successMessage(meta, info, data));
  }
}

/* --------------------------------------------------------------------------
   URL-Hash
   -------------------------------------------------------------------------- */

function syncHash() {
  const params = new URLSearchParams();
  if (state.tiltDataset) {
    params.set("tilt", "1");
    params.set("dataset", state.tiltDataset);
  } else {
    if (state.source === "demo") params.set("demo", "1");
    if (state.stationId) params.set("station", state.stationId);
    if (state.variableId) params.set("variable", state.variableId);
  }

  const mode = state.tiltDataset ? "realtime" : getTimeMode();
  params.set("mode", mode);
  if (mode === "year") {
    params.set(
      "year",
      String(clampInt(els.yearInput.value, 1900, 2100, 2025))
    );
  } else {
    params.set(
      "days",
      String(clampInt(els.daysInput.value, 0, realtimeMaxDays(), 30))
    );
  }
  params.set(
    "cutoff",
    clampFloat(els.cutoffRange.value, 0.01, 0.5, 0.1).toFixed(2)
  );
  params.set("filter", els.filterSelect.value);
  params.set("order", String(clampInt(els.orderInput.value, 1, 8, 4)));
  params.set("detrend", els.detrendInput.checked ? "1" : "0");
  params.set("pad", clampFloat(els.padRange.value, 0, 0.5, 0.1).toFixed(2));

  const hash = `#${params.toString()}`;
  if (location.hash === hash) return;
  try {
    history.replaceState(null, "", hash);
  } catch (error) {
    location.hash = hash;
  }
}

function applyHashToForm() {
  const raw = location.hash.startsWith("#")
    ? location.hash.slice(1)
    : location.hash;
  if (!raw) {
    els.stationInput.value = state.stationId;
    return;
  }
  const params = new URLSearchParams(raw);

  const tilt = params.get("tilt");
  const dataset = params.get("dataset");
  if (tilt === "1" && dataset && /^B\d{4}$/.test(dataset.toUpperCase())) {
    state.tiltDataset = dataset.toUpperCase();
    state.startTilt = state.tiltDataset;
  }

  const station = params.get("station");
  if (station && /^[A-Za-z0-9]{3,10}$/.test(station)) {
    state.stationId = station.toUpperCase();
  }
  const variable = params.get("variable");
  if (variable && /^[A-Za-z0-9_]{1,24}$/.test(variable)) {
    state.variableId = variable.toUpperCase();
  }

  const mode = params.get("mode");
  if (mode === "year" || mode === "realtime") {
    for (const radio of els.timeRadios) {
      radio.checked = radio.value === mode;
    }
  }

  const days = params.get("days");
  if (days !== null) {
    els.daysInput.value = String(clampInt(days, 0, 1000, 30));
  }
  const year = params.get("year");
  if (year !== null) {
    state.pendingYear = clampInt(year, 1900, 2100, 2025);
    els.yearInput.value = String(state.pendingYear);
  }
  const cutoff = params.get("cutoff");
  if (cutoff !== null) {
    els.cutoffRange.value = String(
      clampFloat(cutoff, 0.01, 0.5, 0.1)
    );
  }
  const filter = params.get("filter");
  if (filter && FILTERS.includes(filter)) {
    els.filterSelect.value = filter;
  }
  const order = params.get("order");
  if (order !== null) {
    els.orderInput.value = String(clampInt(order, 1, 8, 4));
  }
  const detrend = params.get("detrend");
  if (detrend === "0") els.detrendInput.checked = false;
  else if (detrend === "1") els.detrendInput.checked = true;
  const pad = params.get("pad");
  if (pad !== null) {
    els.padRange.value = String(clampFloat(pad, 0, 0.5, 0.1));
  }
  if (params.get("demo") === "1") state.startDemo = true;

  els.stationInput.value = state.stationId;
  els.tiltSelect.value = state.tiltDataset || "";
  updateCutoffLabel();
  updateOrderLabel();
  updatePadLabel();
}

/* --------------------------------------------------------------------------
   Ladeabläufe
   -------------------------------------------------------------------------- */

async function loadDataWith(ctx, settings) {
  if (!settings.station || !settings.variable) {
    throw new Error("Bitte Station und Messgröße auswählen.");
  }
  const params = buildDataParams(settings);
  const payload = await fetchJSON(`/api/data?${params.toString()}`, {
    signal: ctx.signal,
  });
  if (!ctx.isCurrent()) return;
  applyPayload(payload, { source: "ndbc", settings });
}

async function loadStation(stationId) {
  if (!stationId) {
    showError("Bitte eine Stations-ID angeben.");
    return;
  }
  if (!/^[A-Za-z0-9]{3,10}$/.test(stationId)) {
    showError(
      "Ungültige Stations-ID. Erlaubt sind 3–10 Buchstaben oder Ziffern."
    );
    return;
  }

  const id = stationId.toUpperCase();
  state.stationId = id;
  state.source = "ndbc";
  state.tiltDataset = null;
  els.tiltSelect.value = "";
  updateRealtimeHint();
  removeUploadOption();
  ensureStationOption(
    id,
    state.stationInfo && state.stationInfo.station === id
      ? state.stationInfo.name
      : null
  );
  els.stationSelect.value = id;
  els.stationInput.value = id;

  const ctx = beginLoad();
  setBusy(true);
  setStatus("loading", `Lade Station ${id} …`);

  try {
    const payload = await fetchJSON(
      `/api/variables?station=${encodeURIComponent(id)}`,
      { signal: ctx.signal }
    );
    if (!ctx.isCurrent()) return;

    state.stationInfo = payload;
    state.variables = Array.isArray(payload.variables)
      ? payload.variables.filter((variable) => variable && variable.id)
      : [];
    ensureStationOption(id, payload.name);
    els.stationSelect.value = id;

    if (!state.variables.length) {
      throw new Error("Für diese Station sind keine Messgrößen verfügbar.");
    }

    const preferred = state.variableId;
    const chosen =
      state.variables.find((variable) => variable.id === preferred) ||
      state.variables[0];
    state.variableId = chosen.id;
    populateVariables();
    applyAvailabilityFor(chosen.id);

    setStatus("loading", `Lade ${chosen.id} für Station ${id} …`);
    await loadDataWith(ctx, readSettings());
  } catch (error) {
    if (isAbortError(error) || !ctx.isCurrent()) return;
    showError(errorMessage(error));
  } finally {
    if (ctx.isCurrent()) {
      if (state.activeAbort === ctx.controller) state.activeAbort = null;
      setBusy(false);
    }
  }
}

async function loadCurrent() {
  if (state.busy) return;

  if (state.tiltDataset) {
    await loadTilt(state.tiltDataset);
    return;
  }

  if (els.stationSelect.value === "__upload__") {
    if (!state.lastUpload) {
      showError("Bitte zuerst eine CSV-Datei auswählen.");
      return;
    }
    await uploadText(
      state.lastUpload.filename,
      state.lastUpload.text,
      readSettings()
    );
    return;
  }

  const settings = readSettings();
  if (!settings.station) {
    showError("Bitte eine Station auswählen.");
    return;
  }
  if (!settings.variable) {
    await loadStation(settings.station);
    return;
  }

  state.stationId = settings.station;
  state.variableId = settings.variable;
  state.source = "ndbc";

  const ctx = beginLoad();
  setBusy(true);
  setStatus(
    "loading",
    `Lade ${settings.variable} für Station ${settings.station} …`
  );

  try {
    await loadDataWith(ctx, settings);
  } catch (error) {
    if (isAbortError(error) || !ctx.isCurrent()) return;
    showError(errorMessage(error));
  } finally {
    if (ctx.isCurrent()) {
      if (state.activeAbort === ctx.controller) state.activeAbort = null;
      setBusy(false);
    }
  }
}

async function loadDemo() {
  if (state.busy) return;
  state.tiltDataset = null;
  els.tiltSelect.value = "";
  const ctx = beginLoad();
  setBusy(true);
  setStatus("loading", "Lade Demo-Daten …");

  try {
    const settings = readSettings();
    const params = buildDataParams(settings, { demo: true });
    const payload = await fetchJSON(`/api/data?${params.toString()}`, {
      signal: ctx.signal,
    });
    if (!ctx.isCurrent()) return;

    removeUploadOption();
    if (state.stationId) {
      ensureStationOption(
        state.stationId,
        state.stationInfo && state.stationInfo.name
      );
      els.stationSelect.value = state.stationId;
    }
    applyPayload(payload, { source: "demo", settings });
    resetAvailabilityControls();
  } catch (error) {
    if (isAbortError(error) || !ctx.isCurrent()) return;
    showError(errorMessage(error));
  } finally {
    if (ctx.isCurrent()) {
      if (state.activeAbort === ctx.controller) state.activeAbort = null;
      setBusy(false);
    }
  }
}

async function loadTilt(datasetId) {
  if (state.busy) return;
  const id = String(datasetId || "").toUpperCase();
  if (!/^B\d{4}$/.test(id)) {
    showError("Unbekannter Kipp-Datensatz.");
    return;
  }

  state.tiltDataset = id;
  state.source = "tilt";
  state.variables = [];
  state.stationInfo = null;
  els.tiltSelect.value = id;
  setTimeMode("realtime");

  const ctx = beginLoad();
  setBusy(true);
  setStatus("loading", `Lade Kipp-Daten ${id} …`);

  try {
    const settings = readSettings();
    const params = buildDataParams(settings, { tilt: id });
    const payload = await fetchJSON(`/api/data?${params.toString()}`, {
      signal: ctx.signal,
    });
    if (!ctx.isCurrent()) return;

    removeUploadOption();
    applyPayload(payload, { source: "tilt", dataset: id, settings });
    updateRealtimeHint();
    updateControlStates();
  } catch (error) {
    if (isAbortError(error) || !ctx.isCurrent()) return;
    showError(errorMessage(error));
  } finally {
    if (ctx.isCurrent()) {
      if (state.activeAbort === ctx.controller) state.activeAbort = null;
      setBusy(false);
    }
  }
}

async function uploadText(filename, text, settings) {
  if (state.busy) return;
  state.tiltDataset = null;
  els.tiltSelect.value = "";
  const ctx = beginLoad();
  setBusy(true);
  setStatus("loading", `Verarbeite „${filename}“ …`);

  try {
    const body = {
      filename,
      csv: text,
      cutoff: settings.cutoff,
      filter: settings.filter,
      order: settings.order,
      detrend: settings.detrend,
      pad: settings.pad,
      x_col: 0,
      y_col: -1,
      delimiter: "auto",
    };
    const payload = await fetchJSON("/api/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctx.signal,
    });
    if (!ctx.isCurrent()) return;

    applyPayload(payload, { source: "upload", filename, settings });
    resetAvailabilityControls();
    state.lastUpload = { filename, text };
    markUploadOption(filename);
    els.uploadFilename.hidden = false;
    els.uploadFilename.textContent = filename;
  } catch (error) {
    if (isAbortError(error) || !ctx.isCurrent()) return;
    showError(errorMessage(error));
  } finally {
    if (ctx.isCurrent()) {
      if (state.activeAbort === ctx.controller) state.activeAbort = null;
      setBusy(false);
    }
  }
}

function handleFile(file) {
  if (!file || state.busy) return;
  const name = file.name || "datei.csv";
  const lower = name.toLowerCase();
  if (!lower.endsWith(".csv") && !lower.endsWith(".txt")) {
    showError("Bitte eine .csv- oder .txt-Datei auswählen.");
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showError("Die Datei ist größer als 10 MB.");
    return;
  }

  els.uploadFilename.hidden = false;
  els.uploadFilename.textContent = `${name} · ${formatBytes(file.size)}`;

  const reader = new FileReader();
  reader.onerror = () => {
    showError("Die Datei konnte nicht gelesen werden.");
  };
  reader.onload = () => {
    const text = typeof reader.result === "string" ? reader.result : "";
    if (!text.trim()) {
      showError("Die Datei ist leer.");
      return;
    }
    uploadText(name, text, readSettings());
  };
  reader.readAsText(file, "utf-8");
}

function loadStationFromInput() {
  if (state.busy) return;
  const id = els.stationInput.value.trim().toUpperCase();
  if (!/^[A-Za-z0-9]{3,10}$/.test(id)) {
    showError(
      "Bitte eine gültige Stations-ID mit 3–10 Buchstaben oder Ziffern eingeben."
    );
    els.stationInput.focus();
    return;
  }
  state.variableId = els.variableSelect.value || state.variableId;
  loadStation(id);
}

function handleStationSelectChange() {
  if (state.busy) return;
  const value = els.stationSelect.value;
  if (value === "__upload__") {
    if (state.lastUpload) {
      uploadText(
        state.lastUpload.filename,
        state.lastUpload.text,
        readSettings()
      );
    } else {
      showError("Bitte zuerst eine CSV-Datei auswählen.");
    }
    return;
  }
  if (!value) return;

  removeUploadOption();
  state.variableId = els.variableSelect.value || state.variableId;
  state.stationId = value;
  els.stationInput.value = value;
  loadStation(value);
}

/* --------------------------------------------------------------------------
   Events und Initialisierung
   -------------------------------------------------------------------------- */

function onControlsKeyDown(event) {
  if (event.key !== "Enter") return;
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  if (target.type === "checkbox" || target.type === "radio") return;
  if (target.type === "file") return;

  if (target === els.stationInput) {
    event.preventDefault();
    loadStationFromInput();
    return;
  }
  event.preventDefault();
  loadCurrent();
}

function bindDropZone() {
  const zone = els.dropZone;

  zone.addEventListener("click", (event) => {
    if (event.target === els.fileInput) return;
    if (state.busy) return;
    els.fileInput.click();
  });

  zone.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    if (state.busy) return;
    els.fileInput.click();
  });

  for (const type of ["dragenter", "dragover"]) {
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!state.busy) zone.classList.add("is-dragover");
    });
  }

  for (const type of ["dragleave", "dragend"]) {
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      event.stopPropagation();
      zone.classList.remove("is-dragover");
    });
  }

  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    zone.classList.remove("is-dragover");
    if (state.busy) return;
    const files = event.dataTransfer && event.dataTransfer.files;
    if (files && files.length) handleFile(files[0]);
  });
}

function bindEvents() {
  els.themeToggle.addEventListener("click", toggleTheme);
  els.browserButton.addEventListener("click", openBrowser);
  els.browserClose.addEventListener("click", closeBrowser);
  els.browserSearch.addEventListener("input", renderBrowser);
  els.browserFilters.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-kind]");
    if (!button) return;
    state.browserFilter = button.dataset.kind || "all";
    syncBrowserFilters();
    renderBrowser();
  });
  els.browserDialog.addEventListener("click", (event) => {
    if (event.target === els.browserDialog) closeBrowser();
  });
  els.tiltSelect.addEventListener("change", handleTiltSelectChange);
  els.cutoffRange.addEventListener("input", updateCutoffLabel);
  els.orderInput.addEventListener("input", updateOrderLabel);
  els.padRange.addEventListener("input", updatePadLabel);
  els.filterSelect.addEventListener("change", updateFilterMode);
  els.timeRadios.forEach((radio) => {
    radio.addEventListener("change", updateTimeMode);
  });
  els.variableSelect.addEventListener("change", () => {
    state.variableId = els.variableSelect.value || state.variableId;
    applyAvailabilityFor(state.variableId);
    if (state.stationInfo) syncHash();
  });

  els.loadButton.addEventListener("click", () => {
    loadCurrent();
  });
  els.resetZoom.addEventListener("click", () => {
    if (state.chart) state.chart.resetView();
  });
  els.demoButton.addEventListener("click", () => {
    loadDemo();
  });
  els.stationLoad.addEventListener("click", loadStationFromInput);
  els.stationSelect.addEventListener("change", handleStationSelectChange);

  els.showOriginal.addEventListener("change", () => {
    state.chart.setVisible("original", els.showOriginal.checked);
  });
  els.showSmoothed.addEventListener("change", () => {
    state.chart.setVisible("smoothed", els.showSmoothed.checked);
  });
  els.showResidual.addEventListener("change", () => {
    state.chart.setVisible("residual", els.showResidual.checked);
  });

  els.fileInput.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  els.fileInput.addEventListener("change", () => {
    const file = els.fileInput.files && els.fileInput.files[0];
    els.fileInput.value = "";
    if (file) handleFile(file);
  });
  bindDropZone();
  els.controls.addEventListener("keydown", onControlsKeyDown);
}

async function init() {
  cacheDom();
  applyTheme(currentTheme(), { persist: false });

  if (themeMedia) {
    const onSystemThemeChange = (event) => {
      if (storedTheme()) return;
      applyTheme(event.matches ? "dark" : "light", { persist: false });
    };
    if (typeof themeMedia.addEventListener === "function") {
      themeMedia.addEventListener("change", onSystemThemeChange);
    } else if (typeof themeMedia.addListener === "function") {
      themeMedia.addListener(onSystemThemeChange);
    }
  }

  state.chart = createChart(els.chart, els.tooltip);
  bindEvents();
  loadCatalog({ silent: true });

  applyHashToForm();
  updateTimeMode();
  updateFilterMode();
  updateCutoffLabel();
  updateOrderLabel();
  updatePadLabel();
  updateControlStates();

  setBusy(true);
  setStatus("loading", "Stationen werden geladen …");
  const ctx = beginLoad();

  try {
    const payload = await fetchJSON("/api/stations", {
      signal: ctx.signal,
    });
    if (!ctx.isCurrent()) return;

    state.stations = Array.isArray(payload.stations)
      ? payload.stations
      : [];
    populateStations();
    if (state.activeAbort === ctx.controller) state.activeAbort = null;
    setBusy(false);

    if (state.startTilt) await loadTilt(state.startTilt);
    else if (state.startDemo) await loadDemo();
    else await loadStation(state.stationId);
  } catch (error) {
    if (isAbortError(error) || !ctx.isCurrent()) return;

    state.stations = [];
    populateStations();
    if (state.activeAbort === ctx.controller) state.activeAbort = null;
    setBusy(false);
    showError(errorMessage(error));

    if (state.startTilt) await loadTilt(state.startTilt);
    else if (state.startDemo) await loadDemo();
    else await loadStation(state.stationId);
  }
}

function start() {
  init().catch((error) => {
    if (els.status) showError(errorMessage(error));
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}




