const DEFAULT_COLORS = ["#1f2937", "#1f2937", "#1f2937", "#1f2937", "#1f2937"];
const MULTI_TYPE_COLOR = "#b967ff";
const FALLBACK_VAPORWAVE = ["#f15bb5", "#fee440", "#00bbf9", "#00f5d4", "#9b5de5", "#fb5607", "#ffbe0b", "#72efdd"];
const STAT_PLACEHOLDER = "- - -";
let TYPE_META = {};
let OTHER_BUCKET = "OtherSports";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MS_PER_DAY = 1000 * 60 * 60 * 24;

const typeButtons = document.getElementById("typeButtons");
const yearButtons = document.getElementById("yearButtons");
const typeMenu = document.getElementById("typeMenu");
const yearMenu = document.getElementById("yearMenu");
const typeMenuButton = document.getElementById("typeMenuButton");
const yearMenuButton = document.getElementById("yearMenuButton");
const typeMenuLabel = document.getElementById("typeMenuLabel");
const yearMenuLabel = document.getElementById("yearMenuLabel");
const typeClearButton = document.getElementById("typeClearButton");
const yearClearButton = document.getElementById("yearClearButton");
const typeMenuOptions = document.getElementById("typeMenuOptions");
const yearMenuOptions = document.getElementById("yearMenuOptions");
const heatmaps = document.getElementById("heatmaps");
const tooltip = document.getElementById("tooltip");
const summary = document.getElementById("summary");
const updated = document.getElementById("updated");
const repoLink = document.querySelector(".repo-link");
const isTouch = window.matchMedia("(hover: none) and (pointer: coarse)").matches;

function blurAfterTouchInteraction(element) {
  if (!isTouch || !element || typeof element.blur !== "function") return;
  element.blur();
}

function inferGitHubRepoFromLocation(loc) {
  const host = String(loc.hostname || "").toLowerCase();
  const pathParts = String(loc.pathname || "")
    .split("/")
    .filter(Boolean);

  if (host.endsWith(".github.io")) {
    const owner = host.replace(/\.github\.io$/, "");
    if (!owner) return null;
    const repo = pathParts[0] || `${owner}.github.io`;
    return { owner, repo };
  }

  if (host === "github.com" && pathParts.length >= 2) {
    return { owner: pathParts[0], repo: pathParts[1] };
  }

  return null;
}

function syncRepoLink() {
  if (!repoLink) return;
  const inferred = inferGitHubRepoFromLocation(window.location);
  if (!inferred) return;
  const href = `https://github.com/${inferred.owner}/${inferred.repo}`;
  repoLink.href = href;
  repoLink.textContent = `${inferred.owner}/${inferred.repo}`;
}

function readCssVar(name, fallback, scope) {
  const target = scope || document.body || document.documentElement;
  const value = getComputedStyle(target).getPropertyValue(name).trim();
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function getLayout(scope) {
  return {
    cell: readCssVar("--cell", 12, scope),
    gap: readCssVar("--gap", 2, scope),
    gridPadTop: readCssVar("--grid-pad-top", 6, scope),
    gridPadLeft: readCssVar("--grid-pad-left", 6, scope),
    gridPadRight: readCssVar("--grid-pad-right", 4, scope),
    gridPadBottom: readCssVar("--grid-pad-bottom", 6, scope),
  };
}

function getElementBoxWidth(element) {
  if (!element) return 0;
  const width = element.getBoundingClientRect().width;
  return Number.isFinite(width) ? width : 0;
}

function getElementContentWidth(element) {
  if (!element) return 0;
  const styles = getComputedStyle(element);
  const paddingLeft = parseFloat(styles.paddingLeft) || 0;
  const paddingRight = parseFloat(styles.paddingRight) || 0;
  return Math.max(0, element.clientWidth - paddingLeft - paddingRight);
}

function resetCardLayoutState() {
  if (!heatmaps) return;
  heatmaps.querySelectorAll(".more-stats").forEach((card) => {
    card.classList.remove("more-stats-stacked");
    card.style.removeProperty("--card-graph-rail-width");
    card.style.removeProperty("--frequency-graph-gap");
    card.style.removeProperty("--frequency-grid-pad-right");
  });
  heatmaps.querySelectorAll(".year-card").forEach((card) => {
    card.classList.remove("year-card-stacked");
    card.style.removeProperty("--card-graph-rail-width");
  });
}

function normalizeSideStatCardSize() {
  if (!heatmaps) return;
  const cards = Array.from(
    heatmaps.querySelectorAll(
      ".year-card .card-stats.side-stats-column .card-stat, .more-stats .more-stats-fact-card",
    ),
  );
  cards.forEach((card) => {
    card.style.removeProperty("width");
    card.style.removeProperty("maxWidth");
    card.style.removeProperty("minHeight");
  });
  if (!cards.length) {
    heatmaps.style.removeProperty("--side-stat-card-width");
    heatmaps.style.removeProperty("--side-stat-card-min-height");
    return;
  }

  const maxWidth = cards.reduce((acc, card) => Math.max(acc, Math.ceil(getElementBoxWidth(card))), 0);
  const maxHeight = cards.reduce((acc, card) => Math.max(acc, Math.ceil(card.getBoundingClientRect().height || 0)), 0);

  if (maxWidth > 0) {
    heatmaps.style.setProperty("--side-stat-card-width", `${maxWidth}px`);
  }
  if (maxHeight > 0) {
    heatmaps.style.setProperty("--side-stat-card-min-height", `${maxHeight}px`);
  }
}

function buildSectionLayoutPlan(list) {
  const frequencyCard = list.querySelector(".labeled-card-row-frequency .more-stats");
  const yearCards = Array.from(list.querySelectorAll(".labeled-card-row-year .year-card"));
  if (!frequencyCard && !yearCards.length) return null;

  const yearGraphWidths = yearCards
    .map((card) => getElementBoxWidth(card.querySelector(".heatmap-area")))
    .filter((width) => width > 0);

  let graphRailWidth = yearGraphWidths.length ? Math.max(...yearGraphWidths) : 0;
  let frequencyGap = null;
  let frequencyPadRight = null;

  if (frequencyCard) {
    const frequencyCols = Array.from(frequencyCard.querySelectorAll(".more-stats-grid > .more-stats-col"));
    const columnWidths = frequencyCols
      .map((col) => getElementBoxWidth(col))
      .filter((width) => width > 0);
    const graphCount = columnWidths.length;
    const totalFrequencyGraphWidth = columnWidths.reduce((sum, width) => sum + width, 0);

    if (!graphRailWidth && totalFrequencyGraphWidth > 0) {
      const baseGap = readCssVar("--frequency-graph-gap-base", 12, frequencyCard);
      graphRailWidth = totalFrequencyGraphWidth + (Math.max(0, graphCount - 1) * baseGap);
    }

    if (graphRailWidth > 0 && totalFrequencyGraphWidth > 0) {
      const totalGap = Math.max(0, graphRailWidth - totalFrequencyGraphWidth);
      if (graphCount > 1) {
        // Use subpixel gaps so we don't need trailing right padding that can create tiny overflow scroll.
        frequencyGap = totalGap / (graphCount - 1);
        frequencyPadRight = 0;
      } else {
        frequencyPadRight = totalGap;
      }
    }
  }

  const cards = [
    ...(frequencyCard ? [frequencyCard] : []),
    ...yearCards,
  ];

  let shouldStackSection = false;
  const desktopLike = window.matchMedia("(min-width: 901px)").matches;
  cards.forEach((card) => {
    const statsColumn = card.classList.contains("more-stats")
      ? card.querySelector(".more-stats-facts.side-stats-column")
      : card.querySelector(".card-stats.side-stats-column");
    if (!statsColumn) return;

    const measuredMain = card.classList.contains("more-stats")
      ? getElementBoxWidth(card.querySelector(".more-stats-grid"))
      : getElementBoxWidth(card.querySelector(".heatmap-area"));
    const mainWidth = graphRailWidth > 0 ? graphRailWidth : measuredMain;
    const statsWidth = getElementBoxWidth(statsColumn);
    const sideGap = readCssVar("--stats-column-gap", 12, card);
    const requiredWidth = mainWidth + sideGap + statsWidth;
    const availableWidth = getElementContentWidth(card);
    const overflow = requiredWidth - availableWidth;
    const tolerance = desktopLike
      ? readCssVar("--stack-overflow-tolerance-desktop", 0, card)
      : 0;
    if (overflow > tolerance) {
      shouldStackSection = true;
    }
  });

  return {
    frequencyCard,
    yearCards,
    graphRailWidth,
    frequencyGap,
    frequencyPadRight,
    shouldStackSection,
  };
}

function applySectionLayoutPlan(plan) {
  const {
    frequencyCard,
    yearCards,
    graphRailWidth,
    frequencyGap,
    frequencyPadRight,
    shouldStackSection,
  } = plan;
  const cards = [
    ...(frequencyCard ? [frequencyCard] : []),
    ...yearCards,
  ];

  cards.forEach((card) => {
    if (graphRailWidth > 0) {
      card.style.setProperty("--card-graph-rail-width", `${graphRailWidth}px`);
    } else {
      card.style.removeProperty("--card-graph-rail-width");
    }
  });

  if (frequencyCard) {
    if (Number.isFinite(frequencyGap)) {
      frequencyCard.style.setProperty("--frequency-graph-gap", `${Math.max(0, frequencyGap)}px`);
    } else {
      frequencyCard.style.removeProperty("--frequency-graph-gap");
    }
    if (Number.isFinite(frequencyPadRight)) {
      frequencyCard.style.setProperty("--frequency-grid-pad-right", `${Math.max(0, frequencyPadRight)}px`);
    } else {
      frequencyCard.style.removeProperty("--frequency-grid-pad-right");
    }
  }

  if (frequencyCard) {
    frequencyCard.classList.toggle("more-stats-stacked", shouldStackSection);
  }
  yearCards.forEach((card) => {
    card.classList.toggle("year-card-stacked", shouldStackSection);
  });
}

function alignStackedStatsToYAxisLabels() {
  if (!heatmaps) return;
  resetCardLayoutState();
  normalizeSideStatCardSize();

  const plans = Array.from(heatmaps.querySelectorAll(".type-list"))
    .map((list) => buildSectionLayoutPlan(list))
    .filter(Boolean);

  plans.forEach((plan) => {
    applySectionLayoutPlan(plan);
  });
}

function sundayOnOrBefore(d) {
  const day = d.getDay();
  const offset = day % 7; // Sunday=0
  const result = new Date(d);
  result.setDate(d.getDate() - offset);
  return result;
}

function saturdayOnOrAfter(d) {
  const day = d.getDay();
  const offset = (6 - day + 7) % 7;
  const result = new Date(d);
  result.setDate(d.getDate() + offset);
  return result;
}

function formatLocalDateKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function localDayNumber(date) {
  return Math.floor(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / MS_PER_DAY);
}

function weekIndexFromSundayStart(date, start) {
  return Math.floor((localDayNumber(date) - localDayNumber(start)) / 7);
}

function weekOfYear(date) {
  const yearStart = new Date(date.getFullYear(), 0, 1);
  const start = sundayOnOrBefore(yearStart);
  return weekIndexFromSundayStart(date, start) + 1;
}

function hexToRgb(hex) {
  const cleaned = hex.replace("#", "");
  if (cleaned.length !== 6) return null;
  const r = parseInt(cleaned.slice(0, 2), 16);
  const g = parseInt(cleaned.slice(2, 4), 16);
  const b = parseInt(cleaned.slice(4, 6), 16);
  if (Number.isNaN(r) || Number.isNaN(g) || Number.isNaN(b)) return null;
  return { r, g, b };
}

function heatColor(hex, value, max) {
  if (max <= 0) return DEFAULT_COLORS[0];
  if (value <= 0) return "#0f172a";
  const rgb = hexToRgb(hex);
  const base = hexToRgb("#0f172a");
  if (!rgb || !base) return hex;
  const intensity = Math.pow(Math.min(value / max, 1), 0.75);
  const r = Math.round(base.r + (rgb.r - base.r) * intensity);
  const g = Math.round(base.g + (rgb.g - base.g) * intensity);
  const b = Math.round(base.b + (rgb.b - base.b) * intensity);
  return `rgb(${r}, ${g}, ${b})`;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function positionTooltip(x, y) {
  const padding = 12;
  const rect = tooltip.getBoundingClientRect();
  const maxX = window.innerWidth - rect.width - padding;
  const maxY = window.innerHeight - rect.height - padding;
  const left = clamp(x + 12, padding, maxX);
  const top = clamp(y + 12, padding, maxY);
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
  tooltip.style.bottom = "auto";
}

function showTooltip(text, x, y) {
  tooltip.textContent = text;
  if (isTouch) {
    tooltip.classList.add("touch");
    tooltip.style.transform = "none";
  } else {
    tooltip.classList.remove("touch");
    tooltip.style.transform = "translateY(-8px)";
  }
  tooltip.classList.add("visible");
  requestAnimationFrame(() => positionTooltip(x, y));
}

function hideTooltip() {
  tooltip.classList.remove("visible");
}

function attachTooltip(cell, text) {
  if (!text) return;
  if (!isTouch) {
    cell.addEventListener("mouseenter", (event) => {
      showTooltip(text, event.clientX, event.clientY);
    });
    cell.addEventListener("mousemove", (event) => {
      showTooltip(text, event.clientX, event.clientY);
    });
    cell.addEventListener("mouseleave", hideTooltip);
    return;
  }
  cell.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "touch") return;
    event.preventDefault();
    if (cell.classList.contains("active")) {
      cell.classList.remove("active");
      hideTooltip();
      return;
    }
    const active = document.querySelector(".cell.active");
    if (active) active.classList.remove("active");
    cell.classList.add("active");
    showTooltip(text, event.clientX, event.clientY);
  });
}

