const DEFAULT_COLORS = ["#1f2937", "#1f2937", "#1f2937", "#1f2937", "#1f2937"];
const MULTI_TYPE_COLOR = "#b967ff";
const TYPE_ACCENT_OVERRIDES = {
  Workout: "#ff8a5b",
};
const FALLBACK_VAPORWAVE = ["#f15bb5", "#fee440", "#00bbf9", "#00f5d4", "#9b5de5", "#fb5607", "#ffbe0b", "#72efdd"];
const STAT_PLACEHOLDER = "- - -";
const CREATOR_REPO_SLUG = "aspain/git-sweaty";
const TYPE_LABEL_OVERRIDES = {
  HighIntensityIntervalTraining: "HITT",
  Workout: "Other Workout",
};
let TYPE_META = {};
let OTHER_BUCKET = "OtherSports";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WEEK_START_SUNDAY = "sunday";
const WEEK_START_MONDAY = "monday";
const WEEKDAY_LABELS_BY_WEEK_START = Object.freeze({
  [WEEK_START_SUNDAY]: Object.freeze(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]),
  [WEEK_START_MONDAY]: Object.freeze(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
});
const MS_PER_DAY = 1000 * 60 * 60 * 24;
const ACTIVE_DAYS_METRIC_KEY = "active_days";
const DAYS_OFF_METRIC_KEY = "days_off";
const DEFAULT_UNITS = Object.freeze({ distance: "mi", elevation: "ft" });
const UNIT_SYSTEM_TO_UNITS = Object.freeze({
  imperial: Object.freeze({ distance: "mi", elevation: "ft" }),
  metric: Object.freeze({ distance: "km", elevation: "m" }),
});

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
const resetAllButton = document.getElementById("resetAllButton");
const imperialUnitsButton = document.getElementById("imperialUnitsButton");
const metricUnitsButton = document.getElementById("metricUnitsButton");
const typeMenuOptions = document.getElementById("typeMenuOptions");
const yearMenuOptions = document.getElementById("yearMenuOptions");
const heatmaps = document.getElementById("heatmaps");
const tooltip = document.getElementById("tooltip");
const summary = document.getElementById("summary");
const headerMeta = document.getElementById("headerMeta");
const headerLinks = document.querySelector(".header-links");
const repoLink = document.querySelector(".repo-link");
const stravaProfileLink = document.querySelector(".strava-profile-link");
const stravaProfileLabel = stravaProfileLink
  ? stravaProfileLink.querySelector(".strava-profile-label")
  : null;
const footerHostedPrefix = document.getElementById("footerHostedPrefix");
const footerHostedLink = document.getElementById("footerHostedLink");
const footerPoweredLabel = document.getElementById("footerPoweredLabel");
const dashboardTitle = document.getElementById("dashboardTitle");
const isTouch = window.matchMedia("(hover: none) and (pointer: coarse)").matches;
const hasTouchInput = Number(window.navigator?.maxTouchPoints || 0) > 0;
const useTouchInteractions = isTouch || hasTouchInput;
const BREAKPOINTS = Object.freeze({
  NARROW_LAYOUT_MAX: 900,
});
const DESKTOP_MIN_YEAR_HEATMAP_WEEK_COLUMNS = 54;
const DESKTOP_OUTLIER_WEEK_TOLERANCE_COLUMNS = 1;
const FILTER_MENU_DROPDOWN_GAP_PX = 6;
const FILTER_MENU_VIEWPORT_GUTTER_PX = 12;
const FILTER_MENU_MIN_HEIGHT_PX = 180;
const FILTER_MENU_MAX_VIEWPORT_RATIO = 0.75;
let pendingAlignmentFrame = null;
let pendingSummaryTailFrame = null;
let persistentSideStatCardWidth = 0;
let persistentSideStatCardMinHeight = 0;
let pinnedTooltipCell = null;
let touchTooltipInteractionBlockUntil = 0;
let touchTooltipDismissBlockUntil = 0;
let lastTooltipPointerType = "";
let touchTooltipLinkClickSuppressUntil = 0;
let touchTooltipRecentPointerUpCell = null;
let touchTooltipRecentPointerUpUntil = 0;
let touchTooltipRecentPointerUpWasTap = true;
let touchTooltipPointerDownState = null;
let tooltipPositionFrame = null;
let tooltipSettleFrame = null;
let pendingTooltipPoint = null;
let tooltipResizeObserver = null;
const PROFILE_PROVIDER_STRAVA = "strava";
const PROFILE_PROVIDER_GARMIN = "garmin";
const TOUCH_TOOLTIP_TAP_MAX_MOVE_PX = 10;
const TOUCH_TOOLTIP_TAP_MAX_SCROLL_PX = 2;
const TOUCH_TOOLTIP_MAX_EFFECTIVE_ZOOM = 1.2;
const TOUCH_TOOLTIP_MIN_SCALE = 0.5;

function resetPersistentSideStatSizing() {
  persistentSideStatCardWidth = 0;
  persistentSideStatCardMinHeight = 0;
  if (!heatmaps) return;
  heatmaps.style.removeProperty("--side-stat-card-width");
  heatmaps.style.removeProperty("--side-stat-card-min-height");
}

function normalizeUnits(units) {
  const distance = units?.distance === "km" ? "km" : "mi";
  const elevation = units?.elevation === "m" ? "m" : "ft";
  return { distance, elevation };
}

function normalizeWeekStart(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "monday" || normalized === "mon") {
    return WEEK_START_MONDAY;
  }
  return WEEK_START_SUNDAY;
}

function getUnitSystemFromUnits(units) {
  const normalized = normalizeUnits(units);
  return normalized.distance === "km" && normalized.elevation === "m"
    ? "metric"
    : "imperial";
}

function getUnitsForSystem(system) {
  return normalizeUnits(UNIT_SYSTEM_TO_UNITS[system] || DEFAULT_UNITS);
}

function isNarrowLayoutViewport() {
  return window.matchMedia(`(max-width: ${BREAKPOINTS.NARROW_LAYOUT_MAX}px)`).matches;
}

function isDesktopLikeViewport() {
  return !isNarrowLayoutViewport();
}

function requestLayoutAlignment() {
  if (pendingAlignmentFrame !== null) {
    window.cancelAnimationFrame(pendingAlignmentFrame);
  }
  pendingAlignmentFrame = window.requestAnimationFrame(() => {
    pendingAlignmentFrame = null;
    alignStackedStatsToYAxisLabels();
  });
}

function requestSummaryTypeTailCentering() {
  if (pendingSummaryTailFrame !== null) {
    window.cancelAnimationFrame(pendingSummaryTailFrame);
  }
  pendingSummaryTailFrame = window.requestAnimationFrame(() => {
    pendingSummaryTailFrame = null;
    centerSummaryTypeCardTailRow(summary);
  });
}

function schedulePostInteractionAlignment() {
  if (useTouchInteractions) return;
  requestLayoutAlignment();
}

function captureCardScrollOffsets(container) {
  const offsets = new Map();
  if (!container) return offsets;
  container.querySelectorAll(".card[data-scroll-key]").forEach((card) => {
    const key = String(card.dataset.scrollKey || "");
    if (!key) return;
    const scrollLeft = Number(card.scrollLeft || 0);
    if (Number.isFinite(scrollLeft) && scrollLeft > 0) {
      offsets.set(key, scrollLeft);
    }
  });
  return offsets;
}

function restoreCardScrollOffsets(container, offsets) {
  if (!container || !(offsets instanceof Map) || !offsets.size) return;
  container.querySelectorAll(".card[data-scroll-key]").forEach((card) => {
    const key = String(card.dataset.scrollKey || "");
    if (!key || !offsets.has(key)) return;
    const target = Number(offsets.get(key));
    if (!Number.isFinite(target) || target <= 0) return;
    const maxScroll = Math.max(0, card.scrollWidth - card.clientWidth);
    card.scrollLeft = Math.min(target, maxScroll);
  });
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

function parseGitHubRepo(value) {
  if (value && typeof value === "object") {
    const owner = String(value.owner || "").trim();
    const repo = String(value.repo || "").trim().replace(/\.git$/i, "");
    if (owner && repo) {
      return { owner, repo };
    }
    return null;
  }

  let raw = String(value || "").trim();
  if (!raw) return null;

  if (/^git@github\.com:/i.test(raw)) {
    raw = raw.replace(/^git@github\.com:/i, "");
  } else if (/^https?:\/\//i.test(raw)) {
    try {
      const parsed = new URL(raw);
      if (String(parsed.hostname || "").toLowerCase() !== "github.com") {
        return null;
      }
      raw = parsed.pathname || "";
    } catch (_error) {
      return null;
    }
  } else {
    raw = raw.replace(/^(?:https?:\/\/)?(?:www\.)?github\.com\//i, "");
  }

  const pathParts = raw
    .replace(/^\/+|\/+$/g, "")
    .split("/")
    .filter(Boolean);
  if (pathParts.length < 2) return null;

  const owner = String(pathParts[0] || "").trim();
  const repo = String(pathParts[1] || "").trim().replace(/\.git$/i, "");
  if (!owner || !repo) return null;
  return { owner, repo };
}

function resolveGitHubRepo(loc, fallbackRepo) {
  return inferGitHubRepoFromLocation(loc) || parseGitHubRepo(fallbackRepo);
}

function normalizeRepoSlug(value) {
  const parsed = parseGitHubRepo(value);
  if (!parsed) return "";
  return `${parsed.owner}/${parsed.repo}`.toLowerCase();
}

function shouldHideHostedFooter(repoCandidate) {
  return normalizeRepoSlug(repoCandidate) === CREATOR_REPO_SLUG;
}

function footerPoweredLabelText(repoCandidate) {
  return shouldHideHostedFooter(repoCandidate) ? "Powered" : "powered";
}

function isGitHubHostedLocation(loc) {
  const host = String(loc?.hostname || "").toLowerCase();
  return Boolean(host) && (host === "github.com" || host.endsWith(".github.io"));
}

function customDashboardUrlFromLocation(loc) {
  const protocol = String(loc?.protocol || "").toLowerCase();
  const host = String(loc?.host || loc?.hostname || "").trim();
  if (!host) return "";
  const pathname = String(loc?.pathname || "/");
  const search = String(loc?.search || "");
  if (!protocol || !/^https?:$/.test(protocol)) return "";

  try {
    const normalized = new URL(`${protocol}//${host}${pathname}${search}`);
    return normalized.toString();
  } catch (_error) {
    return "";
  }
}

function customDashboardLabelFromUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    const path = String(parsed.pathname || "").replace(/\/+$/, "");
    const suffixPath = path && path !== "/" ? path : "";
    return `${parsed.host}${suffixPath}${parsed.search}`;
  } catch (_error) {
    return "";
  }
}

function resolveHeaderRepoLink(loc, fallbackRepo) {
  const inferred = resolveGitHubRepo(loc, fallbackRepo);
  if (inferred) {
    return {
      href: `https://github.com/${inferred.owner}/${inferred.repo}`,
      text: `${inferred.owner}/${inferred.repo}`,
    };
  }

  if (!isGitHubHostedLocation(loc)) {
    const customUrl = customDashboardUrlFromLocation(loc);
    if (customUrl) {
      const customLabel = customDashboardLabelFromUrl(customUrl) || customUrl;
      return { href: customUrl, text: customLabel };
    }
  }

  return null;
}

function resolveFooterHostedLink(loc, fallbackRepo) {
  const inferred = resolveGitHubRepo(loc, fallbackRepo);
  if (!inferred) return null;
  return {
    href: `https://github.com/${inferred.owner}/${inferred.repo}`,
    text: `${inferred.owner}/${inferred.repo}`,
  };
}

function syncRepoLink(fallbackRepo) {
  if (!repoLink) return;
  const resolved = resolveHeaderRepoLink(
    window.location,
    fallbackRepo || repoLink.getAttribute("href") || repoLink.textContent,
  );
  if (!resolved) return;
  repoLink.href = resolved.href;
  repoLink.textContent = resolved.text;
}

function syncFooterHostedLink(fallbackRepo) {
  if (!footerHostedLink) return;
  const footerFallbackRepo = fallbackRepo
    || repoLink?.getAttribute("href")
    || repoLink?.textContent
    || footerHostedLink.getAttribute("href")
    || footerHostedLink.textContent;
  const resolved = resolveFooterHostedLink(
    window.location,
    footerFallbackRepo,
  );
  if (resolved) {
    footerHostedLink.href = resolved.href;
    footerHostedLink.textContent = resolved.text;
  }
  const footerRepoCandidate = resolved?.text || resolved?.href || footerFallbackRepo;
  if (footerHostedPrefix) {
    footerHostedPrefix.hidden = shouldHideHostedFooter(footerRepoCandidate);
  }
  if (footerPoweredLabel) {
    footerPoweredLabel.textContent = footerPoweredLabelText(footerRepoCandidate);
  }
}

function syncHeaderLinkPlacement() {
  if (!repoLink || !headerLinks) return;
  if (repoLink.parentElement !== headerLinks) {
    headerLinks.insertBefore(repoLink, headerLinks.firstChild);
  }

  if (!stravaProfileLink || !headerMeta) return;
  if (stravaProfileLink.parentElement !== headerMeta) {
    headerMeta.appendChild(stravaProfileLink);
  }
}

function syncProfileLinkNavigationTarget() {
  if (!stravaProfileLink) return;
  if (isDesktopLikeViewport()) {
    stravaProfileLink.target = "_blank";
    stravaProfileLink.rel = "noopener noreferrer";
    return;
  }
  stravaProfileLink.removeAttribute("target");
  stravaProfileLink.removeAttribute("rel");
}

function setProfileProviderIcon(provider) {
  if (!stravaProfileLink) return;
  stravaProfileLink.classList.remove("profile-provider-strava", "profile-provider-garmin");
  if (provider === PROFILE_PROVIDER_GARMIN) {
    stravaProfileLink.classList.add("profile-provider-garmin");
    return;
  }
  stravaProfileLink.classList.add("profile-provider-strava");
}

function parseStravaProfileUrl(value) {
  let raw = String(value || "").trim();
  if (!raw) return null;
  if (!/^https?:\/\//i.test(raw)) {
    raw = `https://${raw.replace(/^\/+/, "")}`;
  }

  let parsed;
  try {
    parsed = new URL(raw);
  } catch (_error) {
    return null;
  }

  const host = String(parsed.hostname || "").toLowerCase();
  const isStravaHost = host === "strava.com" || host.endsWith(".strava.com");
  const isGarminHost = host === "connect.garmin.com" || host.endsWith(".connect.garmin.com");
  if (!isStravaHost && !isGarminHost) {
    return null;
  }

  const path = String(parsed.pathname || "").trim().replace(/\/+$/, "");
  if (!path || path === "/") {
    return null;
  }

  let normalizedPath = path;
  if (isGarminHost) {
    const garminMatch = path.match(/^\/(?:modern\/)?profile\/([^/]+)(?:\/.*)?$/i);
    if (!garminMatch) {
      return null;
    }
    normalizedPath = `/modern/profile/${garminMatch[1]}`;
  }

  return {
    href: `${parsed.protocol}//${parsed.host}${normalizedPath}${parsed.search}`,
    label: isGarminHost ? "Garmin" : "Strava",
  };
}

function parseStravaActivityUrl(value) {
  let raw = String(value || "").trim();
  if (!raw) return null;
  if (!/^https?:\/\//i.test(raw)) {
    raw = `https://${raw.replace(/^\/+/, "")}`;
  }

  let parsed;
  try {
    parsed = new URL(raw);
  } catch (_error) {
    return null;
  }

  const host = String(parsed.hostname || "").toLowerCase();
  const isStravaHost = host === "strava.com" || host.endsWith(".strava.com");
  const isGarminHost = host === "connect.garmin.com" || host.endsWith(".connect.garmin.com");
  if (!isStravaHost && !isGarminHost) {
    return null;
  }

  const path = String(parsed.pathname || "").trim().replace(/\/+$/, "");
  if (isStravaHost && !/^\/activities\/[^/]+$/i.test(path)) {
    return null;
  }
  if (isGarminHost && !/^\/(?:modern\/)?activity\/[^/]+$/i.test(path)) {
    return null;
  }

  return {
    href: `${parsed.protocol}//${parsed.host}${path}${parsed.search}`,
  };
}

function syncStravaProfileLink(profileUrl, source) {
  if (!stravaProfileLink) return;
  const parsed = parseStravaProfileUrl(profileUrl);
  if (!parsed) {
    stravaProfileLink.hidden = true;
    setProfileProviderIcon(PROFILE_PROVIDER_STRAVA);
    syncProfileLinkNavigationTarget();
    syncHeaderLinkPlacement();
    return;
  }
  stravaProfileLink.href = parsed.href;
  const providerLabel = parsed.label || providerDisplayName(source) || "Profile";
  const provider = providerLabel === "Garmin"
    ? PROFILE_PROVIDER_GARMIN
    : PROFILE_PROVIDER_STRAVA;
  setProfileProviderIcon(provider);
  if (stravaProfileLabel) {
    stravaProfileLabel.textContent = providerLabel;
  } else {
    stravaProfileLink.textContent = providerLabel;
  }
  stravaProfileLink.hidden = false;
  syncProfileLinkNavigationTarget();
  syncHeaderLinkPlacement();
}

function providerDisplayName(source) {
  const normalized = String(source || "").trim().toLowerCase();
  if (normalized === "garmin") return "Garmin";
  if (normalized === "strava") return "Strava";
  return "";
}

function payloadRepoCandidate(payload) {
  return payload?.repo
    || payload?.repo_slug
    || payload?.repo_url
    || payload?.repository
    || "";
}

function payloadProfileUrl(payload) {
  return payload?.profile_url
    || payload?.profileUrl
    || payload?.provider_profile_url
    || payload?.garmin_profile_url
    || payload?.garminProfileUrl
    || payload?.garmin_profile
    || payload?.strava_profile_url
    || payload?.stravaProfileUrl
    || payload?.strava_profile
    || "";
}

