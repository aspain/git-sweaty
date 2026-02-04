const DEFAULT_COLORS = ["#f3f5f8", "#dfeae4", "#bdd8cf", "#8ebfad", "#5f9f8a"];
const TYPE_COLORS = {
  Run: ["#f3f5f8", "#dee8f6", "#bfcfe9", "#93aed7", "#5d82c1"],
  Ride: ["#f3f5f8", "#dff1e7", "#bcdcc9", "#8cbda2", "#5c9674"],
  WeightTraining: ["#f3f5f8", "#f3dddd", "#e7bcbc", "#d59393", "#b66565"],
};
const MULTI_TYPE_COLOR = "#7b6fb3";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const typeSelect = document.getElementById("typeSelect");
const yearSelect = document.getElementById("yearSelect");
const heatmaps = document.getElementById("heatmaps");
const tooltip = document.getElementById("tooltip");
const summary = document.getElementById("summary");
const updated = document.getElementById("updated");
const isTouch = window.matchMedia("(hover: none) and (pointer: coarse)").matches;

function readCssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function getLayout() {
  return {
    cell: readCssVar("--cell", 12),
    gap: readCssVar("--gap", 2),
    gridPadTop: readCssVar("--grid-pad-top", 6),
    gridPadLeft: readCssVar("--grid-pad-left", 6),
  };
}

function mondayOnOrBefore(d) {
  const day = d.getDay();
  const offset = (day + 6) % 7; // convert Sunday=0 to 6, Monday=1 to 0
  const result = new Date(d);
  result.setDate(d.getDate() - offset);
  return result;
}

function sundayOnOrAfter(d) {
  const day = d.getDay();
  const offset = (7 - day) % 7;
  const result = new Date(d);
  result.setDate(d.getDate() + offset);
  return result;
}

function showTooltip(text, x, y) {
  tooltip.textContent = text;
  if (isTouch) {
    tooltip.classList.add("touch");
    tooltip.style.left = "50%";
    tooltip.style.top = "auto";
    tooltip.style.bottom = "16px";
    tooltip.style.transform = "translateX(-50%)";
  } else {
    tooltip.classList.remove("touch");
    tooltip.style.left = `${x + 12}px`;
    tooltip.style.top = `${y + 12}px`;
    tooltip.style.bottom = "auto";
    tooltip.style.transform = "translateY(-8px)";
  }
  tooltip.classList.add("visible");
}

function hideTooltip() {
  tooltip.classList.remove("visible");
}

function getColors(type) {
  return TYPE_COLORS[type] || DEFAULT_COLORS;
}

function displayType(type) {
  if (type === "WeightTraining") return "Weight Training";
  return type;
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
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }
  return `${minutes}m`;
}

function formatElevation(meters, units) {
  if (units.elevation === "m") {
    return `${formatNumber(Math.round(meters), 0)} m`;
  }
  return `${formatNumber(Math.round(meters * 3.28084), 0)} ft`;
}