function getColors(type) {
  const accent = TYPE_META[type]?.accent || fallbackColor(type);
  return [DEFAULT_COLORS[0], DEFAULT_COLORS[1], DEFAULT_COLORS[2], DEFAULT_COLORS[3], accent];
}

function displayType(type) {
  return TYPE_META[type]?.label || prettifyType(type);
}

function summaryTypeTitle(type) {
  return displayType(type);
}

function formatActivitiesTitle(types) {
  if (!types || !types.length) {
    return "Activities";
  }
  return `${types.map((type) => displayType(type)).join(" + ")} Activities`;
}

function pluralizeLabel(label) {
  if (/(s|x|z|ch|sh)$/i.test(label)) return `${label}es`;
  if (/[^aeiou]y$/i.test(label)) return `${label.slice(0, -1)}ies`;
  return `${label}s`;
}

function getTypeCountNouns(type) {
  if (!type || type === "all") {
    return { singular: "activity", plural: "activities" };
  }

  const meta = TYPE_META[type] || {};
  const singularMeta = String(meta.count_singular || meta.singular || "").trim().toLowerCase();
  const pluralMeta = String(meta.count_plural || meta.plural || "").trim().toLowerCase();
  if (singularMeta && pluralMeta) {
    return { singular: singularMeta, plural: pluralMeta };
  }

  const baseLabel = String(singularMeta || meta.label || prettifyType(type)).trim().toLowerCase();
  if (!baseLabel) {
    return { singular: "activity", plural: "activities" };
  }
  if (pluralMeta) {
    return { singular: baseLabel, plural: pluralMeta };
  }

  if (isOtherSportsType(type) || baseLabel.includes(" ") || /(ing|ion)$/i.test(baseLabel)) {
    return {
      singular: `${baseLabel} activity`,
      plural: `${baseLabel} activities`,
    };
  }

  return {
    singular: baseLabel,
    plural: pluralizeLabel(baseLabel),
  };
}

function formatActivityCountLabel(count, types = []) {
  if (Array.isArray(types) && types.length === 1) {
    const nouns = getTypeCountNouns(types[0]);
    return `${count} ${count === 1 ? nouns.singular : nouns.plural}`;
  }
  return `${count} ${count === 1 ? "Activity" : "Activities"}`;
}

function fallbackColor(type) {
  if (!type) return FALLBACK_VAPORWAVE[0];
  let index = 0;
  for (let i = 0; i < type.length; i += 1) {
    index += (i + 1) * type.charCodeAt(i);
  }
  return FALLBACK_VAPORWAVE[index % FALLBACK_VAPORWAVE.length];
}

function prettifyType(type) {
  return String(type || "Other")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .trim();
}

function formatNumber(value, fractionDigits) {
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    useGrouping: true,
  }).format(value);
}

function formatDistance(meters, units) {
  if (units.distance === "km") {
    return `${formatNumber(meters / 1000, 1)} km`;
  }
  return `${formatNumber(meters / 1609.344, 1)} mi`;
}

function formatDuration(seconds) {
  const minutes = Math.round(seconds / 60);
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${formatNumber(hours, 0)}h ${minutes % 60}m`;
  }
  return `${minutes}m`;
}

function formatElevation(meters, units) {
  if (units.elevation === "m") {
    return `${formatNumber(Math.round(meters), 0)} m`;
  }
  return `${formatNumber(Math.round(meters * 3.28084), 0)} ft`;
}

function buildYearMetricStatItems(totals, units) {
  return [
    {
      key: "distance",
      label: "Total Distance",
      value: totals.distance > 0
        ? formatDistance(totals.distance, units || { distance: "mi" })
        : STAT_PLACEHOLDER,
      filterable: totals.distance > 0,
    },
    {
      key: "moving_time",
      label: "Total Time",
      value: formatDuration(totals.moving_time),
      filterable: totals.moving_time > 0,
    },
    {
      key: "elevation_gain",
      label: "Total Elevation",
      value: totals.elevation > 0
        ? formatElevation(totals.elevation, units || { elevation: "ft" })
        : STAT_PLACEHOLDER,
      filterable: totals.elevation > 0,
    },
  ];
}

function formatHourLabel(hour) {
  const suffix = hour < 12 ? "a" : "p";
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${hour12}${suffix}`;
}

function isOtherSportsType(type) {
  return String(type || "") === String(OTHER_BUCKET || "OtherSports");
}

function getActivitySubtypeLabel(activity) {
  const rawSubtype = activity?.subtype || activity?.raw_type;
  const value = String(rawSubtype || "").trim();
  if (!value) return "";
  if (isOtherSportsType(activity?.type) && value === String(activity?.type || "")) {
    return "";
  }
  return TYPE_META[value]?.label || prettifyType(value);
}

function createTooltipBreakdown() {
  return {
    typeCounts: {},
    otherSubtypeCounts: {},
  };
}

function addTooltipBreakdownCount(breakdown, activityType, subtypeLabel) {
  if (!breakdown) return;
  breakdown.typeCounts[activityType] = (breakdown.typeCounts[activityType] || 0) + 1;
  if (isOtherSportsType(activityType) && subtypeLabel) {
    breakdown.otherSubtypeCounts[subtypeLabel] = (breakdown.otherSubtypeCounts[subtypeLabel] || 0) + 1;
  }
}

function sortBreakdownEntries(counts) {
  return Object.entries(counts || {})
    .filter(([, count]) => count > 0)
    .sort((a, b) => {
      if (b[1] !== a[1]) return b[1] - a[1];
      return String(a[0]).localeCompare(String(b[0]));
    });
}

function formatTypeBreakdownLines(breakdown, types) {
  const lines = [];
  const typeCounts = breakdown?.typeCounts || {};
  const subtypeEntries = sortBreakdownEntries(breakdown?.otherSubtypeCounts || {});
  const selectedTypes = Array.isArray(types) ? types : [];
  const showTypeBreakdown = selectedTypes.length > 1;
  let otherSportsLineRendered = false;

  if (showTypeBreakdown) {
    selectedTypes.forEach((type) => {
      const count = typeCounts[type] || 0;
      if (count <= 0) return;
      const otherType = isOtherSportsType(type);
      lines.push(`${displayType(type)}: ${count}`);
      if (!otherType || !subtypeEntries.length) return;
      otherSportsLineRendered = true;
      subtypeEntries.forEach(([subtype, subtypeCount]) => {
        lines.push(`  - ${subtype}: ${subtypeCount}`);
      });
    });
  }

  if (subtypeEntries.length && !otherSportsLineRendered) {
    const otherTotal = typeCounts[OTHER_BUCKET]
      || subtypeEntries.reduce((sum, [, count]) => sum + count, 0);
    if (otherTotal > 0) {
      lines.push(`${displayType(OTHER_BUCKET)}: ${otherTotal}`);
    }
    subtypeEntries.forEach(([subtype, count]) => {
      lines.push(`  - ${subtype}: ${count}`);
    });
  }

  return lines;
}

function formatTooltipBreakdown(total, breakdown, types) {
  const lines = [`Total: ${formatActivityCountLabel(total, types)}`];
  const detailLines = formatTypeBreakdownLines(breakdown, types);
  if (!detailLines.length) {
    return lines.join("\n");
  }
  lines.push(...detailLines);
  return lines.join("\n");
}