function payloadSource(payload) {
  return payload?.source || payload?.provider || "";
}

function cloneSelectionState(allMode, selectedValues) {
  return {
    allMode: Boolean(allMode),
    selectedValues: new Set(selectedValues),
  };
}

function reduceTopButtonSelection({
  rawValue,
  allMode,
  selectedValues,
  allValues,
  normalizeValue = (value) => value,
}) {
  if (rawValue === "all") {
    if (!allValues.length) {
      return { allMode: true, selectedValues: new Set() };
    }
    const hasExplicitAllSelection = !allMode
      && selectedValues.size === allValues.length
      && allValues.every((value) => selectedValues.has(value));
    if (hasExplicitAllSelection) {
      return { allMode: true, selectedValues: new Set() };
    }
    return { allMode: false, selectedValues: new Set(allValues) };
  }
  const normalizedValue = normalizeValue(rawValue);
  if (!allValues.includes(normalizedValue)) {
    return { allMode, selectedValues };
  }
  if (allMode) {
    return {
      allMode: false,
      selectedValues: new Set([normalizedValue]),
    };
  }
  const nextSelectedValues = new Set(selectedValues);
  if (nextSelectedValues.has(normalizedValue)) {
    nextSelectedValues.delete(normalizedValue);
    if (!nextSelectedValues.size) {
      return { allMode: true, selectedValues: new Set() };
    }
    return { allMode: false, selectedValues: nextSelectedValues };
  }
  nextSelectedValues.add(normalizedValue);
  return { allMode: false, selectedValues: nextSelectedValues };
}

function reduceMenuSelection({
  rawValue,
  allMode,
  selectedValues,
  allValues,
  normalizeValue = (value) => value,
  allowToggleOffAll = false,
}) {
  if (rawValue === "all") {
    const hasExplicitAllSelection = !allMode
      && allValues.length > 0
      && selectedValues.size === allValues.length
      && allValues.every((value) => selectedValues.has(value));
    if (allowToggleOffAll && (allMode || hasExplicitAllSelection)) {
      return { allMode: false, selectedValues: new Set() };
    }
    return { allMode: true, selectedValues: new Set() };
  }
  const normalizedValue = normalizeValue(rawValue);
  if (!allValues.includes(normalizedValue)) {
    return { allMode, selectedValues };
  }
  if (allMode) {
    return {
      allMode: false,
      selectedValues: new Set(allValues.filter((value) => value !== normalizedValue)),
    };
  }
  const nextSelectedValues = new Set(selectedValues);
  if (nextSelectedValues.has(normalizedValue)) {
    nextSelectedValues.delete(normalizedValue);
    return { allMode: false, selectedValues: nextSelectedValues };
  }
  nextSelectedValues.add(normalizedValue);
  return { allMode: false, selectedValues: nextSelectedValues };
}

function deriveActiveSummaryYearMetricKey({
  visibleYears,
  selectedMetricByYear,
  filterableMetricsByYear,
}) {
  const selectedMetrics = new Set();
  for (const year of visibleYears) {
    const selectedMetric = selectedMetricByYear.get(year);
    const filterableSet = filterableMetricsByYear.get(year) || new Set();
    if (selectedMetric && filterableSet.has(selectedMetric)) {
      selectedMetrics.add(selectedMetric);
    }
  }
  if (selectedMetrics.size !== 1) {
    return null;
  }
  const [candidateMetric] = Array.from(selectedMetrics);
  let hasEligibleYear = false;
  for (const year of visibleYears) {
    const filterableSet = filterableMetricsByYear.get(year) || new Set();
    if (!filterableSet.has(candidateMetric)) continue;
    hasEligibleYear = true;
    if (selectedMetricByYear.get(year) !== candidateMetric) {
      return null;
    }
  }
  return hasEligibleYear ? candidateMetric : null;
}

function toStringSet(values) {
  const result = new Set();
  (Array.isArray(values) ? values : []).forEach((value) => {
    if (typeof value === "string") {
      result.add(value);
    }
  });
  return result;
}

function trackYearMetricAvailability(year, visibleYearsSet) {
  visibleYearsSet.add(Number(year));
}

function pruneYearMetricSelectionsByFilterability(selectionByYear, filterableMetricsByYearMap) {
  Array.from(selectionByYear.keys()).forEach((year) => {
    const filterableSet = filterableMetricsByYearMap.get(year);
    const selectedMetricKey = selectionByYear.get(year) || null;
    if (!filterableSet || (selectedMetricKey && !filterableSet.has(selectedMetricKey))) {
      selectionByYear.delete(year);
    }
  });
}

function selectedTypesListForState(state, allTypes) {
  if (!state || state.allMode) {
    return allTypes.slice();
  }
  return allTypes.filter((type) => state.selectedValues.has(type));
}

function selectedYearsListForState(state, visibleYears) {
  if (!state || state.allMode) {
    return visibleYears.slice();
  }
  return visibleYears.filter((year) => state.selectedValues.has(Number(year)));
}

function updateButtonState(container, selectedValues, isAllSelected, allValues, normalizeValue) {
  if (!container) return;
  const hasExplicitAllSelection = allValues.length > 0
    && !isAllSelected
    && selectedValues.size === allValues.length
    && allValues.every((value) => selectedValues.has(value));
  container.querySelectorAll(".filter-button").forEach((button) => {
    const rawValue = String(button.dataset.value || "");
    const value = normalizeValue ? normalizeValue(rawValue) : rawValue;
    const isActive = rawValue === "all"
      ? hasExplicitAllSelection
      : (!isAllSelected && selectedValues.has(value));
    button.classList.toggle("active", isActive);
  });
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
  if (fallbackText && fallbackText !== text) {
    labelEl.textContent = fallbackText;
    return;
  }
  labelEl.textContent = text;
}

function setMenuOpenState(menuEl, buttonEl, isOpen) {
  if (!menuEl) return;
  menuEl.classList.toggle("open", isOpen);
  if (buttonEl) {
    buttonEl.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }
}

function ensureFilterMenuList(container) {
  if (!container) return null;
  let list = container.querySelector(".filter-menu-options-list");
  if (list) return list;
  list = document.createElement("div");
  list.className = "filter-menu-options-list";
  container.appendChild(list);
  return list;
}

function resetFilterMenuScroll(container) {
  if (!container) return;
  const list = container.querySelector(".filter-menu-options-list");
  if (list) {
    list.scrollTop = 0;
    return;
  }
  container.scrollTop = 0;
}

function getFilterMenuMaxHeightPx(triggerButtonEl) {
  if (!triggerButtonEl) return null;
  const viewportHeight = Number(window.innerHeight || document.documentElement?.clientHeight || 0);
  if (!viewportHeight) return null;
  const rect = triggerButtonEl.getBoundingClientRect();
  const spaceBelow = Math.max(
    0,
    viewportHeight - rect.bottom - FILTER_MENU_DROPDOWN_GAP_PX - FILTER_MENU_VIEWPORT_GUTTER_PX,
  );
  const viewportCap = Math.floor(viewportHeight * FILTER_MENU_MAX_VIEWPORT_RATIO);
  const boundedCap = Math.min(spaceBelow, viewportCap);
  const minimum = Math.min(FILTER_MENU_MIN_HEIGHT_PX, spaceBelow);
  return Math.max(minimum, boundedCap);
}

function applyFilterMenuMaxHeight(menuEl, triggerButtonEl, optionsEl) {
  if (!menuEl || !optionsEl || !menuEl.classList.contains("open")) {
    if (optionsEl) {
      optionsEl.style.removeProperty("--filter-menu-max-height");
    }
    return;
  }
  const maxHeight = getFilterMenuMaxHeightPx(triggerButtonEl);
  if (Number.isFinite(maxHeight) && maxHeight > 0) {
    optionsEl.style.setProperty("--filter-menu-max-height", `${Math.round(maxHeight)}px`);
    return;
  }
  optionsEl.style.removeProperty("--filter-menu-max-height");
}

function syncOpenFilterMenuMaxHeights() {
  applyFilterMenuMaxHeight(typeMenu, typeMenuButton, typeMenuOptions);
  applyFilterMenuMaxHeight(yearMenu, yearMenuButton, yearMenuOptions);
}