function buildSummary(payload, types, years, showTypeBreakdown, showActiveDays, hideDistanceElevation) {
  summary.innerHTML = "";

  const totals = {
    count: 0,
    distance: 0,
    moving_time: 0,
    elevation: 0,
  };
  const typeTotals = {};
  const activeDays = new Set();

  Object.entries(payload.aggregates || {}).forEach(([year, yearData]) => {
    if (!years.includes(Number(year))) return;
    Object.entries(yearData || {}).forEach(([type, entries]) => {
      if (!types.includes(type)) return;
      if (!typeTotals[type]) {
        typeTotals[type] = { count: 0 };
      }
      Object.entries(entries || {}).forEach(([dateStr, entry]) => {
        if ((entry.count || 0) > 0) {
          activeDays.add(dateStr);
        }
        totals.count += entry.count || 0;
        totals.distance += entry.distance || 0;
        totals.moving_time += entry.moving_time || 0;
        totals.elevation += entry.elevation_gain || 0;
        typeTotals[type].count += entry.count || 0;
      });
    });
  });

  const cards = [
    { title: "Total Workouts", value: totals.count.toLocaleString() },
  ];
  if (!hideDistanceElevation) {
    cards.push({
      title: "Total Distance",
      value: formatDistance(totals.distance, payload.units || { distance: "mi" }),
    });
    cards.push({
      title: "Total Elevation",
      value: formatElevation(totals.elevation, payload.units || { elevation: "ft" }),
    });
  }
  cards.push({ title: "Total Time", value: formatDuration(totals.moving_time) });
  if (showActiveDays) {
    cards.push({ title: "Active Days", value: activeDays.size.toLocaleString() });
  }

  cards.forEach((card) => {
    const el = document.createElement("div");
    el.className = "summary-card";
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

  if (showTypeBreakdown) {
    types.forEach((type) => {
      const typeCard = document.createElement("div");
      typeCard.className = "summary-card";
      const title = document.createElement("div");
      title.className = "summary-title";
      title.textContent = `${displayType(type)} Workouts`;
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
      summary.appendChild(typeCard);
    });
  }
}

function buildHeatmapArea(aggregates, year, units, colors, type, layout, options = {}) {
  const heatmapArea = document.createElement("div");
  heatmapArea.className = "heatmap-area";

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
  const start = mondayOnOrBefore(yearStart);
  const end = sundayOnOrAfter(yearEnd);

  for (let month = 0; month < 12; month += 1) {
    const monthStart = new Date(year, month, 1);
    const weekIndex = Math.floor((monthStart - start) / (1000 * 60 * 60 * 24 * 7));
    const monthLabel = document.createElement("div");
    monthLabel.className = "month-label";
    monthLabel.textContent = MONTHS[month];
    monthLabel.style.left = `${weekIndex * (layout.cell + layout.gap)}px`;
    monthRow.appendChild(monthLabel);
  }

  const grid = document.createElement("div");
  grid.className = "grid";

  for (let day = new Date(start); day <= end; day.setDate(day.getDate() + 1)) {
    const dateStr = day.toISOString().slice(0, 10);
    const inYear = day.getFullYear() === year;
    const entry = (aggregates && aggregates[dateStr]) || {
      count: 0,
      distance: 0,
      moving_time: 0,
      elevation_gain: 0,
      activity_ids: [],
    };

    const weekIndex = Math.floor((day - start) / (1000 * 60 * 60 * 24 * 7));
    const row = (day.getDay() + 6) % 7; // Monday=0

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
    if (filled && typeof options.colorForEntry === "function") {
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
      `${entry.count} workout${entry.count === 1 ? "" : "s"}`,
    ];

    const showDistanceElevation = (() => {
      if (type === "WeightTraining") return false;
      if (type === "all") {
        if (entry.types && entry.types.length === 1 && entry.types[0] === "WeightTraining") {
          return false;
        }
      }
      return true;
    })();

    if (type === "all" && entry.types && entry.types.length) {
      lines.push(`Types: ${entry.types.map(displayType).join(", ")}`);
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

function buildCard(type, year, aggregates, units, options = {}) {
  const card = document.createElement("div");
  card.className = "card";

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = String(year);
  card.appendChild(title);

  const body = document.createElement("div");
  body.className = "card-body";

  const colors = type === "all" ? DEFAULT_COLORS : getColors(type);
  const layout = getLayout();
  const heatmapArea = buildHeatmapArea(aggregates, year, units, colors, type, layout, options);
  body.appendChild(heatmapArea);

  const stats = document.createElement("div");
  stats.className = "card-stats";
  const totals = {
    count: 0,
    distance: 0,
    moving_time: 0,
    elevation: 0,
  };
  const activeDays = new Set();
  Object.entries(aggregates || {}).forEach(([dateStr, entry]) => {
    if ((entry.count || 0) > 0) {
      activeDays.add(dateStr);
    }
    totals.count += entry.count || 0;
    totals.distance += entry.distance || 0;
    totals.moving_time += entry.moving_time || 0;
    totals.elevation += entry.elevation_gain || 0;
  });

  const statItems = [
    { label: "Total Workouts", value: totals.count.toLocaleString() },
    { label: "Active Days", value: activeDays.size.toLocaleString() },
    { label: "Total Time", value: formatDuration(totals.moving_time) },
  ];

  const hideDistanceElevation = type === "WeightTraining";
  if (!hideDistanceElevation) {
    statItems.splice(2, 0, {
      label: "Total Distance",
      value: formatDistance(totals.distance, units || { distance: "mi" }),
    });
    statItems.push({
      label: "Total Elevation",
      value: formatElevation(totals.elevation, units || { elevation: "ft" }),
    });
  }

  statItems.forEach((item) => {
    const stat = document.createElement("div");
    stat.className = "card-stat";
    const label = document.createElement("div");
    label.className = "card-stat-label";
    label.textContent = item.label;
    const value = document.createElement("div");
    value.className = "card-stat-value";
    value.textContent = item.value;
    stat.appendChild(label);
    stat.appendChild(value);
    stats.appendChild(stat);
  });

  body.appendChild(stats);
  card.appendChild(body);
  return card;
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

async function init() {
  const resp = await fetch("data.json");
  const payload = await resp.json();

  if (payload.generated_at) {
    const updatedAt = new Date(payload.generated_at);
    if (!Number.isNaN(updatedAt.getTime())) {
      updated.textContent = `Last updated: ${updatedAt.toLocaleString()}`;
    }
  }

  const allTypesOption = document.createElement("option");
  allTypesOption.value = "all";
  allTypesOption.textContent = "All types";
  typeSelect.appendChild(allTypesOption);

  payload.types.forEach((type) => {
    const opt = document.createElement("option");
    opt.value = type;
    opt.textContent = displayType(type);
    typeSelect.appendChild(opt);
  });

  const allYearsOption = document.createElement("option");
  allYearsOption.value = "all";
  allYearsOption.textContent = "All years";
  yearSelect.appendChild(allYearsOption);

  payload.years.slice().reverse().forEach((year) => {
    const opt = document.createElement("option");
    opt.value = year;
    opt.textContent = year;
    yearSelect.appendChild(opt);
  });

  let resizeTimer = null;

  function update() {
    const selectedType = typeSelect.value;
    const selectedYear = yearSelect.value;
    const types = selectedType === "all" ? payload.types : [selectedType];
    const years = selectedYear === "all" ? payload.years : [Number(selectedYear)];
    years.sort((a, b) => b - a);

    heatmaps.innerHTML = "";
    if (selectedType === "all") {
      const section = document.createElement("div");
      section.className = "type-section";
      const header = document.createElement("div");
      header.className = "type-header";
      header.textContent = "All Workouts";
      section.appendChild(header);

      const list = document.createElement("div");
      list.className = "type-list";
      years.forEach((year) => {
        const yearData = payload.aggregates?.[String(year)] || {};
        const aggregates = combineYearAggregates(yearData, types);
        const colorForEntry = (entry) => {
          if (!entry.types || entry.types.length === 0) {
            return DEFAULT_COLORS[0];
          }
          if (entry.types.length === 1) {
            return getColors(entry.types[0])[4];
          }
          return MULTI_TYPE_COLOR;
        };
        const card = buildCard(
          "all",
          year,
          aggregates,
          payload.units || { distance: "mi", elevation: "ft" },
          { colorForEntry },
        );
        list.appendChild(card);
      });
      section.appendChild(list);
      heatmaps.appendChild(section);
    } else {
      types.forEach((type) => {
        const section = document.createElement("div");
        section.className = "type-section";
        const header = document.createElement("div");
        header.className = "type-header";
        header.textContent = displayType(type);
        section.appendChild(header);

        const list = document.createElement("div");
        list.className = "type-list";
        years.forEach((year) => {
          const aggregates = payload.aggregates?.[String(year)]?.[type] || {};
          const card = buildCard(type, year, aggregates, payload.units || { distance: "mi", elevation: "ft" });
          list.appendChild(card);
        });
        if (!list.childElementCount) {
          return;
        }
        section.appendChild(list);
        heatmaps.appendChild(section);
      });
    }

    const showTypeBreakdown = selectedType === "all";
    const showActiveDays = selectedType === "all" && selectedYear === "all";
    const hideDistanceElevation = selectedType === "WeightTraining";
    buildSummary(payload, types, years, showTypeBreakdown, showActiveDays, hideDistanceElevation);
  }

  typeSelect.addEventListener("change", update);
  yearSelect.addEventListener("change", update);

  typeSelect.value = "all";
  yearSelect.value = "all";
  update();

  window.addEventListener("resize", () => {
    if (resizeTimer) {
      window.clearTimeout(resizeTimer);
    }
    resizeTimer = window.setTimeout(() => {
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
});