function buildCombinedTypeDetailsByDate(payload, types, years) {
  const detailsByDate = {};
  const typeBreakdownsByDate = {};
  const activities = getFilteredActivities(payload, types, years);

  activities.forEach((activity) => {
    const dateStr = String(activity.date || "");
    if (!dateStr) return;
    if (!detailsByDate[dateStr]) {
      detailsByDate[dateStr] = {
        normalTypes: new Set(),
        otherSubtypeLabels: new Set(),
        hasOtherSports: false,
      };
    }
    if (!typeBreakdownsByDate[dateStr]) {
      typeBreakdownsByDate[dateStr] = createTooltipBreakdown();
    }
    const details = detailsByDate[dateStr];
    const activityType = String(activity.type || "");
    const subtypeLabel = getActivitySubtypeLabel(activity);
    addTooltipBreakdownCount(typeBreakdownsByDate[dateStr], activityType, subtypeLabel);
    if (isOtherSportsType(activityType)) {
      details.hasOtherSports = true;
      if (subtypeLabel) {
        details.otherSubtypeLabels.add(`${subtypeLabel} subtype`);
      }
      return;
    }
    details.normalTypes.add(activityType);
  });

  const orderedTypes = Array.isArray(types) ? types : [];
  const typeLabelsByDate = {};

  Object.entries(detailsByDate).forEach(([dateStr, details]) => {
    const labels = [];
    orderedTypes.forEach((type) => {
      if (!isOtherSportsType(type) && details.normalTypes.has(type)) {
        labels.push(displayType(type));
      }
    });

    const extraTypes = Array.from(details.normalTypes)
      .filter((type) => !isOtherSportsType(type) && !orderedTypes.includes(type))
      .map((type) => displayType(type))
      .sort((a, b) => a.localeCompare(b));
    labels.push(...extraTypes);

    const subtypeLabels = Array.from(details.otherSubtypeLabels).sort((a, b) => a.localeCompare(b));
    if (subtypeLabels.length) {
      labels.push(...subtypeLabels);
    } else if (details.hasOtherSports) {
      labels.push(displayType(OTHER_BUCKET));
    }

    typeLabelsByDate[dateStr] = labels;
  });

  return { typeLabelsByDate, typeBreakdownsByDate };
}

function buildSummary(
  payload,
  types,
  years,
  showTypeBreakdown,
  showActiveDays,
  typeCardTypes,
  activeTypeCards,
  hoverClearedType,
  onTypeCardSelect,
  onTypeCardHoverReset,
  activeYearMetricKey,
  hoverClearedYearMetricKey,
  onYearMetricCardSelect,
  onYearMetricCardHoverReset,
) {
  summary.innerHTML = "";
  summary.classList.remove(
    "summary-center-two-types",
    "summary-center-three-types",
    "summary-center-four-types",
    "summary-center-tail-one",
    "summary-center-tail-two",
    "summary-center-tail-three",
    "summary-center-tail-four",
  );

  const totals = {
    count: 0,
    distance: 0,
    moving_time: 0,
    elevation: 0,
  };
  const typeTotals = {};
  const selectedTypeSet = new Set(types);
  const typeCardsList = Array.isArray(typeCardTypes) && typeCardTypes.length
    ? typeCardTypes.slice()
    : types.slice();
  const visibleTypeCardsList = typeCardsList.length > 1
    ? typeCardsList
    : [];
  const typeCardSet = new Set(visibleTypeCardsList);
  const activeDays = new Set();

  Object.entries(payload.aggregates || {}).forEach(([year, yearData]) => {
    if (!years.includes(Number(year))) return;
    Object.entries(yearData || {}).forEach(([type, entries]) => {
      const includeTotals = selectedTypeSet.has(type);
      const includeTypeCardCount = typeCardSet.has(type);
      if (!includeTotals && !includeTypeCardCount) return;
      if (includeTypeCardCount && !typeTotals[type]) {
        typeTotals[type] = { count: 0 };
      }
      Object.entries(entries || {}).forEach(([dateStr, entry]) => {
        if (includeTotals && (entry.count || 0) > 0) {
          activeDays.add(dateStr);
        }
        if (includeTotals) {
          totals.count += entry.count || 0;
          totals.distance += entry.distance || 0;
          totals.moving_time += entry.moving_time || 0;
          totals.elevation += entry.elevation_gain || 0;
        }
        if (includeTypeCardCount) {
          typeTotals[type].count += entry.count || 0;
        }
      });
    });
  });

  const cards = [
    { title: "Total Activities", value: totals.count.toLocaleString() },
    {
      title: "Total Distance",
      value: totals.distance > 0
        ? formatDistance(totals.distance, payload.units || { distance: "mi" })
        : STAT_PLACEHOLDER,
      metricKey: "distance",
      filterable: totals.distance > 0,
    },
    {
      title: "Total Time",
      value: formatDuration(totals.moving_time),
      metricKey: "moving_time",
      filterable: totals.moving_time > 0,
    },
    {
      title: "Total Elevation",
      value: totals.elevation > 0
        ? formatElevation(totals.elevation, payload.units || { elevation: "ft" })
        : STAT_PLACEHOLDER,
      metricKey: "elevation_gain",
      filterable: totals.elevation > 0,
    },
  ];
  if (showActiveDays) {
    cards.push({ title: "Active Days", value: activeDays.size.toLocaleString() });
  }

  cards.forEach((card) => {
    const metricKey = typeof card.metricKey === "string" ? card.metricKey : "";
    const isMetricCard = Boolean(metricKey);
    const canToggleMetric = isMetricCard
      && card.filterable
      && typeof onYearMetricCardSelect === "function";
    const el = document.createElement(canToggleMetric ? "button" : "div");
    if (canToggleMetric) {
      const isActiveMetric = activeYearMetricKey === metricKey;
      el.type = "button";
      el.className = "summary-card summary-card-action summary-year-metric-card";
      el.dataset.metricKey = metricKey;
      el.classList.toggle("active", isActiveMetric);
      if (!isActiveMetric && hoverClearedYearMetricKey === metricKey) {
        el.classList.add("summary-glow-cleared");
      }
      el.setAttribute("aria-pressed", isActiveMetric ? "true" : "false");
      el.title = `Filter all year cards: ${card.title}`;
      el.addEventListener("click", () => {
        const currentlyActive = el.classList.contains("active");
        onYearMetricCardSelect(metricKey, currentlyActive);
      });
      if (onYearMetricCardHoverReset) {
        el.addEventListener("pointerleave", () => {
          if (el.classList.contains("summary-glow-cleared")) {
            el.classList.remove("summary-glow-cleared");
          }
          onYearMetricCardHoverReset(metricKey);
        });
      }
    } else {
      el.className = "summary-card";
    }
    const title = document.createElement("div");
    title.className = "summary-title";
    title.textContent = card.title;
    const value = document.createElement("div");
    value.className = "summary-value";
    value.textContent = card.value;
    el.appendChild(title);
    el.appendChild(value);
    summary.appendChild(el);
  });

  if (showTypeBreakdown && visibleTypeCardsList.length) {
    const typeCardCount = visibleTypeCardsList.length;
    const centerTailCards = typeCardCount > 5 ? typeCardCount % 5 : 0;
    summary.classList.toggle("summary-center-two-types", visibleTypeCardsList.length === 2);
    summary.classList.toggle("summary-center-three-types", visibleTypeCardsList.length === 3);
    summary.classList.toggle("summary-center-four-types", visibleTypeCardsList.length === 4);
    summary.classList.toggle("summary-center-tail-one", centerTailCards === 1);
    summary.classList.toggle("summary-center-tail-two", centerTailCards === 2);
    summary.classList.toggle("summary-center-tail-three", centerTailCards === 3);
    summary.classList.toggle("summary-center-tail-four", centerTailCards === 4);

    visibleTypeCardsList.forEach((type) => {
      const typeCard = document.createElement("button");
      typeCard.type = "button";
      typeCard.className = "summary-card summary-card-action summary-type-card";
      const isActiveTypeCard = Boolean(activeTypeCards && activeTypeCards.has(type));
      typeCard.classList.toggle("active", isActiveTypeCard);
      if (!isActiveTypeCard && hoverClearedType === type) {
        typeCard.classList.add("summary-glow-cleared");
      }
      typeCard.setAttribute("aria-pressed", isActiveTypeCard ? "true" : "false");
      typeCard.title = `Filter: ${displayType(type)}`;
      const title = document.createElement("div");
      title.className = "summary-title";
      title.textContent = summaryTypeTitle(type);
      const value = document.createElement("div");
      value.className = "summary-type";
      const dot = document.createElement("span");
      dot.className = "summary-dot";
      dot.style.background = getColors(type)[4];
      const text = document.createElement("span");
      text.textContent = (typeTotals[type]?.count || 0).toLocaleString();
      value.appendChild(dot);
      value.appendChild(text);
      typeCard.appendChild(title);
      typeCard.appendChild(value);
      if (onTypeCardHoverReset) {
        typeCard.addEventListener("pointerleave", () => {
          if (typeCard.classList.contains("summary-glow-cleared")) {
            typeCard.classList.remove("summary-glow-cleared");
          }
          onTypeCardHoverReset(type);
        });
      }
      if (onTypeCardSelect) {
        typeCard.addEventListener("click", () => onTypeCardSelect(type, isActiveTypeCard));
      }
      summary.appendChild(typeCard);
    });
  }
}