function renderFilterButtons(container, options, onSelect) {
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

function renderFilterMenuOptions(
  container,
  options,
  selectedValues,
  isAllSelected,
  onSelect,
  normalizeValue,
) {
  if (!container) return;
  container.innerHTML = "";
  const list = ensureFilterMenuList(container);
  if (!list) return;
  const normalizedOptionValues = options
    .filter((option) => String(option.value) !== "all")
    .map((option) => {
      const rawValue = String(option.value);
      return normalizeValue ? normalizeValue(rawValue) : rawValue;
    });
  const hasExplicitAllSelection = !isAllSelected
    && normalizedOptionValues.length > 0
    && normalizedOptionValues.every((value) => selectedValues.has(value));
  const allOptionSelected = isAllSelected || hasExplicitAllSelection;
  options.forEach((option) => {
    const rawValue = String(option.value);
    const normalized = normalizeValue ? normalizeValue(rawValue) : rawValue;
    const isActive = rawValue === "all"
      ? allOptionSelected
      : (!isAllSelected && selectedValues.has(normalized));
    const isChecked = rawValue === "all"
      ? allOptionSelected
      : (isAllSelected || selectedValues.has(normalized));

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
    list.appendChild(row);
  });
}

function renderFilterMenuDoneButton(container, onDone) {
  if (!container) return;
  const footer = document.createElement("div");
  footer.className = "filter-menu-footer";
  const done = document.createElement("button");
  done.type = "button";
  done.className = "filter-menu-done";
  done.textContent = "Done";
  done.addEventListener("pointerdown", (event) => {
    event.stopPropagation();
  });
  done.addEventListener("click", () => onDone());
  footer.appendChild(done);
  container.appendChild(footer);
}

function syncFilterControlState({
  typeButtons,
  yearButtons,
  selectedTypes,
  selectedYears,
  allTypeValues,
  allYearValues,
  allTypesSelected,
  allYearsSelected,
  typeMenuTypes,
  yearMenuYears,
  typeMenuSelection,
  yearMenuSelection,
  typeMenuLabel,
  yearMenuLabel,
  typeClearButton,
  yearClearButton,
  keepTypeMenuOpen,
  keepYearMenuOpen,
  typeMenu,
  yearMenu,
  typeMenuButton,
  yearMenuButton,
}) {
  updateButtonState(typeButtons, selectedTypes, allTypesSelected, allTypeValues);
  updateButtonState(yearButtons, selectedYears, allYearsSelected, allYearValues, (v) => Number(v));
  const typeMenuText = getTypeMenuText(
    typeMenuTypes,
    typeMenuSelection.allMode || typeMenuTypes.length === allTypeValues.length,
  );
  const yearMenuText = getYearMenuText(
    yearMenuYears,
    yearMenuSelection.allMode || yearMenuYears.length === allYearValues.length,
  );
  setMenuLabel(
    typeMenuLabel,
    typeMenuText,
    !typeMenuSelection.allMode
    && typeMenuTypes.length > 1
    && typeMenuTypes.length < allTypeValues.length
      ? "Multiple Activities Selected"
      : "",
  );
  setMenuLabel(
    yearMenuLabel,
    yearMenuText,
    !yearMenuSelection.allMode
    && yearMenuYears.length > 1
    && yearMenuYears.length < allYearValues.length
      ? "Multiple Years Selected"
      : "",
  );
  if (typeClearButton) {
    if (allTypesSelected) {
      typeClearButton.textContent = "Select All";
      typeClearButton.disabled = allTypeValues.length === 0;
    } else {
      typeClearButton.textContent = "Clear";
      typeClearButton.disabled = false;
    }
  }
  if (yearClearButton) {
    yearClearButton.disabled = allYearsSelected;
  }
  if (keepTypeMenuOpen) {
    setMenuOpenState(typeMenu, typeMenuButton, true);
  }
  if (keepYearMenuOpen) {
    setMenuOpenState(yearMenu, yearMenuButton, true);
  }
}

function setDashboardTitle(source) {
  const provider = providerDisplayName(source);
  const title = provider ? `${provider} Activity Heatmaps` : "Activity Heatmaps";
  if (dashboardTitle) {
    dashboardTitle.textContent = title;
  }
  document.title = title;
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

function getYearCardWeekColumnCount(card) {
  const heatmapArea = card?.querySelector(".heatmap-area");
  if (!heatmapArea) return 0;
  const rawValue = Number(heatmapArea.dataset.weekColumns || "");
  return Number.isFinite(rawValue) && rawValue > 0 ? rawValue : 0;
}

function getYearHeatmapWeekStep(referenceElement) {
  if (!referenceElement) return 0;
  const cell = readCssVar("--cell", 12, referenceElement);
  const gap = readCssVar("--gap", 2, referenceElement);
  const step = cell + gap;
  return Number.isFinite(step) && step > 0 ? step : 0;
}

function getDominantYearRailWidth(widths) {
  const finiteWidths = widths.filter((width) => Number.isFinite(width) && width > 0);
  if (!finiteWidths.length) return 0;
  const buckets = new Map();
  finiteWidths.forEach((width) => {
    const bucket = Math.round(width);
    const current = buckets.get(bucket) || { count: 0, minWidth: width };
    current.count += 1;
    current.minWidth = Math.min(current.minWidth, width);
    buckets.set(bucket, current);
  });
  let bestBucket = null;
  let bestCount = -1;
  let bestBucketWidth = Infinity;
  buckets.forEach((entry, bucket) => {
    if (entry.count > bestCount || (entry.count === bestCount && bucket < bestBucketWidth)) {
      bestCount = entry.count;
      bestBucket = entry;
      bestBucketWidth = bucket;
    }
  });
  return bestBucket ? bestBucket.minWidth : 0;
}

function alignFrequencyMetricChipsToSecondGraphAxis(frequencyCard, title, metricChipRow) {
  metricChipRow.style.removeProperty("margin-left");
  const secondGraphYearLabel = frequencyCard.querySelector(
    ".more-stats-grid > .more-stats-col[data-chip-axis-anchor=\"true\"] .axis-day-col .axis-y-label",
  );
  if (!secondGraphYearLabel) return;

  const titleRect = title.getBoundingClientRect();
  const chipRect = metricChipRow.getBoundingClientRect();
  const yearLabelRect = secondGraphYearLabel.getBoundingClientRect();
  const currentLeft = chipRect.left - titleRect.left;
  const targetLeft = yearLabelRect.left - titleRect.left;

  if (!Number.isFinite(currentLeft) || !Number.isFinite(targetLeft)) return;
  const extraOffset = targetLeft - currentLeft;
  if (extraOffset > 0.5) {
    metricChipRow.style.setProperty("margin-left", `${extraOffset}px`);
  }
}

function resetCardLayoutState() {
  if (!heatmaps) return;
  heatmaps.querySelectorAll(".more-stats").forEach((card) => {
    card.classList.remove("more-stats-stacked");
    card.style.removeProperty("--card-graph-rail-width");
    card.style.removeProperty("--frequency-graph-gap");
    card.style.removeProperty("--frequency-grid-pad-right");
    const metricChipRow = card.querySelector(".more-stats-metric-chips");
    const facts = card.querySelector(".more-stats-facts.side-stats-column");
    if (metricChipRow && facts && facts.firstElementChild !== metricChipRow) {
      metricChipRow.style.removeProperty("margin-left");
      facts.insertBefore(metricChipRow, facts.firstChild);
    }
  });
  heatmaps.querySelectorAll(".year-card").forEach((card) => {
    card.classList.remove("year-card-stacked");
    card.style.removeProperty("--card-graph-rail-width");
  });
}

function normalizeSideStatCardSize() {
  if (!heatmaps) return;
  const configuredMinWidth = readCssVar("--side-stat-card-width-min", 0, heatmaps);
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
    if (persistentSideStatCardWidth > 0) {
      heatmaps.style.setProperty("--side-stat-card-width", `${persistentSideStatCardWidth}px`);
    } else if (configuredMinWidth > 0) {
      heatmaps.style.setProperty("--side-stat-card-width", `${configuredMinWidth}px`);
    } else {
      heatmaps.style.removeProperty("--side-stat-card-width");
    }
    if (persistentSideStatCardMinHeight > 0) {
      heatmaps.style.setProperty("--side-stat-card-min-height", `${persistentSideStatCardMinHeight}px`);
    } else {
      heatmaps.style.removeProperty("--side-stat-card-min-height");
    }
    return;
  }

  const maxWidth = cards.reduce((acc, card) => Math.max(acc, Math.ceil(getElementBoxWidth(card))), 0);
  const maxHeight = cards.reduce((acc, card) => Math.max(acc, Math.ceil(card.getBoundingClientRect().height || 0)), 0);
  const normalizedWidth = Math.max(maxWidth, Math.ceil(configuredMinWidth));
  persistentSideStatCardWidth = Math.max(persistentSideStatCardWidth, normalizedWidth);
  persistentSideStatCardMinHeight = Math.max(persistentSideStatCardMinHeight, maxHeight);

  if (persistentSideStatCardWidth > 0) {
    heatmaps.style.setProperty("--side-stat-card-width", `${persistentSideStatCardWidth}px`);
  }
  if (persistentSideStatCardMinHeight > 0) {
    heatmaps.style.setProperty("--side-stat-card-min-height", `${persistentSideStatCardMinHeight}px`);
  }
}

function buildSectionLayoutPlan(list) {
  const frequencyCard = list.querySelector(".labeled-card-row-frequency .more-stats");
  const yearCards = Array.from(list.querySelectorAll(".labeled-card-row-year .year-card"));
  if (!frequencyCard && !yearCards.length) return null;

  const desktopLike = isDesktopLikeViewport();
  const yearGraphWidths = yearCards
    .map((card) => getElementBoxWidth(card.querySelector(".heatmap-area")))
    .filter((width) => width > 0);
  const maxYearWeekColumns = yearCards.reduce(
    (maxColumns, card) => Math.max(maxColumns, getYearCardWeekColumnCount(card)),
    0,
  );

  let graphRailWidth = yearGraphWidths.length ? Math.max(...yearGraphWidths) : 0;
  const dominantYearRailWidth = getDominantYearRailWidth(yearGraphWidths);
  let frequencyGap = null;
  let frequencyPadRight = null;
  let desktopCalendarOverflowAllowance = 0;
  const weekStepReference = yearCards[0]?.querySelector(".heatmap-area") || frequencyCard || list;
  const weekStep = getYearHeatmapWeekStep(weekStepReference);

  if (
    desktopLike
    && graphRailWidth > 0
    && maxYearWeekColumns > 0
    && weekStep > 0
  ) {
    const missingWeeks = Math.max(0, DESKTOP_MIN_YEAR_HEATMAP_WEEK_COLUMNS - maxYearWeekColumns);
    if (missingWeeks > 0) {
      const baselineExpansion = missingWeeks * weekStep;
      desktopCalendarOverflowAllowance += baselineExpansion;
    }

    if (maxYearWeekColumns >= DESKTOP_MIN_YEAR_HEATMAP_WEEK_COLUMNS) {
      desktopCalendarOverflowAllowance += DESKTOP_OUTLIER_WEEK_TOLERANCE_COLUMNS * weekStep;
    }
  }

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
      const frequencyRailWidth = (
        dominantYearRailWidth > 0
        && dominantYearRailWidth < graphRailWidth
      )
        ? dominantYearRailWidth
        : graphRailWidth;
      const targetRailWidth = Math.max(totalFrequencyGraphWidth, frequencyRailWidth);
      const totalGap = Math.max(0, targetRailWidth - totalFrequencyGraphWidth);
      if (graphCount > 1) {
        const gapCount = graphCount - 1;
        const desiredTrailingPad = readCssVar("--year-grid-pad-right", 0, frequencyCard);
        const trailingPad = Math.max(0, Math.min(totalGap, desiredTrailingPad));
        const distributableGap = Math.max(0, totalGap - trailingPad);
        // Reserve trailing right gutter first so the third graph rail stays aligned with yearly rails.
        frequencyGap = distributableGap / gapCount;
        frequencyPadRight = trailingPad;
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
      ? (readCssVar("--stack-overflow-tolerance-desktop", 0, card) + desktopCalendarOverflowAllowance)
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
    const metricChipRow = frequencyCard.querySelector(".more-stats-metric-chips");
    const title = frequencyCard.querySelector(":scope > .labeled-card-title");
    const facts = frequencyCard.querySelector(".more-stats-facts.side-stats-column");
    if (metricChipRow && title && facts) {
      const keepChipsWithTitle = shouldStackSection;
      if (keepChipsWithTitle) {
        title.appendChild(metricChipRow);
        alignFrequencyMetricChipsToSecondGraphAxis(frequencyCard, title, metricChipRow);
      } else if (facts.firstElementChild !== metricChipRow) {
        metricChipRow.style.removeProperty("margin-left");
        facts.insertBefore(metricChipRow, facts.firstChild);
      }
    }
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

function getLocalTodayDateKey(referenceDate = new Date()) {
  return formatLocalDateKey(referenceDate);
}

function isDateKeyElapsed(dateKey, todayDateKey = getLocalTodayDateKey()) {
  const normalizedDateKey = String(dateKey || "");
  return Boolean(normalizedDateKey) && normalizedDateKey <= todayDateKey;
}

function getElapsedDayCountForYear(year, referenceDate = new Date()) {
  const normalizedYear = Number(year);
  if (!Number.isFinite(normalizedYear)) return 0;
  const currentYear = referenceDate.getFullYear();
  if (normalizedYear > currentYear) return 0;
  if (normalizedYear < currentYear) {
    const yearStart = Date.UTC(normalizedYear, 0, 1);
    const nextYearStart = Date.UTC(normalizedYear + 1, 0, 1);
    return Math.max(0, Math.round((nextYearStart - yearStart) / MS_PER_DAY));
  }
  const currentDayUtc = Date.UTC(
    referenceDate.getFullYear(),
    referenceDate.getMonth(),
    referenceDate.getDate(),
  );
  const yearStartUtc = Date.UTC(normalizedYear, 0, 1);
  return Math.max(0, Math.floor((currentDayUtc - yearStartUtc) / MS_PER_DAY) + 1);
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

function utcDateFromParts(year, monthIndex, dayOfMonth) {
  return new Date(Date.UTC(year, monthIndex, dayOfMonth));
}

function formatUtcDateKey(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function utcDayNumber(date) {
  return Math.floor(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) / MS_PER_DAY);
}

function weekdayRowFromStart(utcDayIndex, weekStart) {
  if (normalizeWeekStart(weekStart) === WEEK_START_MONDAY) {
    return (utcDayIndex + 6) % 7;
  }
  return utcDayIndex;
}

function weekStartOnOrBeforeUtc(date, weekStart) {
  const offset = weekdayRowFromStart(date.getUTCDay(), weekStart);
  const result = new Date(date.getTime());
  result.setUTCDate(result.getUTCDate() - offset);
  return result;
}

function weekEndOnOrAfterUtc(date, weekStart) {
  const offset = weekdayRowFromStart(date.getUTCDay(), weekStart);
  const result = new Date(date.getTime());
  result.setUTCDate(result.getUTCDate() + (6 - offset));
  return result;
}

function weekIndexFromWeekStartUtc(date, start) {
  return Math.floor((utcDayNumber(date) - utcDayNumber(start)) / 7);
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

function getViewportMetrics() {
  const viewport = useTouchInteractions ? window.visualViewport : null;
  if (!viewport) {
    return {
      offsetLeft: 0,
      offsetTop: 0,
      width: window.innerWidth,
      height: window.innerHeight,
    };
  }
  return {
    offsetLeft: Number.isFinite(viewport.offsetLeft) ? viewport.offsetLeft : 0,
    offsetTop: Number.isFinite(viewport.offsetTop) ? viewport.offsetTop : 0,
    width: Number.isFinite(viewport.width) ? viewport.width : window.innerWidth,
    height: Number.isFinite(viewport.height) ? viewport.height : window.innerHeight,
  };
}

function tooltipViewportAnchorOffset(viewport) {
  if (!useTouchInteractions) {
    return { x: 0, y: 0 };
  }
  return {
    x: Number.isFinite(viewport?.offsetLeft) ? viewport.offsetLeft : 0,
    y: Number.isFinite(viewport?.offsetTop) ? viewport.offsetTop : 0,
  };
}

function pickTooltipCoordinate(preferred, alternate, min, max) {
  const preferredFits = preferred >= min && preferred <= max;
  if (preferredFits) {
    return preferred;
  }
  const alternateFits = alternate >= min && alternate <= max;
  if (alternateFits) {
    return alternate;
  }
  const clampedPreferred = clamp(preferred, min, max);
  const clampedAlternate = clamp(alternate, min, max);
  return Math.abs(clampedPreferred - preferred) <= Math.abs(clampedAlternate - alternate)
    ? clampedPreferred
    : clampedAlternate;
}

function getTouchTooltipScale() {
  if (!useTouchInteractions) {
    return 1;
  }
  const viewport = window.visualViewport;
  const scale = Number(viewport?.scale);
  if (!Number.isFinite(scale) || scale <= 0) {
    return 1;
  }
  const desiredScale = TOUCH_TOOLTIP_MAX_EFFECTIVE_ZOOM / scale;
  return clamp(desiredScale, TOUCH_TOOLTIP_MIN_SCALE, 1);
}

function updateDesktopTooltipBounds() {
  if (useTouchInteractions) return;
  const padding = 12;
  const viewport = getViewportMetrics();
  const maxWidth = Math.max(200, Math.floor(viewport.width - (padding * 2)));
  const maxHeight = Math.max(120, Math.floor(viewport.height - (padding * 2)));
  tooltip.style.maxWidth = `${maxWidth}px`;
  tooltip.style.maxHeight = `${maxHeight}px`;
  tooltip.style.overflowY = "auto";
  tooltip.style.overflowX = "hidden";
}

function positionTooltip(x, y) {
  const padding = 12;
  const rect = tooltip.getBoundingClientRect();
  const rectWidth = Number.isFinite(rect.width) && rect.width > 0
    ? rect.width
    : Math.max(0, Number(tooltip.offsetWidth || 0));
  const rectHeight = Number.isFinite(rect.height) && rect.height > 0
    ? rect.height
    : Math.max(0, Number(tooltip.offsetHeight || 0));
  const viewport = getViewportMetrics();
  const anchorOffset = tooltipViewportAnchorOffset(viewport);
  const anchorX = x + anchorOffset.x;
  const anchorY = y + anchorOffset.y;
  const minX = anchorOffset.x + padding;
  const minY = anchorOffset.y + padding;
  const maxX = Math.max(minX, anchorOffset.x + viewport.width - rectWidth - padding);
  const maxY = Math.max(minY, anchorOffset.y + viewport.height - rectHeight - padding);
  const preferredLeft = anchorX + padding;
  const alternateLeft = anchorX - rectWidth - padding;
  const left = pickTooltipCoordinate(preferredLeft, alternateLeft, minX, maxX);
  const preferredTop = useTouchInteractions
    ? (anchorY - rectHeight - padding)
    : (anchorY + padding);
  const alternateTop = useTouchInteractions
    ? (anchorY + padding)
    : (anchorY - rectHeight - padding);
  const top = pickTooltipCoordinate(preferredTop, alternateTop, minY, maxY);
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
  tooltip.style.bottom = "auto";
  const finalRect = tooltip.getBoundingClientRect();
  const finalMaxX = Math.max(minX, anchorOffset.x + viewport.width - finalRect.width - padding);
  const finalMaxY = Math.max(minY, anchorOffset.y + viewport.height - finalRect.height - padding);
  const finalPreferredLeft = anchorX + padding;
  const finalAlternateLeft = anchorX - finalRect.width - padding;
  const adjustedLeft = pickTooltipCoordinate(finalPreferredLeft, finalAlternateLeft, minX, finalMaxX);
  const finalPreferredTop = useTouchInteractions
    ? (anchorY - finalRect.height - padding)
    : (anchorY + padding);
  const finalAlternateTop = useTouchInteractions
    ? (anchorY + padding)
    : (anchorY - finalRect.height - padding);
  const adjustedTop = pickTooltipCoordinate(finalPreferredTop, finalAlternateTop, minY, finalMaxY);
  if (Math.abs(adjustedLeft - finalRect.left) > 0.5) {
    tooltip.style.left = `${adjustedLeft}px`;
  }
  if (Math.abs(adjustedTop - finalRect.top) > 0.5) {
    tooltip.style.top = `${adjustedTop}px`;
  }
  if (!useTouchInteractions && window.visualViewport) {
    const visualViewport = window.visualViewport;
    const vvLeft = Number.isFinite(visualViewport.offsetLeft) ? visualViewport.offsetLeft : 0;
    const vvTop = Number.isFinite(visualViewport.offsetTop) ? visualViewport.offsetTop : 0;
    const vvWidth = Number.isFinite(visualViewport.width) ? visualViewport.width : viewport.width;
    const vvHeight = Number.isFinite(visualViewport.height) ? visualViewport.height : viewport.height;
    const afterClampRect = tooltip.getBoundingClientRect();
    const vvMinX = vvLeft + padding;
    const vvMinY = vvTop + padding;
    const vvMaxX = Math.max(vvMinX, vvLeft + vvWidth - afterClampRect.width - padding);
    const vvMaxY = Math.max(vvMinY, vvTop + vvHeight - afterClampRect.height - padding);
    const vvPreferredLeft = anchorX + padding;
    const vvAlternateLeft = anchorX - afterClampRect.width - padding;
    const vvAdjustedLeft = pickTooltipCoordinate(vvPreferredLeft, vvAlternateLeft, vvMinX, vvMaxX);
    const vvPreferredTop = anchorY + padding;
    const vvAlternateTop = anchorY - afterClampRect.height - padding;
    const vvAdjustedTop = pickTooltipCoordinate(vvPreferredTop, vvAlternateTop, vvMinY, vvMaxY);
    if (Math.abs(vvAdjustedLeft - afterClampRect.left) > 0.5) {
      tooltip.style.left = `${vvAdjustedLeft}px`;
    }
    if (Math.abs(vvAdjustedTop - afterClampRect.top) > 0.5) {
      tooltip.style.top = `${vvAdjustedTop}px`;
    }
  }
}

function updateTouchTooltipWrapMode() {
  if (!useTouchInteractions) return;
  const padding = 12;
  const viewport = getViewportMetrics();
  const anchorOffset = tooltipViewportAnchorOffset(viewport);
  const touchTooltipScale = getTouchTooltipScale();
  const effectiveScale = touchTooltipScale > 0 ? touchTooltipScale : 1;
  const availableWidth = Math.max(0, viewport.width - (padding * 2));
  const availableHeight = Math.max(0, viewport.height - (padding * 2));
  const scaledAvailableWidth = Math.max(0, Math.floor(availableWidth / effectiveScale));
  const scaledAvailableHeight = Math.max(0, Math.floor(availableHeight / effectiveScale));
  if (availableHeight > 0) {
    const preferredMaxHeight = Math.max(120, Math.floor((viewport.height * 0.7) / effectiveScale));
    const maxHeight = Math.min(scaledAvailableHeight, preferredMaxHeight);
    tooltip.style.maxHeight = `${maxHeight}px`;
    tooltip.style.overflowY = "auto";
    tooltip.style.removeProperty("overflow-x");
  } else {
    tooltip.style.removeProperty("max-height");
    tooltip.style.removeProperty("overflow-y");
    tooltip.style.removeProperty("overflow-x");
  }
  if (availableWidth <= 0) {
    tooltip.style.removeProperty("max-width");
    tooltip.classList.remove("nowrap");
    return;
  }
  const maxWidth = scaledAvailableWidth;
  tooltip.style.maxWidth = `${maxWidth}px`;

  tooltip.classList.remove("nowrap");
  tooltip.style.left = `${anchorOffset.x + padding}px`;
  tooltip.style.top = `${anchorOffset.y + padding}px`;
  tooltip.style.bottom = "auto";
  tooltip.style.right = "auto";

  tooltip.classList.add("nowrap");
  const nowrapWidth = Math.max(0, Number(tooltip.scrollWidth || 0));
  if (!nowrapWidth || nowrapWidth > maxWidth) {
    tooltip.classList.remove("nowrap");
    tooltip.style.overflowX = "hidden";
  } else {
    tooltip.style.removeProperty("overflow-x");
  }
}

function normalizeTooltipHref(value) {
  const parsed = parseStravaActivityUrl(value);
  return parsed?.href || "";
}

function normalizeTooltipLine(line) {
  if (Array.isArray(line)) {
    return line.map((segment) => {
      if (segment && typeof segment === "object") {
        return {
          text: String(segment.text ?? ""),
          href: normalizeTooltipHref(segment.href),
        };
      }
      return { text: String(segment ?? ""), href: "" };
    });
  }
  return [{ text: String(line ?? ""), href: "" }];
}

function normalizeTooltipContent(content) {
  if (content && typeof content === "object" && Array.isArray(content.lines)) {
    return content.lines.map((line) => normalizeTooltipLine(line));
  }
  if (Array.isArray(content)) {
    return content.map((line) => normalizeTooltipLine(line));
  }
  return String(content ?? "").split("\n").map((line) => normalizeTooltipLine(line));
}

function rememberTooltipPointerType(event) {
  const pointerType = String(event?.pointerType || "").trim().toLowerCase();
  if (pointerType) {
    lastTooltipPointerType = pointerType;
    return;
  }
  const type = String(event?.type || "").trim().toLowerCase();
  if (type.startsWith("touch")) {
    lastTooltipPointerType = "touch";
  }
}

function isTouchTooltipActivationEvent(event) {
  const pointerType = String(event?.pointerType || "").trim().toLowerCase();
  if (pointerType) {
    return pointerType === "touch" || pointerType === "pen";
  }
  if (lastTooltipPointerType) {
    return lastTooltipPointerType === "touch" || lastTooltipPointerType === "pen";
  }
  if (event?.sourceCapabilities && event.sourceCapabilities.firesTouchEvents === true) {
    return true;
  }
  return useTouchInteractions;
}

function renderTooltipContent(content) {
  const normalizedLines = normalizeTooltipContent(content);
  tooltip.innerHTML = "";
  let hasLinks = false;
  normalizedLines.forEach((line) => {
    const lineEl = document.createElement("div");
    lineEl.className = "tooltip-line";
    if (!line.length) {
      lineEl.textContent = "";
      tooltip.appendChild(lineEl);
      return;
    }
    line.forEach((segment) => {
      const text = String(segment?.text ?? "");
      const href = normalizeTooltipHref(segment?.href);
      if (href) {
        hasLinks = true;
        const link = document.createElement("a");
        link.className = "tooltip-link";
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.addEventListener(
          "touchstart",
          (event) => {
            rememberTooltipPointerType(event);
            event.stopPropagation();
            markTouchTooltipInteractionBlock(1600);
          },
          { passive: true },
        );
        link.addEventListener("pointerdown", (event) => {
          rememberTooltipPointerType(event);
          event.stopPropagation();
          if (isTouchTooltipActivationEvent(event)) {
            markTouchTooltipInteractionBlock(1600);
          }
        });
        link.addEventListener(
          "touchend",
          (event) => {
            rememberTooltipPointerType(event);
            if (!isTouchTooltipActivationEvent(event)) {
              return;
            }
            event.preventDefault();
            event.stopPropagation();
            markTouchTooltipInteractionBlock(1600);
            markTouchTooltipLinkClickSuppress(1200);
            openTooltipLinkInCurrentTab(link);
          },
          { passive: false },
        );
        link.addEventListener("click", (event) => {
          if (shouldSuppressTouchTooltipLinkClick() && isTouchTooltipActivationEvent(event)) {
            event.preventDefault();
            event.stopPropagation();
            return;
          }
          handleTooltipLinkActivation(event);
        });
        link.textContent = text;
        lineEl.appendChild(link);
      } else {
        lineEl.appendChild(document.createTextNode(text));
      }
    });
    tooltip.appendChild(lineEl);
  });
  return { hasLinks };
}

function isTooltipPinned() {
  return Boolean(pinnedTooltipCell);
}

function clearPinnedTooltipCell() {
  if (!pinnedTooltipCell) return;
  pinnedTooltipCell.classList.remove("active");
  pinnedTooltipCell = null;
}

function showTooltip(content, x, y, options = {}) {
  const { interactive = false } = options;
  const rendered = renderTooltipContent(content);
  const allowInteraction = rendered.hasLinks && (useTouchInteractions || interactive);
  tooltip.classList.toggle("interactive", allowInteraction);
  if (useTouchInteractions) {
    tooltip.classList.add("touch");
    const touchTooltipScale = getTouchTooltipScale();
    tooltip.style.transformOrigin = "top left";
    if (touchTooltipScale === 1) {
      tooltip.style.removeProperty("transform");
    } else {
      tooltip.style.transform = `scale(${touchTooltipScale})`;
    }
  } else {
    tooltip.classList.remove("touch");
    updateDesktopTooltipBounds();
    tooltip.style.transform = "none";
    tooltip.style.removeProperty("transform-origin");
  }
  tooltip.classList.add("visible");
  if (useTouchInteractions) {
    updateTouchTooltipWrapMode();
  }
  pendingTooltipPoint = { x, y };
  if (tooltipPositionFrame !== null) {
    window.cancelAnimationFrame(tooltipPositionFrame);
    tooltipPositionFrame = null;
  }
  if (tooltipSettleFrame !== null) {
    window.cancelAnimationFrame(tooltipSettleFrame);
    tooltipSettleFrame = null;
  }
  tooltipPositionFrame = window.requestAnimationFrame(() => {
    tooltipPositionFrame = null;
    if (!pendingTooltipPoint) return;
    positionTooltip(pendingTooltipPoint.x, pendingTooltipPoint.y);
    tooltipSettleFrame = window.requestAnimationFrame(() => {
      tooltipSettleFrame = null;
      if (!pendingTooltipPoint) return;
      positionTooltip(pendingTooltipPoint.x, pendingTooltipPoint.y);
    });
  });
}

function hideTooltip() {
  if (tooltipPositionFrame !== null) {
    window.cancelAnimationFrame(tooltipPositionFrame);
    tooltipPositionFrame = null;
  }
  if (tooltipSettleFrame !== null) {
    window.cancelAnimationFrame(tooltipSettleFrame);
    tooltipSettleFrame = null;
  }
  pendingTooltipPoint = null;
  tooltip.classList.remove("visible");
  tooltip.classList.remove("nowrap");
  tooltip.classList.remove("interactive");
  tooltip.innerHTML = "";
}

function clearActiveTouchCell() {
  const active = document.querySelector(".cell.active");
  if (active) active.classList.remove("active");
}

function dismissTooltipState() {
  clearPinnedTooltipCell();
  clearActiveTouchCell();
  hideTooltip();
}

function nowMs() {
  return (window.performance && typeof window.performance.now === "function")
    ? window.performance.now()
    : Date.now();
}

function markTouchTooltipDismissBlock(durationMs = 450) {
  if (!useTouchInteractions) return;
  const blockUntil = nowMs() + Math.max(0, Number(durationMs) || 0);
  touchTooltipDismissBlockUntil = Math.max(touchTooltipDismissBlockUntil, blockUntil);
}

function shouldIgnoreTouchTooltipDismiss() {
  if (!useTouchInteractions) return false;
  return nowMs() <= touchTooltipDismissBlockUntil;
}

function markTouchTooltipLinkClickSuppress(durationMs = 1200) {
  if (!useTouchInteractions) return;
  const blockUntil = nowMs() + Math.max(0, Number(durationMs) || 0);
  touchTooltipLinkClickSuppressUntil = Math.max(touchTooltipLinkClickSuppressUntil, blockUntil);
}

function shouldSuppressTouchTooltipLinkClick() {
  if (!useTouchInteractions) return false;
  return nowMs() <= touchTooltipLinkClickSuppressUntil;
}

function markTouchTooltipCellPointerUp(cell, durationMs = 700, wasTap = true) {
  if (!useTouchInteractions) return;
  if (!cell) return;
  touchTooltipRecentPointerUpCell = cell;
  touchTooltipRecentPointerUpUntil = nowMs() + Math.max(0, Number(durationMs) || 0);
  touchTooltipRecentPointerUpWasTap = Boolean(wasTap);
}

function shouldSuppressTouchTooltipCellClick(event, cell) {
  if (!useTouchInteractions) return false;
  if (!cell) return false;
  if (!isTouchTooltipActivationEvent(event)) return false;
  if (nowMs() > touchTooltipRecentPointerUpUntil) {
    return false;
  }
  if (!touchTooltipRecentPointerUpWasTap) {
    return true;
  }
  if (!touchTooltipRecentPointerUpCell || touchTooltipRecentPointerUpCell !== cell) {
    return false;
  }
  return true;
}

function markTouchTooltipCellPointerDown(event, cell) {
  if (!useTouchInteractions) return;
  if (!cell) return;
  if (!isTouchTooltipActivationEvent(event)) return;
  const pointerId = Number(event?.pointerId);
  const clientX = Number(event?.clientX);
  const clientY = Number(event?.clientY);
  const scrollHost = typeof cell.closest === "function"
    ? cell.closest(".card")
    : null;
  touchTooltipPointerDownState = {
    pointerId: Number.isFinite(pointerId) ? pointerId : null,
    clientX: Number.isFinite(clientX) ? clientX : null,
    clientY: Number.isFinite(clientY) ? clientY : null,
    viewportX: window.scrollX || window.pageXOffset || 0,
    viewportY: window.scrollY || window.pageYOffset || 0,
    scrollHost,
    scrollLeft: scrollHost ? Number(scrollHost.scrollLeft || 0) : 0,
    scrollTop: scrollHost ? Number(scrollHost.scrollTop || 0) : 0,
  };
}

function wasTouchTooltipCellTapGesture(event) {
  const state = touchTooltipPointerDownState;
  if (!state) {
    return true;
  }

  const pointerId = Number(event?.pointerId);
  if (state.pointerId !== null && Number.isFinite(pointerId) && pointerId !== state.pointerId) {
    return false;
  }

  const clientX = Number(event?.clientX);
  const clientY = Number(event?.clientY);
  const movedByPointer = Number.isFinite(clientX)
    && Number.isFinite(clientY)
    && state.clientX !== null
    && state.clientY !== null
    && (
      Math.abs(clientX - state.clientX) > TOUCH_TOOLTIP_TAP_MAX_MOVE_PX
      || Math.abs(clientY - state.clientY) > TOUCH_TOOLTIP_TAP_MAX_MOVE_PX
    );

  const viewportX = window.scrollX || window.pageXOffset || 0;
  const viewportY = window.scrollY || window.pageYOffset || 0;
  const viewportMoved = Math.abs(viewportX - state.viewportX) > TOUCH_TOOLTIP_TAP_MAX_SCROLL_PX
    || Math.abs(viewportY - state.viewportY) > TOUCH_TOOLTIP_TAP_MAX_SCROLL_PX;

  let scrollHostMoved = false;
  if (state.scrollHost && state.scrollHost.isConnected) {
    const hostScrollLeft = Number(state.scrollHost.scrollLeft || 0);
    const hostScrollTop = Number(state.scrollHost.scrollTop || 0);
    scrollHostMoved = Math.abs(hostScrollLeft - state.scrollLeft) > TOUCH_TOOLTIP_TAP_MAX_SCROLL_PX
      || Math.abs(hostScrollTop - state.scrollTop) > TOUCH_TOOLTIP_TAP_MAX_SCROLL_PX;
  }

  return !(movedByPointer || viewportMoved || scrollHostMoved);
}

function resolveTouchTooltipCellPointerUpTap(event) {
  if (!useTouchInteractions) return true;
  const wasTap = wasTouchTooltipCellTapGesture(event);
  touchTooltipPointerDownState = null;
  return wasTap;
}

function markTouchTooltipInteractionBlock(durationMs = 450) {
  if (!useTouchInteractions) return;
  const blockUntil = nowMs() + Math.max(0, Number(durationMs) || 0);
  touchTooltipInteractionBlockUntil = Math.max(touchTooltipInteractionBlockUntil, blockUntil);
  touchTooltipDismissBlockUntil = Math.max(touchTooltipDismissBlockUntil, blockUntil);
}

function shouldIgnoreTouchCellClick() {
  if (!useTouchInteractions) return false;
  return nowMs() <= touchTooltipInteractionBlockUntil;
}

function isPointInsideTooltip(event) {
  if (!tooltip.classList.contains("visible")) return false;
  const clientX = Number(event?.clientX);
  const clientY = Number(event?.clientY);
  if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) return false;
  const rect = tooltip.getBoundingClientRect();
  return clientX >= rect.left
    && clientX <= rect.right
    && clientY >= rect.top
    && clientY <= rect.bottom;
}

function hasActiveTooltipCell() {
  if (!useTouchInteractions) return false;
  return Boolean(document.querySelector(".cell.active"));
}

function isTooltipLinkTarget(target) {
  const resolvedTarget = target?.nodeType === Node.TEXT_NODE
    ? target.parentElement
    : target;
  if (!resolvedTarget || typeof resolvedTarget.closest !== "function") return false;
  return Boolean(resolvedTarget.closest(".tooltip-link"));
}

function resolveTooltipTargetElement(target) {
  return target?.nodeType === Node.TEXT_NODE
    ? target.parentElement
    : target;
}

function tooltipLinkElementFromEventTarget(target) {
  const resolvedTarget = resolveTooltipTargetElement(target);
  if (!resolvedTarget || typeof resolvedTarget.closest !== "function") {
    return null;
  }
  const linkElement = resolvedTarget.closest(".tooltip-link");
  return linkElement || null;
}

function openTooltipLinkInNewTab(linkElement) {
  const href = normalizeTooltipHref(linkElement?.href || linkElement?.getAttribute?.("href"));
  if (!href) return false;
  let opened = null;
  try {
    opened = window.open(href, "_blank", "noopener,noreferrer");
  } catch (_) {
    opened = null;
  }
  if (opened && typeof opened === "object") {
    try {
      opened.opener = null;
    } catch (_) {
      // Ignore cross-origin access errors; noopener is already requested.
    }
    return true;
  }
  return false;
}

function openTooltipLinkInCurrentTab(linkElement) {
  const href = normalizeTooltipHref(linkElement?.href || linkElement?.getAttribute?.("href"));
  if (!href) return false;
  if (window.location && typeof window.location.assign === "function") {
    window.location.assign(href);
  } else if (window.location) {
    window.location.href = href;
  }
  return true;
}

function handleTooltipLinkActivation(event) {
  const linkElement = tooltipLinkElementFromEventTarget(event.target);
  if (!linkElement) {
    return false;
  }
  rememberTooltipPointerType(event);
  event.stopPropagation();
  if (isTouchTooltipActivationEvent(event)) {
    if (shouldSuppressTouchTooltipLinkClick()) {
      event.preventDefault();
      return true;
    }
    // Mobile/touch: force same-tab navigation so universal links can hand off to provider apps.
    event.preventDefault();
    markTouchTooltipInteractionBlock(1600);
    markTouchTooltipLinkClickSuppress(1200);
    openTooltipLinkInCurrentTab(linkElement);
    return true;
  }
  // Desktop/mouse: open explicitly in a new tab and never navigate current tab.
  event.preventDefault();
  openTooltipLinkInNewTab(linkElement);
  window.setTimeout(() => {
    dismissTooltipState();
  }, 0);
  return true;
}

function getTooltipEventPoint(event, fallbackElement) {
  const clientX = Number(event?.clientX);
  const clientY = Number(event?.clientY);
  if (Number.isFinite(clientX) && Number.isFinite(clientY)) {
    return { x: clientX, y: clientY };
  }
  const rect = fallbackElement?.getBoundingClientRect?.();
  if (!rect) {
    const viewport = getViewportMetrics();
    return { x: viewport.width / 2, y: viewport.height / 2 };
  }
  return {
    x: rect.left + (rect.width / 2),
    y: rect.top + (rect.height / 2),
  };
}

function attachTooltip(cell, text) {
  if (!text) return;
  if (!useTouchInteractions) {
    cell.addEventListener("mouseenter", (event) => {
      if (isTooltipPinned()) return;
      if (hasActiveTooltipCell()) return;
      showTooltip(text, event.clientX, event.clientY);
    });
    cell.addEventListener("mousemove", (event) => {
      if (isTooltipPinned()) return;
      if (hasActiveTooltipCell()) return;
      showTooltip(text, event.clientX, event.clientY);
    });
    cell.addEventListener("mouseleave", () => {
      if (isTooltipPinned()) return;
      if (hasActiveTooltipCell()) return;
      hideTooltip();
    });
    return;
  }
  const handleTouchCellSelection = (event) => {
    if (shouldIgnoreTouchCellClick()) {
      event.stopPropagation();
      return;
    }
    markTouchTooltipDismissBlock(900);
    if (cell.classList.contains("active")) {
      // Keep touch selection stable; outside tap or another cell tap clears it.
      return;
    }
    clearActiveTouchCell();
    cell.classList.add("active");
    const point = getTooltipEventPoint(event, cell);
    showTooltip(text, point.x, point.y);
  };
  cell.addEventListener("pointerdown", (event) => {
    rememberTooltipPointerType(event);
    markTouchTooltipCellPointerDown(event, cell);
  });
  cell.addEventListener("pointerup", (event) => {
    rememberTooltipPointerType(event);
    if (!isTouchTooltipActivationEvent(event)) {
      return;
    }
    const wasTap = resolveTouchTooltipCellPointerUpTap(event);
    markTouchTooltipCellPointerUp(cell, 700, wasTap);
    if (!wasTap) {
      event.stopPropagation();
      return;
    }
    handleTouchCellSelection(event);
  });
  cell.addEventListener("pointercancel", (event) => {
    rememberTooltipPointerType(event);
    if (!isTouchTooltipActivationEvent(event)) {
      return;
    }
    resolveTouchTooltipCellPointerUpTap(event);
    markTouchTooltipCellPointerUp(cell, 700, false);
  });
  cell.addEventListener("click", (event) => {
    rememberTooltipPointerType(event);
    if (shouldSuppressTouchTooltipCellClick(event, cell)) {
      event.stopPropagation();
      return;
    }
    handleTouchCellSelection(event);
  });
}

function getColors(type) {
  const accent = TYPE_ACCENT_OVERRIDES[type] || TYPE_META[type]?.accent || fallbackColor(type);
  return [DEFAULT_COLORS[0], DEFAULT_COLORS[1], DEFAULT_COLORS[2], DEFAULT_COLORS[3], accent];
}

function buildMultiTypeBackgroundImage(types) {
  const accentColors = Array.from(new Set((types || [])
    .map((type) => getColors(type)[4])
    .filter(Boolean)));
  if (!accentColors.length) return "";
  if (accentColors.length === 1) return "";
  if (accentColors.length === 2) {
    return `linear-gradient(135deg, ${accentColors[0]} 0 50%, ${accentColors[1]} 50% 100%)`;
  }
  const step = 100 / accentColors.length;
  const stops = accentColors.map((color, index) => {
    const start = (index * step).toFixed(2);
    const end = ((index + 1) * step).toFixed(2);
    return `${color} ${start}% ${end}%`;
  });
  return `conic-gradient(from 225deg, ${stops.join(", ")})`;
}

function displayType(type) {
  return capitalizeLabelStart(TYPE_META[type]?.label || prettifyType(type));
}

function summaryTypeTitle(type) {
  return displayType(type);
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
  const value = String(type || "Other").trim();
  if (TYPE_LABEL_OVERRIDES[value]) return TYPE_LABEL_OVERRIDES[value];
  return capitalizeLabelStart(value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .trim());
}

function capitalizeLabelStart(label) {
  const value = String(label || "").trim();
  if (!value) return "Other";
  const firstLetterIndex = value.search(/[a-z]/i);
  if (firstLetterIndex < 0) return value;
  return `${value.slice(0, firstLetterIndex)}${value[firstLetterIndex].toUpperCase()}${value.slice(firstLetterIndex + 1)}`;
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

const FREQUENCY_METRIC_ITEMS = [
  { key: "distance", label: "Distance" },
  { key: "moving_time", label: "Time" },
  { key: "elevation_gain", label: "Elevation" },
];
const METRIC_LABEL_BY_KEY = Object.freeze({
  [ACTIVE_DAYS_METRIC_KEY]: "Active Days",
  [DAYS_OFF_METRIC_KEY]: "Days Off",
  distance: "Distance",
  moving_time: "Time",
  elevation_gain: "Elevation",
});

const FREQUENCY_METRIC_UNAVAILABLE_REASON_BY_KEY = {
  distance: "No distance data in current selection.",
  moving_time: "No time data in current selection.",
  elevation_gain: "No elevation data in current selection.",
};

function getFrequencyMetricUnavailableReason(metricKey, metricLabel) {
  return FREQUENCY_METRIC_UNAVAILABLE_REASON_BY_KEY[metricKey]
    || `No ${String(metricLabel || "metric").toLowerCase()} data in current selection.`;
}

function formatMetricTotal(metricKey, value, units) {
  if (metricKey === ACTIVE_DAYS_METRIC_KEY || metricKey === DAYS_OFF_METRIC_KEY) {
    return formatNumber(value, 0);
  }
  if (metricKey === "distance") {
    return formatDistance(value, units || { distance: "mi" });
  }
  if (metricKey === "moving_time") {
    return formatDuration(value);
  }
  if (metricKey === "elevation_gain") {
    return formatElevation(value, units || { elevation: "ft" });
  }
  return formatNumber(value, 0);
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

function createTooltipTextLine(text) {
  return [{ text: String(text ?? "") }];
}

function createTooltipLinkedTypeLine(prefix, label, suffix, href) {
  const segments = [];
  if (prefix) segments.push({ text: prefix });
  if (href) {
    segments.push({ text: label, href });
  } else {
    segments.push({ text: label });
  }
  if (suffix) segments.push({ text: suffix });
  return segments;
}

function activityTypeOrderForTooltip(typeBreakdown, types) {
  const typeCounts = typeBreakdown?.typeCounts || {};
  const selectedTypes = Array.isArray(types) ? types : [];
  const ordered = [];
  const seen = new Set();

  selectedTypes.forEach((type) => {
    if (Number(typeCounts[type] || 0) <= 0) return;
    ordered.push(type);
    seen.add(type);
  });

  Object.keys(typeCounts)
    .filter((type) => Number(typeCounts[type] || 0) > 0 && !seen.has(type))
    .sort((a, b) => String(a).localeCompare(String(b)))
    .forEach((type) => {
      ordered.push(type);
    });

  return ordered;
}

function flattenTooltipActivityLinks(activityLinksByType) {
  const links = [];
  Object.values(activityLinksByType || {}).forEach((entries) => {
    if (!Array.isArray(entries)) return;
    entries.forEach((entry) => {
      const href = normalizeTooltipHref(entry?.href);
      if (!href) return;
      links.push({ href, name: String(entry?.name || "").trim() });
    });
  });
  return links;
}

function firstTooltipActivityLink(activityLinksByType, preferredType) {
  if (!activityLinksByType || typeof activityLinksByType !== "object") {
    return "";
  }
  const preferred = String(preferredType || "").trim();
  if (preferred && preferred !== "all") {
    const entries = Array.isArray(activityLinksByType[preferred]) ? activityLinksByType[preferred] : [];
    if (entries.length === 1) {
      return normalizeTooltipHref(entries[0]?.href);
    }
    return "";
  }
  const allLinks = flattenTooltipActivityLinks(activityLinksByType);
  return allLinks.length === 1 ? String(allLinks[0].href || "") : "";
}

function formatTypeBreakdownLinesWithLinks(typeBreakdown, types, activityLinksByType) {
  const lines = [];
  const orderedTypes = activityTypeOrderForTooltip(typeBreakdown, types);
  const typeCounts = typeBreakdown?.typeCounts || {};

  orderedTypes.forEach((activityType) => {
    const count = Number(typeCounts[activityType] || 0);
    if (count <= 0) return;

    const typeLabel = displayType(activityType);
    const links = Array.isArray(activityLinksByType?.[activityType])
      ? activityLinksByType[activityType]
      : [];
    const hasSingleLinkedType = count === 1 && links.length === 1 && normalizeTooltipHref(links[0]?.href);

    if (hasSingleLinkedType) {
      lines.push(createTooltipLinkedTypeLine("", typeLabel, `: ${count}`, links[0].href));
      return;
    }

    lines.push(createTooltipTextLine(`${typeLabel}: ${count}`));
    if (count > 1 && links.length > 1) {
      links.forEach((entry, index) => {
        const fallbackName = `${typeLabel} ${index + 1}`;
        const name = String(entry?.name || "").trim() || fallbackName;
        lines.push(createTooltipLinkedTypeLine("    - ", name, "", entry?.href || ""));
      });
    }
  });

  return lines;
}

function getSingleActivityTooltipTypeLabel(typeBreakdown, entry, typeLabels) {
  if (Number(entry?.count || 0) !== 1) {
    return "";
  }

  const typeEntries = sortBreakdownEntries(typeBreakdown?.typeCounts || {});
  if (typeEntries.length === 1 && Number(typeEntries[0][1]) === 1) {
    const activityType = String(typeEntries[0][0] || "").trim();
    if (activityType) {
      if (isOtherSportsType(activityType)) {
        const subtypeEntries = sortBreakdownEntries(typeBreakdown?.otherSubtypeCounts || {});
        if (subtypeEntries.length === 1 && Number(subtypeEntries[0][1]) === 1) {
          return String(subtypeEntries[0][0] || "").trim();
        }
      }
      return displayType(activityType);
    }
  }

  if (Array.isArray(typeLabels) && typeLabels.length === 1) {
    return String(typeLabels[0] || "").replace(/\s+subtype$/i, "").trim();
  }
  if (Array.isArray(entry?.types) && entry.types.length === 1) {
    return displayType(entry.types[0]);
  }
  return "";
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
  const activityLinksByDateType = {};
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
    const parsedActivityLink = parseStravaActivityUrl(activity?.url || activity?.activity_url);
    if (parsedActivityLink?.href && activityType) {
      if (!activityLinksByDateType[dateStr]) {
        activityLinksByDateType[dateStr] = {};
      }
      if (!activityLinksByDateType[dateStr][activityType]) {
        activityLinksByDateType[dateStr][activityType] = [];
      }
      activityLinksByDateType[dateStr][activityType].push({
        href: parsedActivityLink.href,
        name: String(activity?.name || activity?.title || "").trim(),
      });
    }
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

  Object.values(activityLinksByDateType).forEach((linksByType) => {
    Object.values(linksByType).forEach((activitiesForType) => {
      activitiesForType.sort((a, b) => {
        const nameA = String(a?.name || "").trim();
        const nameB = String(b?.name || "").trim();
        if (nameA && nameB && nameA !== nameB) {
          return nameA.localeCompare(nameB);
        }
        if (nameA && !nameB) return -1;
        if (!nameA && nameB) return 1;
        return String(a?.href || "").localeCompare(String(b?.href || ""));
      });
    });
  });

  return { typeLabelsByDate, typeBreakdownsByDate, activityLinksByDateType };
}

function centerSummaryTypeCardTailRow(summaryEl) {
  if (!summaryEl) return;
  const allCards = Array.from(summaryEl.children || []);
  if (!allCards.length) return;

  const typeCards = allCards.filter((card) => card.classList.contains("summary-type-card"));
  typeCards.forEach((card) => {
    card.style.removeProperty("grid-column");
    card.style.removeProperty("transform");
  });
  if (!typeCards.length) return;

  const styles = getComputedStyle(summaryEl);
  const gap = parseFloat(styles.columnGap || styles.gap || "0") || 0;
  const cardRects = allCards.map((card) => card.getBoundingClientRect());
  const firstRowTop = cardRects[0]?.top;
  if (!Number.isFinite(firstRowTop)) return;

  const ROW_TOLERANCE = 1;
  let columns = 0;
  for (let idx = 0; idx < cardRects.length; idx += 1) {
    const top = cardRects[idx]?.top;
    if (!Number.isFinite(top) || Math.abs(top - firstRowTop) > ROW_TOLERANCE) {
      break;
    }
    columns += 1;
  }

  if (columns <= 3) {
    summaryEl.style.setProperty("width", "100%");
    summaryEl.style.setProperty("max-width", "none");
  } else {
    summaryEl.style.removeProperty("width");
    summaryEl.style.removeProperty("max-width");
  }

  if (columns <= 1) return;

  const totalCardCount = allCards.length;
  const tailCount = totalCardCount % columns;
  if (tailCount <= 0) return;

  let trailingTypeCardCount = 0;
  for (let idx = totalCardCount - 1; idx >= 0; idx -= 1) {
    if (!allCards[idx].classList.contains("summary-type-card")) {
      break;
    }
    trailingTypeCardCount += 1;
  }
  // Only reposition when the incomplete final row is made of type cards.
  if (trailingTypeCardCount < tailCount) return;

  let columnStep = 0;
  if (columns >= 2) {
    const firstLeft = cardRects[0]?.left;
    for (let idx = 1; idx < columns; idx += 1) {
      const left = cardRects[idx]?.left;
      if (!Number.isFinite(firstLeft) || !Number.isFinite(left)) continue;
      const delta = left - firstLeft;
      if (delta > 0.5) {
        columnStep = delta;
        break;
      }
    }
  }
  if (!(columnStep > 0.5)) {
    const fallbackWidth = cardRects[0]?.width || 0;
    columnStep = fallbackWidth + gap;
  }

  const startColumn = Math.floor((columns - tailCount) / 2) + 1;
  const horizontalShift = (columns - tailCount) % 2 === 1 && columnStep > 0
    ? columnStep / 2
    : 0;

  for (let idx = 0; idx < tailCount; idx += 1) {
    const card = allCards[totalCardCount - tailCount + idx];
    card.style.gridColumn = String(startColumn + idx);
    if (horizontalShift > 0.5) {
      card.style.transform = `translateX(${horizontalShift}px)`;
    }
  }
}

function buildSummary(
  payload,
  types,
  years,
  units,
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
  const summaryUnits = normalizeUnits(units || DEFAULT_UNITS);
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
  const todayDateKey = getLocalTodayDateKey();

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

  visibleTypeCardsList.sort((a, b) => (typeTotals[b]?.count || 0) - (typeTotals[a]?.count || 0));
  const elapsedDays = years.reduce(
    (sum, year) => sum + getElapsedDayCountForYear(Number(year)),
    0,
  );
  let elapsedActiveDays = 0;
  activeDays.forEach((dateKey) => {
    if (isDateKeyElapsed(dateKey, todayDateKey)) {
      elapsedActiveDays += 1;
    }
  });
  const daysOff = Math.max(0, elapsedDays - elapsedActiveDays);

  const cards = [
    { title: "Activities", value: totals.count.toLocaleString() },
  ];
  if (showActiveDays) {
    cards.push({
      title: "Active Days",
      value: activeDays.size.toLocaleString(),
      metricKey: ACTIVE_DAYS_METRIC_KEY,
      filterable: activeDays.size > 0,
    });
    cards.push({
      title: "Days Off",
      value: daysOff.toLocaleString(),
      metricKey: DAYS_OFF_METRIC_KEY,
      filterable: daysOff > 0,
    });
  }
  cards.push(
    {
      title: "Time",
      value: formatDuration(totals.moving_time),
      metricKey: "moving_time",
      filterable: totals.moving_time > 0,
    },
    {
      title: "Distance",
      value: totals.distance > 0
        ? formatDistance(totals.distance, summaryUnits)
        : STAT_PLACEHOLDER,
      metricKey: "distance",
      filterable: totals.distance > 0,
    },
    {
      title: "Elevation",
      value: totals.elevation > 0
        ? formatElevation(totals.elevation, summaryUnits)
        : STAT_PLACEHOLDER,
      metricKey: "elevation_gain",
      filterable: totals.elevation > 0,
    },
  );

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
    centerSummaryTypeCardTailRow(summary);
  }
}

function buildHeatmapArea(aggregates, year, units, colors, type, layout, options = {}) {
  const heatmapArea = document.createElement("div");
  heatmapArea.className = "heatmap-area";
  const weekStart = normalizeWeekStart(options.weekStart);
  const dayLabels = WEEKDAY_LABELS_BY_WEEK_START[weekStart] || DAYS;
  const metricHeatmapKey = typeof options.metricHeatmapKey === "string"
    ? options.metricHeatmapKey
    : null;
  const metricHeatmapMax = metricHeatmapKey === ACTIVE_DAYS_METRIC_KEY
    ? 1
    : metricHeatmapKey === DAYS_OFF_METRIC_KEY
    ? 1
    : metricHeatmapKey
    ? Number(options.metricMaxByKey?.[metricHeatmapKey] || 0)
    : 0;
  const metricHeatmapActive = Boolean(metricHeatmapKey) && metricHeatmapMax > 0;
  const metricHeatmapColor = options.metricHeatmapColor || colors[4];
  const metricHeatmapEmptyColor = options.metricHeatmapEmptyColor || DEFAULT_COLORS[0];
  const todayDateKey = getLocalTodayDateKey();

  const monthRow = document.createElement("div");
  monthRow.className = "month-row";
  monthRow.style.paddingLeft = `${layout.gridPadLeft}px`;
  heatmapArea.appendChild(monthRow);

  const dayCol = document.createElement("div");
  dayCol.className = "day-col";
  dayCol.style.paddingTop = `${layout.gridPadTop}px`;
  dayCol.style.gap = `${layout.gap}px`;
  dayLabels.forEach((label) => {
    const dayLabel = document.createElement("div");
    dayLabel.className = "day-label";
    dayLabel.textContent = label;
    dayLabel.style.height = `${layout.cell}px`;
    dayLabel.style.lineHeight = `${layout.cell}px`;
    dayCol.appendChild(dayLabel);
  });
  heatmapArea.appendChild(dayCol);

  const yearStart = utcDateFromParts(year, 0, 1);
  const yearEnd = utcDateFromParts(year, 11, 31);
  const start = weekStartOnOrBeforeUtc(yearStart, weekStart);
  const end = weekEndOnOrAfterUtc(yearEnd, weekStart);
  const weekColumns = weekIndexFromWeekStartUtc(end, start) + 1;
  if (weekColumns > 0) {
    heatmapArea.dataset.weekColumns = String(weekColumns);
  }

  for (let month = 0; month < 12; month += 1) {
    const monthStart = utcDateFromParts(year, month, 1);
    const weekIndex = weekIndexFromWeekStartUtc(monthStart, start);
    const monthLabel = document.createElement("div");
    monthLabel.className = "month-label";
    monthLabel.textContent = MONTHS[month];
    monthLabel.style.left = `${weekIndex * (layout.cell + layout.gap)}px`;
    monthRow.appendChild(monthLabel);
  }

  const grid = document.createElement("div");
  grid.className = "grid";

  for (let day = new Date(start.getTime()); day <= end; day.setUTCDate(day.getUTCDate() + 1)) {
    const dateStr = formatUtcDateKey(day);
    const inYear = day.getUTCFullYear() === year;
    const entry = (aggregates && aggregates[dateStr]) || {
      count: 0,
      distance: 0,
      moving_time: 0,
      elevation_gain: 0,
      activity_ids: [],
    };

    const weekIndex = weekIndexFromWeekStartUtc(day, start);
    const row = weekdayRowFromStart(day.getUTCDay(), weekStart);

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
      const metricValue = metricHeatmapKey === ACTIVE_DAYS_METRIC_KEY
        ? (filled ? 1 : 0)
        : metricHeatmapKey === DAYS_OFF_METRIC_KEY
        ? (!filled && isDateKeyElapsed(dateStr, todayDateKey) ? 1 : 0)
        : Number(entry[metricHeatmapKey] || 0);
      cell.style.backgroundImage = "none";
      cell.style.background = metricValue > 0
        ? heatColor(metricHeatmapColor, metricValue, metricHeatmapMax)
        : metricHeatmapEmptyColor;
    } else if (filled && typeof options.colorForEntry === "function") {
      const entryColor = options.colorForEntry(entry);
      const backgroundColor = typeof entryColor === "object" && entryColor !== null
        ? String(entryColor.background || colors[0])
        : String(entryColor || colors[0]);
      const backgroundImage = typeof entryColor === "object" && entryColor !== null
        ? String(entryColor.backgroundImage || "").trim()
        : "";
      cell.style.background = backgroundColor;
      cell.style.backgroundImage = backgroundImage || "none";
    } else {
      cell.style.backgroundImage = "none";
      cell.style.background = filled ? colors[4] : colors[0];
    }

    const durationMinutes = Math.round((entry.moving_time || 0) / 60);
    const duration = durationMinutes >= 60
      ? `${Math.floor(durationMinutes / 60)}h ${durationMinutes % 60}m`
      : `${durationMinutes}m`;

    const typeBreakdown = type === "all" ? options.typeBreakdownsByDate?.[dateStr] : null;
    const typeLabels = type === "all" ? options.typeLabelsByDate?.[dateStr] : null;
    const activityLinksByType = options.activityLinksByDateType?.[dateStr] || {};
    const singleTypeLabel = type === "all"
      ? getSingleActivityTooltipTypeLabel(typeBreakdown, entry, typeLabels)
      : (Number(entry.count || 0) === 1 ? displayType(type) : "");
    const singleActivityLink = Number(entry.count || 0) === 1
      ? firstTooltipActivityLink(activityLinksByType, type)
      : "";
    const lines = [createTooltipTextLine(dateStr)];
    if (singleTypeLabel) {
      lines.push(createTooltipLinkedTypeLine("", singleTypeLabel, "", singleActivityLink));
    } else {
      lines.push(createTooltipTextLine(formatActivityCountLabel(entry.count, type === "all" ? [] : [type])));
    }

    const showDistanceElevation = (entry.distance || 0) > 0 || (entry.elevation_gain || 0) > 0;

    if (type === "all") {
      if (!singleTypeLabel) {
        const breakdownLines = formatTypeBreakdownLinesWithLinks(
          typeBreakdown,
          options.selectedTypes || [],
          activityLinksByType,
        );
        if (breakdownLines.length) {
          lines.push(...breakdownLines);
        } else if (Array.isArray(typeLabels) && typeLabels.length) {
          lines.push(createTooltipTextLine(`Types: ${typeLabels.join(", ")}`));
        } else if (entry.types && entry.types.length) {
          lines.push(createTooltipTextLine(`Types: ${entry.types.map(displayType).join(", ")}`));
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
      lines.push(createTooltipTextLine(`Distance: ${distance}`));
      lines.push(createTooltipTextLine(`Elevation: ${elevation}`));
    }

    if (filled) {
      lines.push(createTooltipTextLine(`Duration: ${duration}`));
    }
    const tooltipContent = { lines };
    const canPinTooltip = Boolean(flattenTooltipActivityLinks(activityLinksByType).length);
    if (!useTouchInteractions) {
      cell.addEventListener("mouseenter", (event) => {
        if (isTooltipPinned()) return;
        if (hasActiveTooltipCell()) return;
        showTooltip(tooltipContent, event.clientX, event.clientY);
      });
      cell.addEventListener("mousemove", (event) => {
        if (isTooltipPinned()) return;
        if (hasActiveTooltipCell()) return;
        showTooltip(tooltipContent, event.clientX, event.clientY);
      });
      cell.addEventListener("mouseleave", () => {
        if (isTooltipPinned()) return;
        if (hasActiveTooltipCell()) return;
        hideTooltip();
      });
      if (canPinTooltip) {
        cell.addEventListener("click", (event) => {
          if (pinnedTooltipCell === cell) {
            clearPinnedTooltipCell();
            hideTooltip();
            return;
          }
          clearPinnedTooltipCell();
          pinnedTooltipCell = cell;
          cell.classList.add("active");
          const point = getTooltipEventPoint(event, cell);
          showTooltip(tooltipContent, point.x, point.y, { interactive: true });
        });
      } else {
        cell.addEventListener("click", () => {
          clearPinnedTooltipCell();
        });
      }
    } else {
      const handleTouchCellSelection = (event) => {
        if (shouldIgnoreTouchCellClick()) {
          event.stopPropagation();
          return;
        }
        markTouchTooltipDismissBlock(900);
        if (cell.classList.contains("active")) {
          // Keep touch selection stable; outside tap or another cell tap clears it.
          return;
        }
        const active = grid.querySelector(".cell.active");
        if (active) active.classList.remove("active");
        cell.classList.add("active");
        const point = getTooltipEventPoint(event, cell);
        showTooltip(tooltipContent, point.x, point.y);
      };
      cell.addEventListener("pointerdown", (event) => {
        rememberTooltipPointerType(event);
        markTouchTooltipCellPointerDown(event, cell);
      });
      cell.addEventListener("pointerup", (event) => {
        rememberTooltipPointerType(event);
        if (!isTouchTooltipActivationEvent(event)) {
          return;
        }
        const wasTap = resolveTouchTooltipCellPointerUpTap(event);
        markTouchTooltipCellPointerUp(cell, 700, wasTap);
        if (!wasTap) {
          event.stopPropagation();
          return;
        }
        handleTouchCellSelection(event);
      });
      cell.addEventListener("pointercancel", (event) => {
        rememberTooltipPointerType(event);
        if (!isTouchTooltipActivationEvent(event)) {
          return;
        }
        resolveTouchTooltipCellPointerUpTap(event);
        markTouchTooltipCellPointerUp(cell, 700, false);
      });
      cell.addEventListener("click", (event) => {
        rememberTooltipPointerType(event);
        if (shouldSuppressTouchTooltipCellClick(event, cell)) {
          event.stopPropagation();
          return;
        }
        handleTouchCellSelection(event);
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

function getFilterableKeys(items) {
  return (Array.isArray(items) ? items : [])
    .filter((item) => item && item.filterable)
    .map((item) => item.key);
}

function normalizeSingleSelectKey(activeKey, filterableKeys) {
  return filterableKeys.includes(activeKey) ? activeKey : null;
}

function renderSingleSelectButtonState(items, buttonMap, activeKey) {
  (Array.isArray(items) ? items : []).forEach((item) => {
    const button = buttonMap.get(item.key);
    if (!button) return;
    const active = activeKey === item.key;
    button.classList.toggle("active", active);
    if (active) {
      button.classList.remove("fact-glow-cleared");
    }
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function attachSingleSelectCardToggle(button, options = {}) {
  const {
    itemKey,
    getActiveKey,
    setActiveKey,
    onToggleComplete,
    clearedClassName = "fact-glow-cleared",
  } = options;
  if (!button) return;
  if (typeof getActiveKey !== "function" || typeof setActiveKey !== "function") return;
  button.addEventListener("click", () => {
    const clearing = getActiveKey() === itemKey;
    setActiveKey(clearing ? null : itemKey);
    if (clearing) {
      button.classList.add(clearedClassName);
      button.blur();
    } else {
      button.classList.remove(clearedClassName);
    }
    if (typeof onToggleComplete === "function") {
      onToggleComplete();
    }
  });
  if (!useTouchInteractions) {
    button.addEventListener("pointerleave", () => {
      button.classList.remove(clearedClassName);
    });
  }
}

function buildCard(type, year, aggregates, units, options = {}) {
  const card = document.createElement("div");
  card.className = "card year-card";

  const body = document.createElement("div");
  body.className = "card-body";

  const colors = type === "all" ? DEFAULT_COLORS : getColors(type);
  const metricHeatmapColor = options.metricHeatmapColor || (type === "all" ? MULTI_TYPE_COLOR : colors[4]);
  const metricMaxByKey = {
    [ACTIVE_DAYS_METRIC_KEY]: 0,
    [DAYS_OFF_METRIC_KEY]: 0,
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
  const cardMetricYear = Number(options.cardMetricYear);
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
  const todayDateKey = getLocalTodayDateKey();
  let elapsedActiveDays = 0;
  Object.entries(aggregates || {}).forEach(([dateStr, entry]) => {
    totals.count += entry.count || 0;
    totals.distance += entry.distance || 0;
    totals.moving_time += entry.moving_time || 0;
    totals.elevation += entry.elevation_gain || 0;
    metricMaxByKey.distance = Math.max(metricMaxByKey.distance, Number(entry.distance || 0));
    metricMaxByKey.moving_time = Math.max(metricMaxByKey.moving_time, Number(entry.moving_time || 0));
    metricMaxByKey.elevation_gain = Math.max(metricMaxByKey.elevation_gain, Number(entry.elevation_gain || 0));
    if ((entry?.count || 0) > 0 && isDateKeyElapsed(dateStr, todayDateKey)) {
      elapsedActiveDays += 1;
    }
  });
  const elapsedDaysInYear = getElapsedDayCountForYear(year);
  const daysOffInYear = Math.max(0, elapsedDaysInYear - elapsedActiveDays);
  metricMaxByKey[ACTIVE_DAYS_METRIC_KEY] = totals.count > 0 ? 1 : 0;
  metricMaxByKey[DAYS_OFF_METRIC_KEY] = daysOffInYear > 0 ? 1 : 0;

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
  const filterableMetricKeys = getFilterableKeys(metricItems);
  if (totals.count > 0) {
    filterableMetricKeys.push(ACTIVE_DAYS_METRIC_KEY);
  }
  if (daysOffInYear > 0) {
    filterableMetricKeys.push(DAYS_OFF_METRIC_KEY);
  }
  activeMetricKey = normalizeSingleSelectKey(activeMetricKey, filterableMetricKeys);
  const metricButtons = new Map();
  const reportYearMetricState = (source) => {
    if (!onYearMetricStateChange || !Number.isFinite(cardMetricYear)) return;
    onYearMetricStateChange({
      year: cardMetricYear,
      metricKey: activeMetricKey,
      filterableMetricKeys: filterableMetricKeys.slice(),
      source,
    });
  };
  const renderMetricButtonState = () => renderSingleSelectButtonState(
    metricItems,
    metricButtons,
    activeMetricKey,
  );

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
        attachSingleSelectCardToggle(statCard, {
          itemKey: item.key,
          getActiveKey: () => activeMetricKey,
          setActiveKey: (nextMetricKey) => {
            activeMetricKey = nextMetricKey;
          },
          onToggleComplete: () => {
            renderMetricButtonState();
            renderHeatmap();
            reportYearMetricState("card");
            schedulePostInteractionAlignment();
          },
        });
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

function buildEmptySelectionCard() {
  const card = document.createElement("div");
  card.className = "card card-empty-selection";
  const body = document.createElement("div");
  body.className = "card-empty-selection-body";
  const emptyStat = buildSideStatCard("No activities for current filters", "", {
    className: "card-stat card-empty-selection-stat",
  });
  body.appendChild(emptyStat);
  card.appendChild(body);
  return card;
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

function buildStatsOverview(payload, types, years, color, options = {}) {
  const card = document.createElement("div");
  card.className = "card more-stats";

  const body = document.createElement("div");
  body.className = "more-stats-body";

  const graphs = document.createElement("div");
  graphs.className = "more-stats-grid";
  const facts = buildSideStatColumn([], { className: "more-stats-facts side-stats-column" });
  const metricChipRow = document.createElement("div");
  metricChipRow.className = "more-stats-metric-chips";
  const factGrid = document.createElement("div");
  factGrid.className = "more-stats-fact-grid";

  const yearsDesc = years.slice().sort((a, b) => b - a);
  const emptyColor = DEFAULT_COLORS[0];
  const selectedYearSet = new Set(yearsDesc.map(Number));
  const units = normalizeUnits(options.units || payload.units || DEFAULT_UNITS);
  const onFactStateChange = typeof options.onFactStateChange === "function"
    ? options.onFactStateChange
    : null;
  const onMetricStateChange = typeof options.onMetricStateChange === "function"
    ? options.onMetricStateChange
    : null;
  let activeFactKey = typeof options.initialFactKey === "string"
    ? options.initialFactKey
    : null;
  let activeMetricKey = typeof options.initialMetricKey === "string"
    ? options.initialMetricKey
    : null;
  const aggregateYears = payload.aggregates || {};
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
      const dayEntry = aggregateYears?.[String(year)]?.[activity.type]?.[dateStr] || null;
      const dayEntryCount = Number(dayEntry?.count || 0);
      const perActivityMetricValue = (metricKey) => {
        if (dayEntryCount <= 0) return 0;
        const dayValue = Number(dayEntry?.[metricKey] || 0);
        return Number.isFinite(dayValue) && dayValue > 0
          ? dayValue / dayEntryCount
          : 0;
      };
      return {
        dateKey: dateStr,
        date,
        type: activity.type,
        subtype: getActivitySubtypeLabel(activity),
        year,
        dayIndex: date.getDay(),
        monthIndex: date.getMonth(),
        weekIndex: weekOfYear(date),
        hour: hasHour ? hourValue : null,
        active_days: 1,
        distance: perActivityMetricValue("distance"),
        moving_time: perActivityMetricValue("moving_time"),
        elevation_gain: perActivityMetricValue("elevation_gain"),
      };
    })
    .filter(Boolean);

  const activityYears = new Set(activities.map((activity) => Number(activity.year)));
  const visibleYearsDesc = yearsDesc.filter((year) => activityYears.has(Number(year)));
  const yearIndex = new Map();
  visibleYearsDesc.forEach((year, index) => {
    yearIndex.set(Number(year), index);
  });
  const activeDateKeys = new Set(activities.map((activity) => String(activity.dateKey || "")));
  const daysOffEntries = [];
  visibleYearsDesc.forEach((year) => {
    const elapsedDaysInYear = getElapsedDayCountForYear(year);
    if (elapsedDaysInYear <= 0) return;
    const yearStartUtc = utcDateFromParts(year, 0, 1);
    for (let dayOffset = 0; dayOffset < elapsedDaysInYear; dayOffset += 1) {
      const dayUtc = new Date(yearStartUtc.getTime());
      dayUtc.setUTCDate(dayUtc.getUTCDate() + dayOffset);
      const dateKey = formatUtcDateKey(dayUtc);
      if (activeDateKeys.has(dateKey)) continue;
      const date = new Date(`${dateKey}T00:00:00`);
      if (Number.isNaN(date.getTime())) continue;
      daysOffEntries.push({
        dateKey,
        date,
        type: "",
        subtype: "",
        year,
        dayIndex: date.getDay(),
        monthIndex: date.getMonth(),
        weekIndex: weekOfYear(date),
        hour: null,
        active_days: 0,
        [DAYS_OFF_METRIC_KEY]: 1,
      });
    }
  });

  const formatBreakdown = (total, breakdown) => formatTooltipBreakdown(total, breakdown, types);

  const dayDisplayLabels = ["Sun", "", "", "Wed", "", "", "Sat"];
  const monthDisplayLabels = ["Jan", "", "Mar", "", "May", "", "Jul", "", "Sep", "", "Nov", ""];

  const buildZeroedMatrix = (columns) => visibleYearsDesc.map(() => new Array(columns).fill(0));
  const buildBreakdownMatrix = (columns) => visibleYearsDesc.map(() => (
    Array.from({ length: columns }, () => createTooltipBreakdown())
  ));

  const buildFrequencyData = (filterFn, metricKey = null) => {
    const dayMatrix = buildZeroedMatrix(7);
    const dayBreakdowns = buildBreakdownMatrix(7);
    const monthMatrix = buildZeroedMatrix(12);
    const monthBreakdowns = buildBreakdownMatrix(12);
    const hourMatrix = buildZeroedMatrix(24);
    const hourBreakdowns = buildBreakdownMatrix(24);
    const weekTotals = new Array(54).fill(0);
    let activityCount = 0;
    let hourActivityCount = 0;
    const sourceItems = metricKey === DAYS_OFF_METRIC_KEY
      ? daysOffEntries
      : activities;

    sourceItems.forEach((activity) => {
      if (typeof filterFn === "function" && !filterFn(activity)) {
        return;
      }
      const row = yearIndex.get(activity.year);
      if (row === undefined) return;
      const weight = metricKey === ACTIVE_DAYS_METRIC_KEY
        ? Number(activity.active_days || 0)
        : metricKey === DAYS_OFF_METRIC_KEY
        ? Number(activity[DAYS_OFF_METRIC_KEY] || 0)
        : metricKey
        ? Number(activity[metricKey] || 0)
        : 1;

      activityCount += 1;
      dayMatrix[row][activity.dayIndex] += weight;
      monthMatrix[row][activity.monthIndex] += weight;
      if (activity.weekIndex >= 1 && activity.weekIndex < weekTotals.length) {
        weekTotals[activity.weekIndex] += weight;
      }

      if (metricKey !== DAYS_OFF_METRIC_KEY) {
        const dayBucket = dayBreakdowns[row][activity.dayIndex];
        const monthBucket = monthBreakdowns[row][activity.monthIndex];
        addTooltipBreakdownCount(dayBucket, activity.type, activity.subtype);
        addTooltipBreakdownCount(monthBucket, activity.type, activity.subtype);
      }

      if (Number.isFinite(activity.hour)) {
        hourActivityCount += 1;
        hourMatrix[row][activity.hour] += weight;
        if (metricKey !== DAYS_OFF_METRIC_KEY) {
          const hourBucket = hourBreakdowns[row][activity.hour];
          addTooltipBreakdownCount(hourBucket, activity.type, activity.subtype);
        }
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
  const metricTotals = {
    [ACTIVE_DAYS_METRIC_KEY]: activities.reduce((sum, activity) => sum + Number(activity.active_days || 0), 0),
    [DAYS_OFF_METRIC_KEY]: daysOffEntries.length,
    distance: activities.reduce((sum, activity) => sum + Number(activity.distance || 0), 0),
    moving_time: activities.reduce((sum, activity) => sum + Number(activity.moving_time || 0), 0),
    elevation_gain: activities.reduce((sum, activity) => sum + Number(activity.elevation_gain || 0), 0),
  };
  const metricItems = FREQUENCY_METRIC_ITEMS.map((item) => ({
    key: item.key,
    label: item.label,
    filterable: Number(metricTotals[item.key] || 0) > 0,
  }));
  const metricButtons = new Map();
  const filterableMetricKeys = getFilterableKeys(metricItems);
  if (Number(metricTotals[ACTIVE_DAYS_METRIC_KEY] || 0) > 0) {
    filterableMetricKeys.push(ACTIVE_DAYS_METRIC_KEY);
  }
  if (Number(metricTotals[DAYS_OFF_METRIC_KEY] || 0) > 0) {
    filterableMetricKeys.push(DAYS_OFF_METRIC_KEY);
  }
  activeMetricKey = normalizeSingleSelectKey(activeMetricKey, filterableMetricKeys);
  const reportMetricState = (source) => {
    if (!onMetricStateChange) return;
    onMetricStateChange({
      metricKey: activeMetricKey,
      filterableMetricKeys: filterableMetricKeys.slice(),
      source,
    });
  };
  const renderMetricButtonState = () => renderSingleSelectButtonState(
    metricItems,
    metricButtons,
    activeMetricKey,
  );
  if (baseData.activityCount <= 0) {
    if (onFactStateChange) {
      onFactStateChange({
        factKey: null,
        filterableFactKeys: [],
        source: "init",
      });
    }
    reportMetricState("init");
    return buildEmptySelectionCard();
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
    if (panel === monthPanel.panel) {
      col.dataset.chipAxisAnchor = "true";
    }
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

  const factButtons = new Map();
  const filterableFactKeys = getFilterableKeys(factItems);
  activeFactKey = normalizeSingleSelectKey(activeFactKey, filterableFactKeys);
  const reportFactState = (source) => {
    if (!onFactStateChange) return;
    onFactStateChange({
      factKey: activeFactKey,
      filterableFactKeys: filterableFactKeys.slice(),
      source,
    });
  };
  const renderFactButtonState = () => renderSingleSelectButtonState(
    factItems,
    factButtons,
    activeFactKey,
  );

  const renderFrequencyGraphs = () => {
    const activeFact = factItems.find((item) => item.key === activeFactKey) || null;
    const matrixData = buildFrequencyData(activeFact?.filter, activeMetricKey);
    const metricLabel = activeMetricKey ? (METRIC_LABEL_BY_KEY[activeMetricKey] || "Metric") : "";
    const formatTooltipValue = (value) => {
      if (!activeMetricKey) return "";
      return `${metricLabel}: ${formatMetricTotal(activeMetricKey, value, units)}`;
    };
    const formatMatrixTooltip = (year, label, value, breakdown) => {
      const lines = [`${year} · ${label}`];
      if (activeMetricKey) {
        lines.push(formatTooltipValue(value));
        if (activeMetricKey !== DAYS_OFF_METRIC_KEY) {
          const activityTotal = Object.values(breakdown?.typeCounts || {})
            .reduce((sum, count) => sum + count, 0);
          lines.push(formatBreakdown(activityTotal, breakdown));
        }
      } else {
        lines.push(formatBreakdown(value, breakdown));
      }
      return lines.join("\n");
    };

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
            return formatMatrixTooltip(year, label, value, breakdown);
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
            return formatMatrixTooltip(year, label, value, breakdown);
          },
        },
      ),
    );

    hourPanel.body.innerHTML = "";
    const renderHourMatrix = () => {
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
              return formatMatrixTooltip(year, label, value, breakdown);
            },
          },
        ),
      );
    };
    if (activeMetricKey === DAYS_OFF_METRIC_KEY) {
      renderHourMatrix();
      const hourGrid = hourPanel.body.querySelector(".axis-matrix-grid");
      if (hourGrid) {
        const unavailableNote = document.createElement("div");
        unavailableNote.className = "hourly-days-off-note";
        unavailableNote.textContent = "Hourly frequency unavailable for Days Off";
        hourGrid.classList.add("hourly-days-off-unavailable-grid");
        hourGrid.appendChild(unavailableNote);
      }
      return;
    }
    if (matrixData.hourActivityCount > 0) {
      renderHourMatrix();
      return;
    }

    const fallback = document.createElement("div");
    fallback.className = "stat-subtitle";
    fallback.textContent = "Time-of-day stats require activity timestamps.";
    hourPanel.body.appendChild(fallback);
  };

  metricItems.forEach((item) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "more-stats-metric-chip";
    chip.textContent = item.label;
    chip.setAttribute("aria-disabled", item.filterable ? "false" : "true");
    chip.setAttribute("aria-pressed", "false");
    if (item.filterable) {
      attachSingleSelectCardToggle(chip, {
        itemKey: item.key,
        getActiveKey: () => activeMetricKey,
        setActiveKey: (nextMetricKey) => {
          activeMetricKey = nextMetricKey;
        },
        onToggleComplete: () => {
          renderMetricButtonState();
          renderFrequencyGraphs();
          reportMetricState("card");
          schedulePostInteractionAlignment();
        },
      });
    } else {
      const unavailableReason = getFrequencyMetricUnavailableReason(item.key, item.label);
      chip.classList.add("is-unavailable");
      chip.title = unavailableReason;
      chip.setAttribute("aria-label", `${item.label} unavailable. ${unavailableReason}`);
      attachTooltip(chip, unavailableReason);
    }
    metricButtons.set(item.key, chip);
    metricChipRow.appendChild(chip);
  });

  factItems.forEach((item) => {
    const factCard = buildSideStatCard(item.label, item.value, {
      tagName: "button",
      className: "card-stat more-stats-fact-card more-stats-fact-button",
      extraClasses: item.key ? [`fact-${item.key}`] : [],
      disabled: !item.filterable,
      ariaPressed: false,
    });
    if (item.filterable) {
      attachSingleSelectCardToggle(factCard, {
        itemKey: item.key,
        getActiveKey: () => activeFactKey,
        setActiveKey: (nextFactKey) => {
          activeFactKey = nextFactKey;
        },
        onToggleComplete: () => {
          renderFactButtonState();
          renderFrequencyGraphs();
          reportFactState("card");
          schedulePostInteractionAlignment();
        },
      });
    }
    factButtons.set(item.key, factCard);
    factGrid.appendChild(factCard);
  });

  renderMetricButtonState();
  renderFactButtonState();
  renderFrequencyGraphs();
  reportMetricState("init");
  reportFactState("init");

  facts.appendChild(metricChipRow);
  facts.appendChild(factGrid);
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

function applyDebugPayloadOverrides(payload) {
  if (!payload || typeof payload !== "object" || typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  const debugYearRaw = params.get("debugYear");
  const debugWeekStartRaw = String(params.get("debugWeekStart") || "").trim().toLowerCase();

  if (debugWeekStartRaw === "monday" || debugWeekStartRaw === "mon") {
    payload.week_start = WEEK_START_MONDAY;
  } else if (debugWeekStartRaw === "sunday" || debugWeekStartRaw === "sun") {
    payload.week_start = WEEK_START_SUNDAY;
  }

  if (!debugYearRaw) return;
  const debugYear = Number(debugYearRaw);
  if (!Number.isInteger(debugYear) || debugYear < 1900 || debugYear > 2100) return;

  if (!Array.isArray(payload.types)) payload.types = [];
  if (!Array.isArray(payload.years)) payload.years = [];
  if (!Array.isArray(payload.activities)) payload.activities = [];
  if (!payload.aggregates || typeof payload.aggregates !== "object") payload.aggregates = {};

  const fallbackType = "Run";
  const debugType = payload.types.length ? String(payload.types[0]) : fallbackType;
  if (!payload.types.includes(debugType)) {
    payload.types.push(debugType);
  }

  const debugDate = `${debugYear}-01-01`;
  const debugYearKey = String(debugYear);
  payload.aggregates[debugYearKey] = payload.aggregates[debugYearKey] || {};
  payload.aggregates[debugYearKey][debugType] = payload.aggregates[debugYearKey][debugType] || {};
  payload.aggregates[debugYearKey][debugType][debugDate] = {
    count: 1,
    distance: 1609.344,
    moving_time: 1800,
    elevation_gain: 30,
    activity_ids: ["debug-placeholder"],
  };

  const hasDebugActivity = payload.activities.some(
    (activity) => Number(activity?.year) === debugYear && String(activity?.date || "") === debugDate,
  );
  if (!hasDebugActivity) {
    payload.activities.push({
      date: debugDate,
      hour: 8,
      name: "Debug placeholder activity",
      subtype: debugType,
      type: debugType,
      year: debugYear,
    });
  }

  if (!payload.years.some((yearValue) => Number(yearValue) === debugYear)) {
    payload.years.push(debugYear);
  }
}

async function init() {
  syncRepoLink();
  syncFooterHostedLink();
  syncStravaProfileLink();
  syncProfileLinkNavigationTarget();
  syncHeaderLinkPlacement();
  const resp = await fetch("data.json");
  if (!resp.ok) {
    throw new Error(`Failed to load data.json (${resp.status})`);
  }
  const payload = await resp.json();
  if (!payload || typeof payload !== "object") {
    throw new Error("Invalid dashboard data format.");
  }
  applyDebugPayloadOverrides(payload);
  const repoCandidate = payloadRepoCandidate(payload);
  const profileUrl = payloadProfileUrl(payload);
  const sourceValue = payloadSource(payload);
  syncRepoLink(repoCandidate);
  syncFooterHostedLink(repoCandidate);
  syncStravaProfileLink(
    profileUrl,
    sourceValue,
  );
  setDashboardTitle(sourceValue);
  TYPE_META = payload.type_meta || {};
  OTHER_BUCKET = String(payload.other_bucket || "OtherSports");
  (payload.types || []).forEach((type) => {
    if (!TYPE_META[type]) {
      TYPE_META[type] = { label: prettifyType(type), accent: fallbackColor(type) };
    }
  });

  const typeOptions = [
    { value: "all", label: "All Activities" },
    ...payload.types.map((type) => ({ value: type, label: displayType(type) })),
  ];
  const setupUnits = normalizeUnits(payload.units || DEFAULT_UNITS);
  const setupWeekStart = normalizeWeekStart(payload.week_start || payload.weekStart);

  let resizeTimer = null;
  let lastViewportWidth = window.innerWidth;
  let lastIsNarrowLayout = isNarrowLayoutViewport();

  let allTypesMode = true;
  let selectedTypes = new Set();
  let allYearsMode = true;
  let selectedYears = new Set();
  let currentUnitSystem = getUnitSystemFromUnits(setupUnits);
  let currentUnits = getUnitsForSystem(currentUnitSystem);
  let currentVisibleYears = payload.years.slice().sort((a, b) => b - a);
  let hoverClearedSummaryType = null;
  let hoverClearedSummaryYearMetricKey = null;
  const selectedYearMetricByYear = new Map();
  let visibleYearMetricYears = new Set();
  let filterableYearMetricsByYear = new Map();
  let selectedFrequencyFactKey = null;
  let visibleFrequencyFilterableFactKeys = new Set();
  let selectedFrequencyMetricKey = null;
  let visibleFrequencyFilterableMetricKeys = new Set();
  let draftTypeMenuSelection = null;
  let draftYearMenuSelection = null;

  function hasAnyYearMetricSelection() {
    for (const metricKey of selectedYearMetricByYear.values()) {
      if (metricKey) return true;
    }
    return false;
  }

  function hasAnyFrequencyMetricSelection() {
    return Boolean(selectedFrequencyMetricKey);
  }

  function isDefaultFilterState() {
    return areAllTypesSelected()
      && areAllYearsSelected()
      && !hasAnyYearMetricSelection()
      && !selectedFrequencyFactKey
      && !hasAnyFrequencyMetricSelection();
  }

  function syncResetAllButtonState() {
    if (!resetAllButton) return;
    resetAllButton.disabled = isDefaultFilterState();
  }

  function syncUnitToggleState() {
    const isMetric = currentUnitSystem === "metric";
    if (imperialUnitsButton) {
      imperialUnitsButton.classList.toggle("active", !isMetric);
      imperialUnitsButton.setAttribute("aria-pressed", isMetric ? "false" : "true");
    }
    if (metricUnitsButton) {
      metricUnitsButton.classList.toggle("active", isMetric);
      metricUnitsButton.setAttribute("aria-pressed", isMetric ? "true" : "false");
    }
  }

  function setUnitSystem(system) {
    const normalizedSystem = system === "metric" ? "metric" : "imperial";
    if (normalizedSystem === currentUnitSystem) {
      syncUnitToggleState();
      return;
    }
    currentUnitSystem = normalizedSystem;
    currentUnits = getUnitsForSystem(currentUnitSystem);
    syncUnitToggleState();
    update();
  }

  function setYearMetricSelection(year, metricKey) {
    const normalizedYear = Number(year);
    if (!Number.isFinite(normalizedYear)) return;
    if (typeof metricKey === "string" && metricKey) {
      selectedYearMetricByYear.set(normalizedYear, metricKey);
      return;
    }
    selectedYearMetricByYear.delete(normalizedYear);
  }

  function getActiveSummaryYearMetricKey() {
    return deriveActiveSummaryYearMetricKey({
      visibleYears: visibleYearMetricYears,
      selectedMetricByYear: selectedYearMetricByYear,
      filterableMetricsByYear: filterableYearMetricsByYear,
    });
  }

  function getActiveSummaryMetricDisplayKey() {
    const yearSummaryMetricKey = getActiveSummaryYearMetricKey();
    if (!yearSummaryMetricKey) return null;
    return selectedFrequencyMetricKey === yearSummaryMetricKey
      ? yearSummaryMetricKey
      : null;
  }

  function syncSummaryYearMetricButtons() {
    if (!summary) return;
    const buttons = Array.from(summary.querySelectorAll(".summary-year-metric-card"));
    if (!buttons.length) return;
    const activeSummaryYearMetricKey = getActiveSummaryMetricDisplayKey();
    if (activeSummaryYearMetricKey && hoverClearedSummaryYearMetricKey === activeSummaryYearMetricKey) {
      hoverClearedSummaryYearMetricKey = null;
    }
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

  function toggleType(value) {
    const nextState = reduceTopButtonSelection({
      rawValue: value,
      allMode: allTypesMode,
      selectedValues: selectedTypes,
      allValues: payload.types,
    });
    allTypesMode = nextState.allMode;
    selectedTypes = nextState.selectedValues;
  }

  function toggleTypeMenu(value) {
    const selection = draftTypeMenuSelection || cloneSelectionState(allTypesMode, selectedTypes);
    const nextState = reduceMenuSelection({
      rawValue: value,
      allMode: selection.allMode,
      selectedValues: selection.selectedValues,
      allValues: payload.types,
      allowToggleOffAll: true,
    });
    draftTypeMenuSelection = nextState;
  }

  function toggleTypeFromSummaryCard(type) {
    toggleType(type);
  }

  function toggleYear(value) {
    const nextState = reduceTopButtonSelection({
      rawValue: value,
      allMode: allYearsMode,
      selectedValues: selectedYears,
      allValues: currentVisibleYears,
      normalizeValue: (rawValue) => Number(rawValue),
    });
    allYearsMode = nextState.allMode;
    selectedYears = nextState.selectedValues;
  }

  function toggleYearMenu(value) {
    const selection = draftYearMenuSelection || cloneSelectionState(allYearsMode, selectedYears);
    const nextState = reduceMenuSelection({
      rawValue: value,
      allMode: selection.allMode,
      selectedValues: selection.selectedValues,
      allValues: currentVisibleYears,
      normalizeValue: (rawValue) => Number(rawValue),
      allowToggleOffAll: true,
    });
    draftYearMenuSelection = nextState;
  }

  function commitTypeMenuSelection() {
    if (!draftTypeMenuSelection) return;
    allTypesMode = draftTypeMenuSelection.allMode;
    selectedTypes = new Set(draftTypeMenuSelection.selectedValues);
    draftTypeMenuSelection = null;
  }

  function commitYearMenuSelection() {
    if (!draftYearMenuSelection) return;
    allYearsMode = draftYearMenuSelection.allMode;
    selectedYears = new Set(draftYearMenuSelection.selectedValues);
    draftYearMenuSelection = null;
  }

  function finalizeTypeSelection() {
    if (areAllTypesSelected()) return;
    selectedTypes = new Set(payload.types.filter((type) => selectedTypes.has(type)));
  }

  function finalizeYearSelection() {
    if (!areAllYearsSelected() && selectedYears.size === currentVisibleYears.length) {
      allYearsMode = true;
      selectedYears.clear();
    }
  }

  function setCardScrollKey(card, key) {
    if (!card || !card.dataset) return;
    card.dataset.scrollKey = String(key || "");
  }

  function update(options = {}) {
    const keepTypeMenuOpen = Boolean(options.keepTypeMenuOpen);
    const keepYearMenuOpen = Boolean(options.keepYearMenuOpen);
    const resetTypeMenuScroll = Boolean(options.resetTypeMenuScroll);
    const resetYearMenuScroll = Boolean(options.resetYearMenuScroll);
    const menuOnly = Boolean(options.menuOnly);
    const resetCardScroll = Boolean(options.resetCardScroll);
    const resetViewport = Boolean(options.resetViewport);
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
    const typeMenuSelection = draftTypeMenuSelection || { allMode: allTypesMode, selectedValues: selectedTypes };
    const yearMenuSelection = draftYearMenuSelection || { allMode: allYearsMode, selectedValues: selectedYears };
    const typeMenuTypes = selectedTypesListForState(typeMenuSelection, payload.types);
    const yearMenuYears = selectedYearsListForState(yearMenuSelection, visibleYears);
    yearMenuYears.sort((a, b) => b - a);

    renderFilterButtons(yearButtons, yearOptions, (value) => {
      draftYearMenuSelection = null;
      setMenuOpenState(yearMenu, yearMenuButton, false);
      toggleYear(value);
      update();
    });
    renderFilterMenuOptions(
      typeMenuOptions,
      typeOptions,
      typeMenuSelection.selectedValues,
      typeMenuSelection.allMode,
      (value) => {
        toggleTypeMenu(value);
        update({ keepTypeMenuOpen: true, menuOnly: true });
      },
    );
    renderFilterMenuDoneButton(typeMenuOptions, () => {
      commitTypeMenuSelection();
      finalizeTypeSelection();
      setMenuOpenState(typeMenu, typeMenuButton, false);
      update();
    });
    renderFilterMenuOptions(
      yearMenuOptions,
      yearOptions,
      yearMenuSelection.selectedValues,
      yearMenuSelection.allMode,
      (value) => {
        toggleYearMenu(value);
        update({ keepYearMenuOpen: true, menuOnly: true });
      },
      (v) => Number(v),
    );
    renderFilterMenuDoneButton(yearMenuOptions, () => {
      commitYearMenuSelection();
      finalizeYearSelection();
      setMenuOpenState(yearMenu, yearMenuButton, false);
      update();
    });

    syncFilterControlState({
      typeButtons,
      yearButtons,
      selectedTypes,
      selectedYears,
      allTypeValues: payload.types,
      allYearValues: currentVisibleYears,
      allTypesSelected,
      allYearsSelected,
      typeMenuTypes,
      yearMenuYears,
      typeMenuSelection,
      yearMenuSelection,
      typeMenuLabel,
      yearMenuLabel,
      typeClearButton,
      yearClearButton,
      keepTypeMenuOpen,
      keepYearMenuOpen,
      typeMenu,
      yearMenu,
      typeMenuButton,
      yearMenuButton,
    });

    syncOpenFilterMenuMaxHeights();
    if (resetTypeMenuScroll) {
      resetFilterMenuScroll(typeMenuOptions);
    }
    if (resetYearMenuScroll) {
      resetFilterMenuScroll(yearMenuOptions);
    }

    if (menuOnly) {
      return;
    }
    clearPinnedTooltipCell();
    hideTooltip();

    const years = selectedYearsList(visibleYears);
    years.sort((a, b) => b - a);
    const previousSummaryYearMetricKey = getActiveSummaryYearMetricKey();
    const initialFrequencyMetricKey = selectedFrequencyMetricKey;
    const getInitialYearMetricKey = (year) => {
      const storedMetricKey = selectedYearMetricByYear.get(Number(year));
      if (typeof storedMetricKey === "string" && storedMetricKey) {
        return storedMetricKey;
      }
      return typeof previousSummaryYearMetricKey === "string" && previousSummaryYearMetricKey
        ? previousSummaryYearMetricKey
        : null;
    };
    const frequencyCardColor = getActivityFrequencyCardColor(types);
    const showCombinedTypes = types.length > 1;
    const activeSummaryTypeCards = allTypesSelected ? new Set() : new Set(types);
    const nextVisibleYearMetricYears = new Set();
    const nextFilterableYearMetricsByYear = new Map();
    const nextVisibleFrequencyFilterableFactKeys = new Set();
    const nextVisibleFrequencyFilterableMetricKeys = new Set();
    const onYearMetricStateChange = ({ year, metricKey, filterableMetricKeys, source }) => {
      const normalizedYear = Number(year);
      if (!Number.isFinite(normalizedYear)) return;
      const filterableSet = toStringSet(filterableMetricKeys);
      nextFilterableYearMetricsByYear.set(normalizedYear, filterableSet);
      const normalizedMetricKey = typeof metricKey === "string" && filterableSet.has(metricKey)
        ? metricKey
        : null;
      setYearMetricSelection(normalizedYear, normalizedMetricKey);
      if (source === "card") {
        syncSummaryYearMetricButtons();
        syncResetAllButtonState();
      }
    };
    const onFrequencyFactStateChange = ({ factKey, filterableFactKeys }) => {
      nextVisibleFrequencyFilterableFactKeys.clear();
      toStringSet(filterableFactKeys).forEach((key) => {
        nextVisibleFrequencyFilterableFactKeys.add(key);
      });
      selectedFrequencyFactKey = typeof factKey === "string" && nextVisibleFrequencyFilterableFactKeys.has(factKey)
        ? factKey
        : null;
      syncResetAllButtonState();
    };
    const onFrequencyMetricStateChange = ({ metricKey, filterableMetricKeys, source }) => {
      nextVisibleFrequencyFilterableMetricKeys.clear();
      toStringSet(filterableMetricKeys).forEach((key) => {
        nextVisibleFrequencyFilterableMetricKeys.add(key);
      });
      const normalizedMetricKey = typeof metricKey === "string" && nextVisibleFrequencyFilterableMetricKeys.has(metricKey)
        ? metricKey
        : null;
      if (source === "card") {
        selectedFrequencyMetricKey = normalizedMetricKey;
        syncSummaryYearMetricButtons();
      }
      syncResetAllButtonState();
    };

    const previousCardScrollOffsets = resetCardScroll
      ? new Map()
      : captureCardScrollOffsets(heatmaps);

    if (heatmaps) {
      heatmaps.innerHTML = "";
      const showMoreStats = true;
      const {
        typeLabelsByDate,
        typeBreakdownsByDate,
        activityLinksByDateType,
      } = buildCombinedTypeDetailsByDate(payload, types, years);
      if (showCombinedTypes) {
        const section = document.createElement("div");
        section.className = "type-section";
        const list = document.createElement("div");
        list.className = "type-list";
        const yearTotals = getTypesYearTotals(payload, types, years);
        const cardYears = years.filter((year) => (yearTotals.get(year) || 0) > 0);
        const combinedSelectionKey = `combined:${types.join("|")}`;
        if (showMoreStats) {
          const frequencyCard = buildStatsOverview(payload, types, cardYears, frequencyCardColor, {
            units: currentUnits,
            initialFactKey: selectedFrequencyFactKey,
            initialMetricKey: initialFrequencyMetricKey,
            onFactStateChange: onFrequencyFactStateChange,
            onMetricStateChange: onFrequencyMetricStateChange,
          });
          setCardScrollKey(frequencyCard, `${combinedSelectionKey}:frequency`);
          list.appendChild(
            buildLabeledCardRow(
              "Activity Frequency",
              frequencyCard,
              "frequency",
            ),
          );
        }
        cardYears.forEach((year) => {
          const yearData = payload.aggregates?.[String(year)] || {};
          const aggregates = combineYearAggregates(yearData, types);
          const colorForEntry = (entry) => {
            if (!entry.types || entry.types.length === 0) {
              return {
                background: DEFAULT_COLORS[0],
                backgroundImage: "",
              };
            }
            if (entry.types.length === 1) {
              return {
                background: getColors(entry.types[0])[4],
                backgroundImage: "",
              };
            }
            return {
              background: getColors(entry.types[0])[4] || MULTI_TYPE_COLOR,
              backgroundImage: buildMultiTypeBackgroundImage(entry.types),
            };
          };
          const card = buildCard(
            "all",
            year,
            aggregates,
            currentUnits,
            {
              colorForEntry,
              metricHeatmapColor: frequencyCardColor,
              weekStart: setupWeekStart,
              cardMetricYear: year,
              initialMetricKey: getInitialYearMetricKey(year),
              onYearMetricStateChange,
              selectedTypes: types,
              typeBreakdownsByDate,
              typeLabelsByDate,
              activityLinksByDateType,
            },
          );
          setCardScrollKey(card, `${combinedSelectionKey}:year:${year}`);
          trackYearMetricAvailability(year, nextVisibleYearMetricYears);
          list.appendChild(buildLabeledCardRow(String(year), card, "year"));
        });
        section.appendChild(list);
        heatmaps.appendChild(section);
      } else {
        types.forEach((type) => {
          const section = document.createElement("div");
          section.className = "type-section";

          const list = document.createElement("div");
          list.className = "type-list";
          const yearTotals = getTypeYearTotals(payload, type, years);
          const cardYears = years.filter((year) => (yearTotals.get(year) || 0) > 0);
          const typeCardKey = `type:${type}`;
          if (showMoreStats) {
            const frequencyCard = buildStatsOverview(payload, [type], cardYears, frequencyCardColor, {
              units: currentUnits,
              initialFactKey: selectedFrequencyFactKey,
              initialMetricKey: initialFrequencyMetricKey,
              onFactStateChange: onFrequencyFactStateChange,
              onMetricStateChange: onFrequencyMetricStateChange,
            });
            setCardScrollKey(frequencyCard, `${typeCardKey}:frequency`);
            list.appendChild(
              buildLabeledCardRow(
                "Activity Frequency",
                frequencyCard,
                "frequency",
              ),
            );
          }
          cardYears.forEach((year) => {
            const aggregates = payload.aggregates?.[String(year)]?.[type] || {};
            const card = buildCard(type, year, aggregates, currentUnits, {
              metricHeatmapColor: getColors(type)[4],
              weekStart: setupWeekStart,
              cardMetricYear: year,
              initialMetricKey: getInitialYearMetricKey(year),
              onYearMetricStateChange,
              activityLinksByDateType,
            });
            setCardScrollKey(card, `${typeCardKey}:year:${year}`);
            trackYearMetricAvailability(year, nextVisibleYearMetricYears);
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
    filterableYearMetricsByYear = nextFilterableYearMetricsByYear;
    visibleYearMetricYears = nextVisibleYearMetricYears;
    visibleFrequencyFilterableFactKeys = nextVisibleFrequencyFilterableFactKeys;
    visibleFrequencyFilterableMetricKeys = nextVisibleFrequencyFilterableMetricKeys;
    if (!visibleFrequencyFilterableFactKeys.has(selectedFrequencyFactKey)) {
      selectedFrequencyFactKey = null;
    }
    if (!visibleFrequencyFilterableMetricKeys.has(selectedFrequencyMetricKey)) {
      selectedFrequencyMetricKey = null;
    }
    pruneYearMetricSelectionsByFilterability(selectedYearMetricByYear, filterableYearMetricsByYear);

    const activeSummaryYearMetricKey = getActiveSummaryMetricDisplayKey();
    if (activeSummaryYearMetricKey && hoverClearedSummaryYearMetricKey === activeSummaryYearMetricKey) {
      hoverClearedSummaryYearMetricKey = null;
    }
    syncResetAllButtonState();

    const showTypeBreakdown = payload.types.length > 0;
    const showActiveDays = Boolean(heatmaps);
    buildSummary(
      payload,
      types,
      years,
      currentUnits,
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
        selectedFrequencyFactKey = null;
        if (wasActiveMetricCard) {
          visibleYearMetricYears.forEach((year) => {
            setYearMetricSelection(year, null);
          });
          selectedFrequencyMetricKey = null;
        } else {
          hoverClearedSummaryYearMetricKey = null;
          visibleYearMetricYears.forEach((year) => {
            const filterableSet = filterableYearMetricsByYear.get(year) || new Set();
            setYearMetricSelection(year, filterableSet.has(metricKey) ? metricKey : null);
          });
          selectedFrequencyMetricKey = visibleFrequencyFilterableMetricKeys.has(metricKey)
            ? metricKey
            : null;
        }
        update();
      },
      (metricKey) => {
        if (hoverClearedSummaryYearMetricKey === metricKey) {
          hoverClearedSummaryYearMetricKey = null;
        }
      },
    );
    requestLayoutAlignment();
    if (previousCardScrollOffsets.size) {
      window.requestAnimationFrame(() => {
        restoreCardScrollOffsets(heatmaps, previousCardScrollOffsets);
      });
    }
    if (resetViewport && isNarrowLayoutViewport()) {
      window.requestAnimationFrame(() => {
        window.scrollTo({
          top: 0,
          left: 0,
          behavior: "auto",
        });
      });
    }
  }

  renderFilterButtons(typeButtons, typeOptions, (value) => {
    draftTypeMenuSelection = null;
    setMenuOpenState(typeMenu, typeMenuButton, false);
    toggleType(value);
    update();
  });
  if (typeMenuButton) {
    typeMenuButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = !typeMenu?.classList.contains("open");
      if (open) {
        draftTypeMenuSelection = cloneSelectionState(allTypesMode, selectedTypes);
      } else {
        draftTypeMenuSelection = null;
      }
      draftYearMenuSelection = null;
      setMenuOpenState(typeMenu, typeMenuButton, open);
      setMenuOpenState(yearMenu, yearMenuButton, false);
      update({ keepTypeMenuOpen: open, menuOnly: true, resetTypeMenuScroll: open });
    });
  }
  if (yearMenuButton) {
    yearMenuButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = !yearMenu?.classList.contains("open");
      if (open) {
        draftYearMenuSelection = cloneSelectionState(allYearsMode, selectedYears);
      } else {
        draftYearMenuSelection = null;
      }
      draftTypeMenuSelection = null;
      setMenuOpenState(yearMenu, yearMenuButton, open);
      setMenuOpenState(typeMenu, typeMenuButton, false);
      update({ keepYearMenuOpen: open, menuOnly: true, resetYearMenuScroll: open });
    });
  }
  if (typeClearButton) {
    typeClearButton.addEventListener("click", () => {
      const narrowLayout = isNarrowLayoutViewport();
      if (areAllTypesSelected()) {
        if (!payload.types.length) return;
        draftTypeMenuSelection = null;
        setMenuOpenState(typeMenu, typeMenuButton, false);
        allTypesMode = false;
        selectedTypes = new Set(payload.types);
        update();
        return;
      }
      draftTypeMenuSelection = null;
      setMenuOpenState(typeMenu, typeMenuButton, false);
      allTypesMode = true;
      selectedTypes.clear();
      update();
      if (narrowLayout) {
        typeClearButton.blur();
      }
    });
  }
  if (yearClearButton) {
    yearClearButton.addEventListener("click", () => {
      if (areAllYearsSelected()) return;
      draftYearMenuSelection = null;
      setMenuOpenState(yearMenu, yearMenuButton, false);
      allYearsMode = true;
      selectedYears.clear();
      update();
    });
  }
  if (imperialUnitsButton) {
    imperialUnitsButton.addEventListener("click", () => {
      setUnitSystem("imperial");
    });
  }
  if (metricUnitsButton) {
    metricUnitsButton.addEventListener("click", () => {
      setUnitSystem("metric");
    });
  }
  if (resetAllButton) {
    resetAllButton.addEventListener("click", () => {
      if (isDefaultFilterState()) {
        return;
      }
      draftTypeMenuSelection = null;
      draftYearMenuSelection = null;
      setMenuOpenState(typeMenu, typeMenuButton, false);
      setMenuOpenState(yearMenu, yearMenuButton, false);
      allTypesMode = true;
      selectedTypes.clear();
      allYearsMode = true;
      selectedYears.clear();
      selectedYearMetricByYear.clear();
      visibleYearMetricYears.clear();
      filterableYearMetricsByYear.clear();
      selectedFrequencyFactKey = null;
      visibleFrequencyFilterableFactKeys.clear();
      selectedFrequencyMetricKey = null;
      visibleFrequencyFilterableMetricKeys.clear();
      hoverClearedSummaryType = null;
      hoverClearedSummaryYearMetricKey = null;
      update({
        resetCardScroll: true,
        resetViewport: true,
      });
    });
  }

  document.addEventListener("pointerdown", (event) => {
    const target = event.target;
    let shouldRefreshMenus = false;
    if (typeMenu && !typeMenu.contains(target)) {
      if (typeMenu.classList.contains("open")) {
        setMenuOpenState(typeMenu, typeMenuButton, false);
        shouldRefreshMenus = true;
      }
      if (draftTypeMenuSelection) {
        draftTypeMenuSelection = null;
        shouldRefreshMenus = true;
      }
    }
    if (yearMenu && !yearMenu.contains(target)) {
      if (yearMenu.classList.contains("open")) {
        setMenuOpenState(yearMenu, yearMenuButton, false);
        shouldRefreshMenus = true;
      }
      if (draftYearMenuSelection) {
        draftYearMenuSelection = null;
        shouldRefreshMenus = true;
      }
    }
    if (shouldRefreshMenus) {
      update({ menuOnly: true });
    }
  });
  syncUnitToggleState();
  update();

  if (!useTouchInteractions && typeof window.ResizeObserver === "function" && !tooltipResizeObserver) {
    tooltipResizeObserver = new window.ResizeObserver(() => {
      if (!tooltip.classList.contains("visible")) return;
      if (!pendingTooltipPoint) return;
      positionTooltip(pendingTooltipPoint.x, pendingTooltipPoint.y);
    });
    tooltipResizeObserver.observe(tooltip);
  }

  if (document.fonts?.ready) {
    document.fonts.ready.then(() => {
      requestLayoutAlignment();
      if (!useTouchInteractions && tooltip.classList.contains("visible") && pendingTooltipPoint) {
        positionTooltip(pendingTooltipPoint.x, pendingTooltipPoint.y);
      }
    }).catch(() => {});
  }

  window.addEventListener("resize", () => {
    requestSummaryTypeTailCentering();
    if (resizeTimer) {
      window.clearTimeout(resizeTimer);
    }
    resizeTimer = window.setTimeout(() => {
      const width = window.innerWidth;
      const isNarrowLayout = isNarrowLayoutViewport();
      const widthChanged = Math.abs(width - lastViewportWidth) >= 1;
      const layoutModeChanged = isNarrowLayout !== lastIsNarrowLayout;
      syncOpenFilterMenuMaxHeights();
      if (!widthChanged && !layoutModeChanged) {
        return;
      }
      lastViewportWidth = width;
      lastIsNarrowLayout = isNarrowLayout;
      syncProfileLinkNavigationTarget();
      syncHeaderLinkPlacement();
      resetPersistentSideStatSizing();
      update();
    }, 150);
  });

  if (!useTouchInteractions) {
    tooltip.addEventListener("click", (event) => {
      handleTooltipLinkActivation(event);
    });

    document.addEventListener("pointerdown", (event) => {
      if (!isTooltipPinned()) return;
      const target = event.target;
      if (tooltip.contains(target)) {
        return;
      }
      if (pinnedTooltipCell && pinnedTooltipCell.contains(target)) {
        return;
      }
      dismissTooltipState();
    });

    const dismissTooltipOnDesktopViewportShift = () => {
      if (!isTooltipPinned()) return;
      dismissTooltipState();
    };

    document.addEventListener(
      "scroll",
      dismissTooltipOnDesktopViewportShift,
      { passive: true, capture: true },
    );

    window.addEventListener(
      "scroll",
      dismissTooltipOnDesktopViewportShift,
      { passive: true },
    );

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "visible") {
        dismissTooltipState();
      }
    });

    window.addEventListener("pagehide", () => {
      dismissTooltipState();
    });
  } else {
    tooltip.addEventListener(
      "touchstart",
      (event) => {
        rememberTooltipPointerType(event);
        event.stopPropagation();
        markTouchTooltipInteractionBlock(1200);
      },
      { passive: true },
    );
    tooltip.addEventListener("pointerdown", (event) => {
      rememberTooltipPointerType(event);
      event.stopPropagation();
      if (isTouchTooltipActivationEvent(event)) {
        markTouchTooltipInteractionBlock(1200);
      }
    });
    tooltip.addEventListener("click", (event) => {
      if (!handleTooltipLinkActivation(event)) {
        markTouchTooltipInteractionBlock(1200);
        event.stopPropagation();
        return;
      }
    });

    document.addEventListener("pointerdown", (event) => {
      if (!tooltip.classList.contains("visible")) return;
      const target = event.target;
      if (tooltip.contains(target)) {
        return;
      }
      if (!target.classList.contains("cell")) {
        dismissTooltipState();
      }
    });

    let lastTouchViewportScrollX = window.scrollX || window.pageXOffset || 0;
    let lastTouchViewportScrollY = window.scrollY || window.pageYOffset || 0;

    const dismissTooltipOnTouchScroll = (event) => {
      const scrollTarget = event?.target;
      const targetElement = scrollTarget?.nodeType === Node.TEXT_NODE
        ? scrollTarget.parentElement
        : scrollTarget;
      const cardScrollEvent = Boolean(
        targetElement
        && targetElement !== document
        && targetElement !== window
        && typeof targetElement.closest === "function"
        && targetElement.closest(".card"),
      );

      if (cardScrollEvent && tooltip.classList.contains("visible")) {
        dismissTooltipState();
        return;
      }

      const currentScrollX = window.scrollX || window.pageXOffset || 0;
      const currentScrollY = window.scrollY || window.pageYOffset || 0;
      const viewportMoved = Math.abs(currentScrollX - lastTouchViewportScrollX) >= 2
        || Math.abs(currentScrollY - lastTouchViewportScrollY) >= 2;
      lastTouchViewportScrollX = currentScrollX;
      lastTouchViewportScrollY = currentScrollY;

      if (!tooltip.classList.contains("visible")) {
        return;
      }

      // Always dismiss on actual page movement so touch pan/scroll never leaves stale tooltips.
      if (viewportMoved) {
        dismissTooltipState();
        return;
      }

      if (nowMs() <= touchTooltipInteractionBlockUntil || shouldIgnoreTouchTooltipDismiss()) {
        return;
      }
      dismissTooltipState();
    };

    document.addEventListener(
      "scroll",
      dismissTooltipOnTouchScroll,
      { passive: true, capture: true },
    );

    window.addEventListener(
      "scroll",
      dismissTooltipOnTouchScroll,
      { passive: true },
    );

    window.addEventListener(
      "resize",
      () => {
        dismissTooltipOnTouchScroll();
      },
      { passive: true },
    );

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "visible") {
        dismissTooltipState();
      }
    });

    window.addEventListener("pagehide", () => {
      dismissTooltipState();
    });
  }
}

init().catch((error) => {
  console.error(error);
  renderLoadError(error);
});