function buildHeatmapArea(aggregates, year, units, colors, type, layout, options = {}) {
  const heatmapArea = document.createElement("div");
  heatmapArea.className = "heatmap-area";
  const metricHeatmapKey = typeof options.metricHeatmapKey === "string"
    ? options.metricHeatmapKey
    : null;
  const metricHeatmapMax = metricHeatmapKey
    ? Number(options.metricMaxByKey?.[metricHeatmapKey] || 0)
    : 0;
  const metricHeatmapActive = Boolean(metricHeatmapKey) && metricHeatmapMax > 0;
  const metricHeatmapColor = options.metricHeatmapColor || colors[4];
  const metricHeatmapEmptyColor = options.metricHeatmapEmptyColor || DEFAULT_COLORS[0];

  const monthRow = document.createElement("div");
  monthRow.className = "month-row";
  monthRow.style.paddingLeft = `${layout.gridPadLeft}px`;
  heatmapArea.appendChild(monthRow);

  const dayCol = document.createElement("div");
  dayCol.className = "day-col";
  dayCol.style.paddingTop = `${layout.gridPadTop}px`;
  dayCol.style.gap = `${layout.gap}px`;
  DAYS.forEach((label) => {
    const dayLabel = document.createElement("div");
    dayLabel.className = "day-label";
    dayLabel.textContent = label;
    dayLabel.style.height = `${layout.cell}px`;
    dayLabel.style.lineHeight = `${layout.cell}px`;
    dayCol.appendChild(dayLabel);
  });
  heatmapArea.appendChild(dayCol);

  const yearStart = new Date(year, 0, 1);
  const yearEnd = new Date(year, 11, 31);
  const start = sundayOnOrBefore(yearStart);
  const end = saturdayOnOrAfter(yearEnd);

  for (let month = 0; month < 12; month += 1) {
    const monthStart = new Date(year, month, 1);
    const weekIndex = weekIndexFromSundayStart(monthStart, start);
    const monthLabel = document.createElement("div");
    monthLabel.className = "month-label";
    monthLabel.textContent = MONTHS[month];
    monthLabel.style.left = `${weekIndex * (layout.cell + layout.gap)}px`;
    monthRow.appendChild(monthLabel);
  }

  const grid = document.createElement("div");
  grid.className = "grid";

  for (let day = new Date(start); day <= end; day.setDate(day.getDate() + 1)) {
    const dateStr = formatLocalDateKey(day);
    const inYear = day.getFullYear() === year;
    const entry = (aggregates && aggregates[dateStr]) || {
      count: 0,
      distance: 0,
      moving_time: 0,
      elevation_gain: 0,
      activity_ids: [],
    };

    const weekIndex = weekIndexFromSundayStart(day, start);
    const row = day.getDay(); // Sunday=0

    const cell = document.createElement("div");
    cell.className = "cell";
    cell.style.gridColumn = weekIndex + 1;
    cell.style.gridRow = row + 1;

    if (!inYear) {
      cell.classList.add("outside");
      grid.appendChild(cell);
      continue;
    }

    const filled = (entry.count || 0) > 0;
    if (metricHeatmapActive) {
      const metricValue = Number(entry[metricHeatmapKey] || 0);
      cell.style.background = metricValue > 0
        ? heatColor(metricHeatmapColor, metricValue, metricHeatmapMax)
        : metricHeatmapEmptyColor;
    } else if (filled && typeof options.colorForEntry === "function") {
      cell.style.background = options.colorForEntry(entry);
    } else {
      cell.style.background = filled ? colors[4] : colors[0];
    }

    const durationMinutes = Math.round((entry.moving_time || 0) / 60);
    const duration = durationMinutes >= 60
      ? `${Math.floor(durationMinutes / 60)}h ${durationMinutes % 60}m`
      : `${durationMinutes}m`;

    const lines = [
      dateStr,
      formatActivityCountLabel(entry.count, type === "all" ? [] : [type]),
    ];

    const showDistanceElevation = (entry.distance || 0) > 0 || (entry.elevation_gain || 0) > 0;

    if (type === "all") {
      const typeBreakdown = options.typeBreakdownsByDate?.[dateStr];
      const breakdownLines = formatTypeBreakdownLines(typeBreakdown, options.selectedTypes || []);
      if (breakdownLines.length) {
        lines.push(...breakdownLines);
      } else {
        const typeLabels = options.typeLabelsByDate?.[dateStr];
        if (Array.isArray(typeLabels) && typeLabels.length) {
          lines.push(`Types: ${typeLabels.join(", ")}`);
        } else if (entry.types && entry.types.length) {
          lines.push(`Types: ${entry.types.map(displayType).join(", ")}`);
        }
      }
    }

    if (showDistanceElevation) {
      const distance = units.distance === "km"
        ? `${(entry.distance / 1000).toFixed(2)} km`
        : `${(entry.distance / 1609.344).toFixed(2)} mi`;
      const elevation = units.elevation === "m"
        ? `${Math.round(entry.elevation_gain)} m`
        : `${Math.round(entry.elevation_gain * 3.28084)} ft`;
      lines.push(`Distance: ${distance}`);
      lines.push(`Elevation: ${elevation}`);
    }

    lines.push(`Duration: ${duration}`);
    const tooltipText = lines.join("\n");
    if (!isTouch) {
      cell.addEventListener("mouseenter", (event) => {
        showTooltip(tooltipText, event.clientX, event.clientY);
      });
      cell.addEventListener("mousemove", (event) => {
        showTooltip(tooltipText, event.clientX, event.clientY);
      });
      cell.addEventListener("mouseleave", hideTooltip);
    } else {
      cell.addEventListener("pointerdown", (event) => {
        if (event.pointerType !== "touch") return;
        event.preventDefault();
        if (cell.classList.contains("active")) {
          cell.classList.remove("active");
          hideTooltip();
          return;
        }
        const active = grid.querySelector(".cell.active");
        if (active) active.classList.remove("active");
        cell.classList.add("active");
        showTooltip(tooltipText, event.clientX, event.clientY);
      });
    }

    grid.appendChild(cell);
  }

  heatmapArea.appendChild(grid);
  return heatmapArea;
}

function buildSideStatCard(labelText, valueText, options = {}) {
  const {
    tagName = "div",
    className = "card-stat",
    extraClasses = [],
    disabled = false,
    ariaPressed = null,
  } = options;

  const card = document.createElement(tagName);
  card.className = className;
  extraClasses.forEach((name) => {
    if (name) {
      card.classList.add(name);
    }
  });

  if (tagName.toLowerCase() === "button") {
    card.type = "button";
    card.disabled = Boolean(disabled);
  }
  if (ariaPressed !== null) {
    card.setAttribute("aria-pressed", ariaPressed ? "true" : "false");
  }

  const label = document.createElement("div");
  label.className = "card-stat-label";
  label.textContent = labelText;
  const value = document.createElement("div");
  value.className = "card-stat-value";
  value.textContent = valueText;
  card.appendChild(label);
  card.appendChild(value);
  return card;
}

function buildSideStatColumn(items, options = {}) {
  const column = document.createElement("div");
  column.className = options.className || "card-stats side-stats-column";
  (items || []).forEach((item) => {
    if (!item) return;
    const card = buildSideStatCard(item.label, item.value, item.cardOptions || {});
    if (typeof item.enhance === "function") {
      item.enhance(card);
    }
    column.appendChild(card);
  });
  return column;
}

function buildCard(type, year, aggregates, units, options = {}) {
  const card = document.createElement("div");
  card.className = "card year-card";

  const body = document.createElement("div");
  body.className = "card-body";

  const colors = type === "all" ? DEFAULT_COLORS : getColors(type);
  const metricHeatmapColor = options.metricHeatmapColor || (type === "all" ? MULTI_TYPE_COLOR : colors[4]);
  const metricMaxByKey = {
    distance: 0,
    moving_time: 0,
    elevation_gain: 0,
  };
  const layout = getLayout();
  const heatmapOptions = {
    ...options,
    metricMaxByKey,
    metricHeatmapColor,
    metricHeatmapEmptyColor: DEFAULT_COLORS[0],
  };
  const cardMetricKey = typeof options.cardMetricKey === "string"
    ? options.cardMetricKey
    : "";
  const onYearMetricStateChange = typeof options.onYearMetricStateChange === "function"
    ? options.onYearMetricStateChange
    : null;
  let activeMetricKey = typeof options.initialMetricKey === "string"
    ? options.initialMetricKey
    : null;
  let heatmapArea = null;

  const totals = {
    count: 0,
    distance: 0,
    moving_time: 0,
    elevation: 0,
  };
  Object.entries(aggregates || {}).forEach(([, entry]) => {
    totals.count += entry.count || 0;
    totals.distance += entry.distance || 0;
    totals.moving_time += entry.moving_time || 0;
    totals.elevation += entry.elevation_gain || 0;
    metricMaxByKey.distance = Math.max(metricMaxByKey.distance, Number(entry.distance || 0));
    metricMaxByKey.moving_time = Math.max(metricMaxByKey.moving_time, Number(entry.moving_time || 0));
    metricMaxByKey.elevation_gain = Math.max(metricMaxByKey.elevation_gain, Number(entry.elevation_gain || 0));
  });

  const renderHeatmap = () => {
    const nextHeatmapArea = buildHeatmapArea(aggregates, year, units, colors, type, layout, {
      ...heatmapOptions,
      metricHeatmapKey: activeMetricKey,
    });
    if (heatmapArea && heatmapArea.parentNode === body) {
      body.replaceChild(nextHeatmapArea, heatmapArea);
    } else {
      body.appendChild(nextHeatmapArea);
    }
    heatmapArea = nextHeatmapArea;
  };

  const metricItems = buildYearMetricStatItems(totals, units);
  const filterableMetricKeys = metricItems
    .filter((item) => item.filterable)
    .map((item) => item.key);
  if (!filterableMetricKeys.includes(activeMetricKey)) {
    activeMetricKey = null;
  }
  const metricButtons = new Map();
  const reportYearMetricState = (source) => {
    if (!onYearMetricStateChange || !cardMetricKey) return;
    onYearMetricStateChange({
      cardKey: cardMetricKey,
      metricKey: activeMetricKey,
      filterableMetricKeys: filterableMetricKeys.slice(),
      source,
    });
  };
  const renderMetricButtonState = () => {
    metricItems.forEach((item) => {
      const button = metricButtons.get(item.key);
      if (!button) return;
      const active = activeMetricKey === item.key;
      button.classList.toggle("active", active);
      if (active) {
        button.classList.remove("fact-glow-cleared");
      }
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  };

  const statItems = [
    { label: "Total Activities", value: totals.count.toLocaleString() },
    ...metricItems.map((item) => ({
      label: item.label,
      value: item.value,
      cardOptions: item.filterable
        ? {
          tagName: "button",
          className: "card-stat more-stats-fact-card more-stats-fact-button",
          extraClasses: [`year-metric-${item.key.replace(/_/g, "-")}`],
          ariaPressed: false,
        }
        : undefined,
      enhance: (statCard) => {
        if (!item.filterable) return;
        metricButtons.set(item.key, statCard);
        statCard.addEventListener("click", () => {
          const clearing = activeMetricKey === item.key;
          activeMetricKey = clearing ? null : item.key;
          if (clearing) {
            statCard.classList.add("fact-glow-cleared");
          } else {
            statCard.classList.remove("fact-glow-cleared");
          }
          blurAfterTouchInteraction(statCard);
          renderMetricButtonState();
          renderHeatmap();
          reportYearMetricState("card");
          requestAnimationFrame(alignStackedStatsToYAxisLabels);
        });
        if (!isTouch) {
          statCard.addEventListener("pointerleave", () => {
            statCard.classList.remove("fact-glow-cleared");
          });
        }
      },
    })),
  ];
  const stats = buildSideStatColumn(statItems, { className: "card-stats side-stats-column" });
  renderHeatmap();
  renderMetricButtonState();
  reportYearMetricState("init");

  body.appendChild(stats);
  card.appendChild(body);
  return card;
}

function buildEmptyYearCard(type, year, labelOverride) {
  const card = document.createElement("div");
  card.className = "card card-empty-year";
  const body = document.createElement("div");
  body.className = "card-empty-year-body";
  const label = labelOverride || displayType(type);
  const normalizedLabel = String(label).trim().toLowerCase();
  const activityLabel = normalizedLabel.endsWith(" activities") || normalizedLabel.endsWith(" activity")
    ? normalizedLabel
    : `${normalizedLabel} activities`;
  const emptyMessage = `No ${activityLabel} in ${year}`;

  const emptyStat = buildSideStatCard(emptyMessage, "", {
    className: "card-stat card-empty-year-stat",
  });
  body.appendChild(emptyStat);
  card.appendChild(body);
  return card;
}

function buildEmptySelectionCard(types, years) {
  const selectedTypes = Array.isArray(types) ? types.filter(Boolean) : [];
  const label = selectedTypes.length
    ? selectedTypes.map((type) => displayType(type)).join(" + ")
    : "activities";
  const year = Array.isArray(years) && years.length ? years[0] : 0;
  const fallbackType = selectedTypes[0] || "all";
  return buildEmptyYearCard(fallbackType, year, label);
}

function buildLabeledCardRow(label, card, kind) {
  const row = document.createElement("div");
  row.className = "labeled-card-row";
  if (kind) {
    row.classList.add(`labeled-card-row-${kind}`);
  }
  if (card?.classList?.contains("card")) {
    card.classList.add("card-with-labeled-title");
  }

  const title = document.createElement("div");
  title.className = "card-title labeled-card-title";
  title.textContent = label;

  card.insertBefore(title, card.firstChild);
  row.appendChild(card);
  return row;
}

function combineYearAggregates(yearData, types) {
  const combined = {};
  types.forEach((type) => {
    const entries = yearData?.[type] || {};
    Object.entries(entries).forEach(([dateStr, entry]) => {
      if (!combined[dateStr]) {
        combined[dateStr] = {
          count: 0,
          distance: 0,
          moving_time: 0,
          elevation_gain: 0,
          types: new Set(),
        };
      }
      combined[dateStr].count += entry.count || 0;
      combined[dateStr].distance += entry.distance || 0;
      combined[dateStr].moving_time += entry.moving_time || 0;
      combined[dateStr].elevation_gain += entry.elevation_gain || 0;
      if ((entry.count || 0) > 0) {
        combined[dateStr].types.add(type);
      }
    });
  });

  const result = {};
  Object.entries(combined).forEach(([dateStr, entry]) => {
    result[dateStr] = {
      count: entry.count,
      distance: entry.distance,
      moving_time: entry.moving_time,
      elevation_gain: entry.elevation_gain,
      types: Array.from(entry.types),
    };
  });
  return result;
}

function getFilteredActivities(payload, types, years) {
  const activities = payload.activities || [];
  if (!activities.length) return [];
  const yearSet = new Set(years.map(Number));
  const typeSet = new Set(types);
  return activities.filter((activity) => (
    typeSet.has(activity.type) && yearSet.has(Number(activity.year))
  ));
}

function getTypeYearTotals(payload, type, years) {
  const totals = new Map();
  years.forEach((year) => {
    const entries = payload.aggregates?.[String(year)]?.[type] || {};
    let total = 0;
    Object.values(entries).forEach((entry) => {
      total += entry.count || 0;
    });
    totals.set(year, total);
  });
  return totals;
}

function getTypesYearTotals(payload, types, years) {
  if (types.length === 1) {
    return getTypeYearTotals(payload, types[0], years);
  }
  const totals = new Map();
  years.forEach((year) => {
    const yearData = payload.aggregates?.[String(year)] || {};
    let total = 0;
    types.forEach((type) => {
      Object.values(yearData?.[type] || {}).forEach((entry) => {
        total += entry.count || 0;
      });
    });
    totals.set(year, total);
  });
  return totals;
}

function getVisibleYears(years) {
  return years.slice().sort((a, b) => b - a);
}

function getActivityFrequencyCardColor(types) {
  if (types.length === 1) {
    return getColors(types[0])[4];
  }
  return MULTI_TYPE_COLOR;
}

function buildStatPanel(title, subtitle) {
  const panel = document.createElement("div");
  panel.className = "stat-panel";
  if (title) {
    const titleEl = document.createElement("div");
    titleEl.className = "card-title";
    titleEl.textContent = title;
    panel.appendChild(titleEl);
  }
  if (subtitle) {
    const subtitleEl = document.createElement("div");
    subtitleEl.className = "stat-subtitle";
    subtitleEl.textContent = subtitle;
    panel.appendChild(subtitleEl);
  }
  const body = document.createElement("div");
  body.className = "stat-body";
  panel.appendChild(body);
  return { panel, body };
}

function buildStatsOverview(payload, types, years, color) {
  const card = document.createElement("div");
  card.className = "card more-stats";

  const body = document.createElement("div");
  body.className = "more-stats-body";

  const graphs = document.createElement("div");
  graphs.className = "more-stats-grid";
  const facts = buildSideStatColumn([], { className: "more-stats-facts side-stats-column" });

  const yearsDesc = years.slice().sort((a, b) => b - a);
  const emptyColor = DEFAULT_COLORS[0];
  const selectedYearSet = new Set(yearsDesc.map(Number));
  const activities = getFilteredActivities(payload, types, yearsDesc)
    .map((activity) => {
      const dateStr = String(activity.date || "");
      const date = new Date(`${dateStr}T00:00:00`);
      const year = Number(activity.year);
      const rawHour = activity.hour;
      const hourValue = Number(rawHour);
      const hasHour = rawHour !== null
        && rawHour !== undefined
        && Number.isFinite(hourValue)
        && hourValue >= 0
        && hourValue <= 23;
      if (!selectedYearSet.has(year) || Number.isNaN(date.getTime())) {
        return null;
      }
      return {
        date,
        type: activity.type,
        subtype: getActivitySubtypeLabel(activity),
        year,
        dayIndex: date.getDay(),
        monthIndex: date.getMonth(),
        weekIndex: weekOfYear(date),
        hour: hasHour ? hourValue : null,
      };
    })
    .filter(Boolean);

  const oldestActivityYear = activities.reduce(
    (oldest, activity) => Math.min(oldest, activity.year),
    Number.POSITIVE_INFINITY,
  );
  const visibleYearsDesc = Number.isFinite(oldestActivityYear)
    ? yearsDesc.filter((year) => Number(year) >= oldestActivityYear)
    : yearsDesc.slice();
  const yearIndex = new Map();
  visibleYearsDesc.forEach((year, index) => {
    yearIndex.set(Number(year), index);
  });

  const formatBreakdown = (total, breakdown) => formatTooltipBreakdown(total, breakdown, types);

  const dayDisplayLabels = ["Sun", "", "", "Wed", "", "", "Sat"];
  const monthDisplayLabels = ["Jan", "", "Mar", "", "May", "", "Jul", "", "Sep", "", "Nov", ""];

  const buildZeroedMatrix = (columns) => visibleYearsDesc.map(() => new Array(columns).fill(0));
  const buildBreakdownMatrix = (columns) => visibleYearsDesc.map(() => (
    Array.from({ length: columns }, () => createTooltipBreakdown())
  ));

  const buildFrequencyData = (filterFn) => {
    const dayMatrix = buildZeroedMatrix(7);
    const dayBreakdowns = buildBreakdownMatrix(7);
    const monthMatrix = buildZeroedMatrix(12);
    const monthBreakdowns = buildBreakdownMatrix(12);
    const hourMatrix = buildZeroedMatrix(24);
    const hourBreakdowns = buildBreakdownMatrix(24);
    const weekTotals = new Array(54).fill(0);
    let activityCount = 0;
    let hourActivityCount = 0;

    activities.forEach((activity) => {
      if (typeof filterFn === "function" && !filterFn(activity)) {
        return;
      }
      const row = yearIndex.get(activity.year);
      if (row === undefined) return;

      activityCount += 1;
      dayMatrix[row][activity.dayIndex] += 1;
      monthMatrix[row][activity.monthIndex] += 1;
      if (activity.weekIndex >= 1 && activity.weekIndex < weekTotals.length) {
        weekTotals[activity.weekIndex] += 1;
      }

      const dayBucket = dayBreakdowns[row][activity.dayIndex];
      const monthBucket = monthBreakdowns[row][activity.monthIndex];
      addTooltipBreakdownCount(dayBucket, activity.type, activity.subtype);
      addTooltipBreakdownCount(monthBucket, activity.type, activity.subtype);

      if (Number.isFinite(activity.hour)) {
        hourActivityCount += 1;
        hourMatrix[row][activity.hour] += 1;
        const hourBucket = hourBreakdowns[row][activity.hour];
        addTooltipBreakdownCount(hourBucket, activity.type, activity.subtype);
      }
    });

    const dayTotals = dayMatrix.reduce(
      (acc, row) => row.map((value, index) => acc[index] + value),
      new Array(7).fill(0),
    );
    const monthTotals = monthMatrix.reduce(
      (acc, row) => row.map((value, index) => acc[index] + value),
      new Array(12).fill(0),
    );
    const hourTotals = hourMatrix.reduce(
      (acc, row) => row.map((value, index) => acc[index] + value),
      new Array(24).fill(0),
    );

    return {
      activityCount,
      hourActivityCount,
      dayMatrix,
      dayBreakdowns,
      monthMatrix,
      monthBreakdowns,
      hourMatrix,
      hourBreakdowns,
      weekTotals,
      dayTotals,
      monthTotals,
      hourTotals,
    };
  };

  const baseData = buildFrequencyData();
  if (baseData.activityCount <= 0) {
    return buildEmptySelectionCard(types, yearsDesc);
  }

  const dayPanel = buildStatPanel("");

  const monthPanel = buildStatPanel("");

  const hourPanel = buildStatPanel("");

  const bestDayIndex = baseData.dayTotals.reduce((best, value, index) => (
    value > baseData.dayTotals[best] ? index : best
  ), 0);
  const bestDayLabel = `${DAYS[bestDayIndex]} (${baseData.dayTotals[bestDayIndex]})`;

  const bestMonthIndex = baseData.monthTotals.reduce((best, value, index) => (
    value > baseData.monthTotals[best] ? index : best
  ), 0);
  const bestMonthLabel = `${MONTHS[bestMonthIndex]} (${baseData.monthTotals[bestMonthIndex]})`;

  const bestHourIndex = baseData.hourTotals.reduce((best, value, index) => (
    value > baseData.hourTotals[best] ? index : best
  ), 0);
  const bestHourLabel = baseData.hourActivityCount > 0
    ? `${formatHourLabel(bestHourIndex)} (${baseData.hourTotals[bestHourIndex]})`
    : "Not enough time data yet";

  const bestWeekIndex = baseData.weekTotals.reduce((best, value, index) => (
    index === 0 ? best : (value > baseData.weekTotals[best] ? index : best)
  ), 1);
  const bestWeekCount = baseData.weekTotals[bestWeekIndex] || 0;
  const bestWeekLabel = bestWeekCount > 0
    ? `Week ${bestWeekIndex} (${bestWeekCount})`
    : "Not enough data yet";

  const graphColumns = [dayPanel.panel, monthPanel.panel, hourPanel.panel];

  graphColumns.forEach((panel) => {
    const col = document.createElement("div");
    col.className = "more-stats-col";
    col.appendChild(panel);
    graphs.appendChild(col);
  });

  const factItems = [
    {
      key: "most-active-day",
      label: "Most active day",
      value: bestDayLabel,
      filter: (activity) => activity.dayIndex === bestDayIndex,
      filterable: baseData.activityCount > 0,
    },
    {
      key: "most-active-month",
      label: "Most Active Month",
      value: bestMonthLabel,
      filter: (activity) => activity.monthIndex === bestMonthIndex,
      filterable: baseData.activityCount > 0,
    },
    {
      key: "peak-hour",
      label: "Peak hour",
      value: bestHourLabel,
      filter: (activity) => Number.isFinite(activity.hour) && activity.hour === bestHourIndex,
      filterable: baseData.hourActivityCount > 0,
    },
    {
      key: "most-active-week",
      label: "Most active week",
      value: bestWeekLabel,
      filter: (activity) => activity.weekIndex === bestWeekIndex,
      filterable: bestWeekCount > 0,
    },
  ];

  let activeFactKey = null;
  const factButtons = new Map();

  const renderFactButtonState = () => {
    factItems.forEach((item) => {
      const button = factButtons.get(item.key);
      if (!button) return;
      const active = activeFactKey === item.key;
      button.classList.toggle("active", active);
      if (active) {
        button.classList.remove("fact-glow-cleared");
      }
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  };

  const renderFrequencyGraphs = () => {
    const activeFact = factItems.find((item) => item.key === activeFactKey) || null;
    const matrixData = buildFrequencyData(activeFact?.filter);

    dayPanel.body.innerHTML = "";
    dayPanel.body.appendChild(
      buildYearMatrix(
        visibleYearsDesc,
        dayDisplayLabels,
        matrixData.dayMatrix,
        color,
        {
          tooltipLabels: DAYS,
          emptyColor,
          tooltipFormatter: (year, label, value, row, col) => {
            const breakdown = matrixData.dayBreakdowns[row][col] || {};
            return `${year} · ${label}\n${formatBreakdown(value, breakdown)}`;
          },
        },
      ),
    );

    monthPanel.body.innerHTML = "";
    monthPanel.body.appendChild(
      buildYearMatrix(
        visibleYearsDesc,
        monthDisplayLabels,
        matrixData.monthMatrix,
        color,
        {
          tooltipLabels: MONTHS,
          emptyColor,
          tooltipFormatter: (year, label, value, row, col) => {
            const breakdown = matrixData.monthBreakdowns[row][col] || {};
            return `${year} · ${label}\n${formatBreakdown(value, breakdown)}`;
          },
        },
      ),
    );

    hourPanel.body.innerHTML = "";
    if (matrixData.hourActivityCount > 0) {
      const hourLabels = matrixData.hourTotals.map((_, hour) => (hour % 3 === 0 ? formatHourLabel(hour) : ""));
      const hourTooltipLabels = matrixData.hourTotals.map((_, hour) => `${formatHourLabel(hour)} (${hour}:00)`);
      hourPanel.body.appendChild(
        buildYearMatrix(
          visibleYearsDesc,
          hourLabels,
          matrixData.hourMatrix,
          color,
          {
            tooltipLabels: hourTooltipLabels,
            emptyColor,
            tooltipFormatter: (year, label, value, row, col) => {
              const breakdown = matrixData.hourBreakdowns[row][col] || {};
              return `${year} · ${label}\n${formatBreakdown(value, breakdown)}`;
            },
          },
        ),
      );
      return;
    }

    const fallback = document.createElement("div");
    fallback.className = "stat-subtitle";
    fallback.textContent = "Time-of-day stats require activity timestamps.";
    hourPanel.body.appendChild(fallback);
  };

  factItems.forEach((item) => {
    const factCard = buildSideStatCard(item.label, item.value, {
      tagName: "button",
      className: "card-stat more-stats-fact-card more-stats-fact-button",
      extraClasses: item.key ? [`fact-${item.key}`] : [],
      disabled: !item.filterable,
      ariaPressed: false,
    });
    if (item.filterable) {
      factCard.addEventListener("click", () => {
        const clearing = activeFactKey === item.key;
        activeFactKey = clearing ? null : item.key;
        if (clearing) {
          factCard.classList.add("fact-glow-cleared");
        } else {
          factCard.classList.remove("fact-glow-cleared");
        }
        blurAfterTouchInteraction(factCard);
        renderFactButtonState();
        renderFrequencyGraphs();
        requestAnimationFrame(alignStackedStatsToYAxisLabels);
      });
      if (!isTouch) {
        factCard.addEventListener("pointerleave", () => {
          factCard.classList.remove("fact-glow-cleared");
        });
      }
    }
    factButtons.set(item.key, factCard);
    facts.appendChild(factCard);
  });

  renderFactButtonState();
  renderFrequencyGraphs();

  body.appendChild(graphs);
  card.appendChild(body);
  card.appendChild(facts);
  return card;
}

function buildYearMatrix(years, colLabels, matrixValues, color, options = {}) {
  const container = document.createElement("div");
  container.className = "stat-matrix";
  if (!years.length || !colLabels.length) {
    return container;
  }

  const matrixArea = document.createElement("div");
  matrixArea.className = "axis-matrix-area";
  matrixArea.style.gridTemplateColumns = "var(--axis-width) max-content";
  matrixArea.style.gridTemplateRows = "var(--label-row-height) auto";
  matrixArea.style.columnGap = "var(--axis-gap)";

  const monthRow = document.createElement("div");
  monthRow.className = "axis-month-row";
  monthRow.style.paddingLeft = "var(--grid-pad-left)";

  const dayCol = document.createElement("div");
  dayCol.className = "axis-day-col";
  dayCol.style.paddingTop = "var(--grid-pad-top)";
  dayCol.style.gap = "var(--gap)";

  years.forEach((year) => {
    const yLabel = document.createElement("div");
    yLabel.className = "day-label axis-y-label";
    yLabel.textContent = String(year);
    yLabel.style.height = "var(--cell)";
    yLabel.style.lineHeight = "var(--cell)";
    dayCol.appendChild(yLabel);
  });

  const grid = document.createElement("div");
  grid.className = "axis-matrix-grid";
  grid.style.gridTemplateColumns = `repeat(${colLabels.length}, var(--cell))`;
  grid.style.gridTemplateRows = `repeat(${years.length}, var(--cell))`;
  grid.style.gap = "var(--gap)";
  grid.style.padding = "var(--grid-pad-top) var(--grid-pad-right) var(--grid-pad-bottom) var(--grid-pad-left)";

  const max = matrixValues.reduce(
    (acc, row) => Math.max(acc, ...row),
    0,
  );
  const tooltipLabels = options.tooltipLabels || colLabels;

  colLabels.forEach((label, colIndex) => {
    if (!label) return;
    const xLabel = document.createElement("div");
    xLabel.className = "month-label axis-x-label";
    xLabel.textContent = label;
    xLabel.style.left = `calc(${colIndex} * (var(--cell) + var(--gap)))`;
    monthRow.appendChild(xLabel);
  });

  years.forEach((year, row) => {
    colLabels.forEach((_, col) => {
      const cell = document.createElement("div");
      cell.className = "cell axis-matrix-cell";
      cell.style.gridRow = String(row + 1);
      cell.style.gridColumn = String(col + 1);
      const value = matrixValues[row]?.[col] || 0;
      if (options.emptyColor && value <= 0) {
        cell.style.background = options.emptyColor;
      } else {
        cell.style.background = heatColor(color, value, max);
      }
      if (options.tooltipFormatter) {
        const label = tooltipLabels[col];
        const tooltipText = options.tooltipFormatter(year, label, value, row, col);
        attachTooltip(cell, tooltipText);
      }
      grid.appendChild(cell);
    });
  });

  matrixArea.appendChild(monthRow);
  matrixArea.appendChild(dayCol);
  matrixArea.appendChild(grid);
  container.appendChild(matrixArea);
  return container;
}

function renderLoadError(error) {
  const detail = error && typeof error.message === "string" && error.message
    ? error.message
    : "Unexpected error.";

  if (updated) {
    updated.textContent = "Last updated: unavailable";
  }
  if (summary) {
    summary.innerHTML = "";
  }
  if (!heatmaps) {
    return;
  }

  heatmaps.innerHTML = "";
  const card = document.createElement("div");
  card.className = "card";

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = "Dashboard unavailable";

  const body = document.createElement("div");
  body.className = "stat-subtitle";
  body.textContent = `Could not load dashboard data. ${detail}`;

  card.appendChild(title);
  card.appendChild(body);
  heatmaps.appendChild(card);
}

async function init() {
  syncRepoLink();
  const resp = await fetch("data.json");
  if (!resp.ok) {
    throw new Error(`Failed to load data.json (${resp.status})`);
  }
  const payload = await resp.json();
  if (!payload || typeof payload !== "object") {
    throw new Error("Invalid dashboard data format.");
  }
  TYPE_META = payload.type_meta || {};
  OTHER_BUCKET = String(payload.other_bucket || "OtherSports");
  (payload.types || []).forEach((type) => {
    if (!TYPE_META[type]) {
      TYPE_META[type] = { label: prettifyType(type), accent: fallbackColor(type) };
    }
  });

  if (payload.generated_at) {
    const updatedAt = new Date(payload.generated_at);
    if (!Number.isNaN(updatedAt.getTime())) {
      updated.textContent = `Last updated: ${updatedAt.toLocaleString([], {
        year: "numeric",
        month: "numeric",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })}`;
    }
  }

  const typeOptions = [
    { value: "all", label: "All Activities" },
    ...payload.types.map((type) => ({ value: type, label: displayType(type) })),
  ];

  function renderButtons(container, options, onSelect) {
    if (!container) return;
    container.innerHTML = "";
    options.forEach((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "filter-button";
      button.dataset.value = option.value;
      button.textContent = option.label;
      button.addEventListener("click", () => onSelect(option.value));
      container.appendChild(button);
    });
  }

  function renderMenuOptions(container, options, selectedValues, isAllSelected, onSelect, normalizeValue) {
    if (!container) return;
    container.innerHTML = "";
    options.forEach((option) => {
      const rawValue = String(option.value);
      const normalized = normalizeValue ? normalizeValue(rawValue) : rawValue;
      const isActive = rawValue === "all"
        ? isAllSelected
        : (!isAllSelected && selectedValues.has(normalized));
      const isChecked = isAllSelected || isActive;

      const row = document.createElement("div");
      row.className = "filter-menu-option";
      row.setAttribute("role", "button");
      if (isActive) {
        row.classList.add("active");
      }
      row.dataset.value = rawValue;

      const label = document.createElement("span");
      label.className = "filter-menu-option-label";
      label.textContent = option.label;

      const check = document.createElement("input");
      check.type = "checkbox";
      check.className = "filter-menu-check";
      check.checked = isChecked;
      check.tabIndex = -1;
      check.setAttribute("aria-hidden", "true");

      row.appendChild(label);
      row.appendChild(check);
      row.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
      });
      row.addEventListener("click", () => onSelect(rawValue));
      container.appendChild(row);
    });
  }

  function renderMenuDoneButton(container, onDone) {
    if (!container) return;
    const done = document.createElement("button");
    done.type = "button";
    done.className = "filter-menu-done";
    done.textContent = "Done";
    done.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
    });
    done.addEventListener("click", () => onDone());
    container.appendChild(done);
  }

  let resizeTimer = null;
  let lastViewportWidth = window.innerWidth;
  let lastIsNarrowLayout = window.matchMedia("(max-width: 900px)").matches;

  let allTypesMode = true;
  let selectedTypes = new Set();
  let allYearsMode = true;
  let selectedYears = new Set();
  let currentVisibleYears = payload.years.slice().sort((a, b) => b - a);
  let hoverClearedSummaryType = null;
  let activeSummaryYearMetricKey = null;
  let hoverClearedSummaryYearMetricKey = null;
  const yearMetricSelectionByCard = new Map();
  let visibleYearMetricCardKeys = new Set();

  function hasVisibleYearCardMetric(metricKey) {
    if (!metricKey) return false;
    for (const cardKey of visibleYearMetricCardKeys) {
      if (yearMetricSelectionByCard.get(cardKey) === metricKey) {
        return true;
      }
    }
    return false;
  }

  function clearMetricSelectionAcrossCards(metricKey) {
    if (!metricKey) return;
    yearMetricSelectionByCard.forEach((selectedMetricKey, cardKey) => {
      if (selectedMetricKey === metricKey) {
        yearMetricSelectionByCard.set(cardKey, null);
      }
    });
  }

  function syncSummaryYearMetricSelectionFromCards() {
    if (!activeSummaryYearMetricKey) return;
    if (hasVisibleYearCardMetric(activeSummaryYearMetricKey)) return;
    clearMetricSelectionAcrossCards(activeSummaryYearMetricKey);
    activeSummaryYearMetricKey = null;
    hoverClearedSummaryYearMetricKey = null;
  }

  function syncSummaryYearMetricButtons() {
    if (!summary) return;
    const buttons = Array.from(summary.querySelectorAll(".summary-year-metric-card"));
    if (!buttons.length) return;
    buttons.forEach((button) => {
      const metricKey = String(button.dataset.metricKey || "");
      const active = metricKey === activeSummaryYearMetricKey;
      button.classList.toggle("active", active);
      if (active) {
        button.classList.remove("summary-glow-cleared");
      } else {
        button.classList.toggle("summary-glow-cleared", hoverClearedSummaryYearMetricKey === metricKey);
      }
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function areAllTypesSelected() {
    return allTypesMode;
  }

  function areAllYearsSelected() {
    return allYearsMode;
  }

  function selectedTypesList() {
    if (areAllTypesSelected()) {
      return payload.types.slice();
    }
    return payload.types.filter((type) => selectedTypes.has(type));
  }

  function selectedYearsList(visibleYears) {
    if (areAllYearsSelected()) {
      return visibleYears.slice();
    }
    return visibleYears.filter((year) => selectedYears.has(Number(year)));
  }

  function updateButtonState(container, selectedValues, isAllSelected, normalizeValue) {
    if (!container) return;
    container.querySelectorAll(".filter-button").forEach((button) => {
      const rawValue = String(button.dataset.value || "");
      const value = normalizeValue ? normalizeValue(rawValue) : rawValue;
      const isActive = rawValue === "all"
        ? isAllSelected
        : (!isAllSelected && selectedValues.has(value));
      button.classList.toggle("active", isActive);
    });
  }

  function toggleType(value) {
    if (value === "all") {
      allTypesMode = true;
      selectedTypes.clear();
      return;
    }
    if (!payload.types.includes(value)) return;
    if (allTypesMode) {
      allTypesMode = false;
      selectedTypes = new Set([value]);
      return;
    }
    if (selectedTypes.has(value)) {
      selectedTypes.delete(value);
      if (!selectedTypes.size) {
        allTypesMode = true;
      }
      return;
    }
    selectedTypes.add(value);
  }

  function toggleTypeMenu(value) {
    if (value === "all") {
      const isMobileLayout = window.matchMedia("(max-width: 900px)").matches;
      if (isMobileLayout && allTypesMode) {
        allTypesMode = false;
        selectedTypes.clear();
        return;
      }
      allTypesMode = true;
      selectedTypes.clear();
      return;
    }
    if (!payload.types.includes(value)) return;
    if (allTypesMode) {
      allTypesMode = false;
      selectedTypes = new Set(payload.types.filter((type) => type !== value));
      return;
    }
    if (selectedTypes.has(value)) {
      selectedTypes.delete(value);
      return;
    }
    selectedTypes.add(value);
  }

  function toggleTypeFromSummaryCard(type) {
    toggleType(type);
  }

  function toggleYear(value) {
    if (value === "all") {
      allYearsMode = true;
      selectedYears.clear();
      return;
    }
    const year = Number(value);
    if (!Number.isFinite(year) || !currentVisibleYears.includes(year)) return;
    if (allYearsMode) {
      allYearsMode = false;
      selectedYears = new Set([year]);
      return;
    }
    if (selectedYears.has(year)) {
      selectedYears.delete(year);
      if (!selectedYears.size) {
        allYearsMode = true;
      }
      return;
    }
    selectedYears.add(year);
  }

  function toggleYearMenu(value) {
    if (value === "all") {
      const isMobileLayout = window.matchMedia("(max-width: 900px)").matches;
      if (isMobileLayout && allYearsMode) {
        allYearsMode = false;
        selectedYears.clear();
        return;
      }
      allYearsMode = true;
      selectedYears.clear();
      return;
    }
    const year = Number(value);
    if (!Number.isFinite(year) || !currentVisibleYears.includes(year)) return;
    if (allYearsMode) {
      allYearsMode = false;
      selectedYears = new Set(currentVisibleYears.filter((visibleYear) => visibleYear !== year));
      return;
    }
    if (selectedYears.has(year)) {
      selectedYears.delete(year);
      return;
    }
    selectedYears.add(year);
  }

  function finalizeTypeSelection() {
    if (!areAllTypesSelected() && selectedTypes.size === payload.types.length) {
      allTypesMode = true;
      selectedTypes.clear();
    }
  }

  function finalizeYearSelection() {
    if (!areAllYearsSelected() && selectedYears.size === currentVisibleYears.length) {
      allYearsMode = true;
      selectedYears.clear();
    }
  }

  function getTypeMenuText(types, allTypesSelected) {
    if (allTypesSelected) return "All Activities";
    if (types.length) return types.map((type) => displayType(type)).join(", ");
    return "No Activities Selected";
  }

  function getYearMenuText(years, allYearsSelected) {
    if (allYearsSelected) return "All Years";
    if (years.length) return years.map((year) => String(year)).join(", ");
    return "No Years Selected";
  }

  function setMenuLabel(labelEl, text, fallbackText) {
    if (!labelEl) return;
    labelEl.textContent = text;
    if (!fallbackText || fallbackText === text) return;
    if (!window.matchMedia("(max-width: 900px)").matches) return;
    const menuButton = labelEl.closest(".filter-menu-button");
    if (!menuButton || menuButton.offsetParent === null) return;
    if (labelEl.scrollWidth > labelEl.clientWidth) {
      labelEl.textContent = fallbackText;
    }
  }

  function setMenuOpen(menuEl, buttonEl, isOpen) {
    if (!menuEl) return;
    menuEl.classList.toggle("open", isOpen);
    if (buttonEl) {
      buttonEl.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }
  }

  function update(options = {}) {
    const keepTypeMenuOpen = Boolean(options.keepTypeMenuOpen);
    const keepYearMenuOpen = Boolean(options.keepYearMenuOpen);
    const allTypesSelected = areAllTypesSelected();
    const types = selectedTypesList();
    const visibleYears = getVisibleYears(payload.years);
    currentVisibleYears = visibleYears.slice();
    if (!areAllYearsSelected()) {
      const visibleSet = new Set(visibleYears.map(Number));
      Array.from(selectedYears).forEach((year) => {
        if (!visibleSet.has(Number(year))) {
          selectedYears.delete(year);
        }
      });
    }
    const allYearsSelected = areAllYearsSelected();
    const yearOptions = [
      { value: "all", label: "All Years" },
      ...visibleYears.map((year) => ({ value: String(year), label: String(year) })),
    ];
    renderButtons(yearButtons, yearOptions, (value) => {
      toggleYear(value);
      update();
    });
    renderMenuOptions(
      typeMenuOptions,
      typeOptions,
      selectedTypes,
      allTypesSelected,
      (value) => {
        toggleTypeMenu(value);
        update({ keepTypeMenuOpen: true });
      },
    );
    renderMenuDoneButton(typeMenuOptions, () => {
      finalizeTypeSelection();
      setMenuOpen(typeMenu, typeMenuButton, false);
      update();
    });
    renderMenuOptions(
      yearMenuOptions,
      yearOptions,
      selectedYears,
      allYearsSelected,
      (value) => {
        toggleYearMenu(value);
        update({ keepYearMenuOpen: true });
      },
      (v) => Number(v),
    );
    renderMenuDoneButton(yearMenuOptions, () => {
      finalizeYearSelection();
      setMenuOpen(yearMenu, yearMenuButton, false);
      update();
    });
    const years = selectedYearsList(visibleYears);
    years.sort((a, b) => b - a);
    const frequencyCardColor = getActivityFrequencyCardColor(types);
    const showCombinedTypes = types.length > 1;
    const allAvailableTypesSelected = types.length === payload.types.length;
    const activeSummaryTypeCards = allTypesSelected ? new Set() : new Set(types);
    const nextVisibleYearMetricCardKeys = new Set();
    const onYearMetricStateChange = ({ cardKey, metricKey, filterableMetricKeys, source }) => {
      const key = String(cardKey || "");
      if (!key) return;
      const filterableSet = new Set(filterableMetricKeys || []);
      const normalizedMetricKey = typeof metricKey === "string" && filterableSet.has(metricKey)
        ? metricKey
        : null;
      yearMetricSelectionByCard.set(key, normalizedMetricKey);
      if (source === "card") {
        syncSummaryYearMetricSelectionFromCards();
        syncSummaryYearMetricButtons();
      }
    };

    updateButtonState(typeButtons, selectedTypes, allTypesSelected);
    updateButtonState(yearButtons, selectedYears, allYearsSelected, (v) => Number(v));
    const typeMenuText = getTypeMenuText(types, allTypesSelected || allAvailableTypesSelected);
    const yearMenuText = getYearMenuText(years, allYearsSelected);
    setMenuLabel(
      typeMenuLabel,
      typeMenuText,
      !allTypesSelected && !allAvailableTypesSelected && types.length > 1 ? "Multiple Activities Selected" : "",
    );
    setMenuLabel(
      yearMenuLabel,
      yearMenuText,
      !allYearsSelected && years.length > 1 ? "Multiple Years Selected" : "",
    );
    if (typeClearButton) {
      typeClearButton.disabled = areAllTypesSelected();
    }
    if (yearClearButton) {
      yearClearButton.disabled = areAllYearsSelected();
    }
    if (keepTypeMenuOpen) {
      setMenuOpen(typeMenu, typeMenuButton, true);
    }
    if (keepYearMenuOpen) {
      setMenuOpen(yearMenu, yearMenuButton, true);
    }

    if (heatmaps) {
      heatmaps.innerHTML = "";
      const showMoreStats = true;
      if (showCombinedTypes) {
        const section = document.createElement("div");
        section.className = "type-section";
        const header = document.createElement("div");
        header.className = "type-header";
        header.textContent = allAvailableTypesSelected ? "All Activities" : formatActivitiesTitle(types);
        section.appendChild(header);
        const list = document.createElement("div");
        list.className = "type-list";
        const yearTotals = getTypesYearTotals(payload, types, years);
        const cardYears = years.slice();
        const { typeLabelsByDate, typeBreakdownsByDate } = buildCombinedTypeDetailsByDate(payload, types, cardYears);
        const emptyLabel = types.map((type) => displayType(type)).join(" + ");
        if (showMoreStats) {
          list.appendChild(
            buildLabeledCardRow(
              "Activity Frequency",
              buildStatsOverview(payload, types, cardYears, frequencyCardColor),
              "frequency",
            ),
          );
        }
        cardYears.forEach((year) => {
          const yearData = payload.aggregates?.[String(year)] || {};
          const aggregates = combineYearAggregates(yearData, types);
          const total = yearTotals.get(year) || 0;
          const combinedKey = `combined:${types.join("|")}:${year}`;
          const colorForEntry = (entry) => {
            if (!entry.types || entry.types.length === 0) {
              return DEFAULT_COLORS[0];
            }
            if (entry.types.length === 1) {
              return getColors(entry.types[0])[4];
            }
            return MULTI_TYPE_COLOR;
          };
          const initialMetricKey = activeSummaryYearMetricKey || (
            yearMetricSelectionByCard.has(combinedKey)
              ? yearMetricSelectionByCard.get(combinedKey)
              : null
          );
          const card = total > 0
            ? buildCard(
              "all",
              year,
              aggregates,
              payload.units || { distance: "mi", elevation: "ft" },
              {
                colorForEntry,
                metricHeatmapColor: frequencyCardColor,
                cardMetricKey: combinedKey,
                initialMetricKey,
                onYearMetricStateChange,
                selectedTypes: types,
                typeBreakdownsByDate,
                typeLabelsByDate,
              },
            )
            : buildEmptyYearCard("all", year, emptyLabel);
          if (total > 0) {
            nextVisibleYearMetricCardKeys.add(combinedKey);
          }
          list.appendChild(buildLabeledCardRow(String(year), card, "year"));
        });
        section.appendChild(list);
        heatmaps.appendChild(section);
      } else {
        types.forEach((type) => {
          const section = document.createElement("div");
          section.className = "type-section";
          const header = document.createElement("div");
          header.className = "type-header";
          header.textContent = formatActivitiesTitle([type]);
          section.appendChild(header);

          const list = document.createElement("div");
          list.className = "type-list";
          const yearTotals = getTypeYearTotals(payload, type, years);
          const cardYears = years.slice();
          if (showMoreStats) {
            list.appendChild(
              buildLabeledCardRow(
                "Activity Frequency",
                buildStatsOverview(payload, [type], cardYears, frequencyCardColor),
                "frequency",
              ),
            );
          }
          cardYears.forEach((year) => {
            const aggregates = payload.aggregates?.[String(year)]?.[type] || {};
            const total = yearTotals.get(year) || 0;
            const singleTypeKey = `type:${type}:${year}`;
            const initialMetricKey = activeSummaryYearMetricKey || (
              yearMetricSelectionByCard.has(singleTypeKey)
                ? yearMetricSelectionByCard.get(singleTypeKey)
                : null
            );
            const card = total > 0
              ? buildCard(type, year, aggregates, payload.units || { distance: "mi", elevation: "ft" }, {
                metricHeatmapColor: getColors(type)[4],
                cardMetricKey: singleTypeKey,
                initialMetricKey,
                onYearMetricStateChange,
              })
              : buildEmptyYearCard(type, year);
            if (total > 0) {
              nextVisibleYearMetricCardKeys.add(singleTypeKey);
            }
            list.appendChild(buildLabeledCardRow(String(year), card, "year"));
          });
          if (!list.childElementCount) {
            return;
          }
          section.appendChild(list);
          heatmaps.appendChild(section);
        });
      }
    }
    visibleYearMetricCardKeys = nextVisibleYearMetricCardKeys;
    syncSummaryYearMetricSelectionFromCards();

    const showTypeBreakdown = payload.types.length > 0;
    const showActiveDays = Boolean(heatmaps);
    buildSummary(
      payload,
      types,
      years,
      showTypeBreakdown,
      showActiveDays,
      payload.types,
      activeSummaryTypeCards,
      hoverClearedSummaryType,
      (type, wasActiveTypeCard) => {
        hoverClearedSummaryType = wasActiveTypeCard ? type : null;
        toggleTypeFromSummaryCard(type);
        update();
      },
      (type) => {
        if (hoverClearedSummaryType === type) {
          hoverClearedSummaryType = null;
        }
      },
      activeSummaryYearMetricKey,
      hoverClearedSummaryYearMetricKey,
      (metricKey, wasActiveMetricCard) => {
        hoverClearedSummaryYearMetricKey = wasActiveMetricCard ? metricKey : null;
        if (wasActiveMetricCard) {
          activeSummaryYearMetricKey = null;
          clearMetricSelectionAcrossCards(metricKey);
        } else {
          activeSummaryYearMetricKey = metricKey;
          hoverClearedSummaryYearMetricKey = null;
          visibleYearMetricCardKeys.forEach((cardKey) => {
            yearMetricSelectionByCard.set(cardKey, metricKey);
          });
        }
        update();
      },
      (metricKey) => {
        if (hoverClearedSummaryYearMetricKey === metricKey) {
          hoverClearedSummaryYearMetricKey = null;
        }
      },
    );
    requestAnimationFrame(alignStackedStatsToYAxisLabels);
  }

  renderButtons(typeButtons, typeOptions, (value) => {
    toggleType(value);
    update();
  });
  if (typeMenuButton) {
    typeMenuButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = !typeMenu?.classList.contains("open");
      setMenuOpen(typeMenu, typeMenuButton, open);
      setMenuOpen(yearMenu, yearMenuButton, false);
    });
  }
  if (yearMenuButton) {
    yearMenuButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = !yearMenu?.classList.contains("open");
      setMenuOpen(yearMenu, yearMenuButton, open);
      setMenuOpen(typeMenu, typeMenuButton, false);
    });
  }
  if (typeClearButton) {
    typeClearButton.addEventListener("click", () => {
      if (areAllTypesSelected()) return;
      allTypesMode = true;
      selectedTypes.clear();
      update();
    });
  }
  if (yearClearButton) {
    yearClearButton.addEventListener("click", () => {
      if (areAllYearsSelected()) return;
      allYearsMode = true;
      selectedYears.clear();
      update();
    });
  }

  document.addEventListener("pointerdown", (event) => {
    const target = event.target;
    if (typeMenu && !typeMenu.contains(target)) {
      setMenuOpen(typeMenu, typeMenuButton, false);
    }
    if (yearMenu && !yearMenu.contains(target)) {
      setMenuOpen(yearMenu, yearMenuButton, false);
    }
  });
  update();

  if (document.fonts?.ready) {
    document.fonts.ready.then(() => {
      alignStackedStatsToYAxisLabels();
    }).catch(() => {});
  }

  window.addEventListener("resize", () => {
    if (resizeTimer) {
      window.clearTimeout(resizeTimer);
    }
    resizeTimer = window.setTimeout(() => {
      const width = window.innerWidth;
      const isNarrowLayout = window.matchMedia("(max-width: 900px)").matches;
      const widthChanged = Math.abs(width - lastViewportWidth) >= 1;
      const layoutModeChanged = isNarrowLayout !== lastIsNarrowLayout;
      if (!widthChanged && !layoutModeChanged) {
        return;
      }
      lastViewportWidth = width;
      lastIsNarrowLayout = isNarrowLayout;
      update();
    }, 150);
  });

  if (isTouch) {
    document.addEventListener("pointerdown", (event) => {
      if (!tooltip.classList.contains("visible")) return;
      const target = event.target;
      if (tooltip.contains(target)) {
        hideTooltip();
        const active = document.querySelector(".cell.active");
        if (active) active.classList.remove("active");
        return;
      }
      if (!target.classList.contains("cell")) {
        hideTooltip();
        const active = document.querySelector(".cell.active");
        if (active) active.classList.remove("active");
      }
    });

    window.addEventListener(
      "scroll",
      () => {
        hideTooltip();
        const active = document.querySelector(".cell.active");
        if (active) active.classList.remove("active");
      },
      { passive: true },
    );
  }
}

init().catch((error) => {
  console.error(error);
  renderLoadError(error);
});
