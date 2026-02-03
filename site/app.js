const CELL = 12;
const GAP = 2;
const LABEL_LEFT = 36;
const LABEL_TOP = 20;

const DEFAULT_COLORS = ["#edf8f7", "#bce9e4", "#76d7cf", "#2bb7a5", "#0b7f6d"];
const TYPE_COLORS = {
  Run: ["#eef6ff", "#bfe3ff", "#7ac7ff", "#2f97ff", "#005ae6"],
  Ride: ["#fff4e6", "#ffd6a1", "#ffad4d", "#ff7a1a", "#d14b00"],
  WeightTraining: ["#f4e9ff", "#d8b8ff", "#b17bff", "#8a3ffc", "#5f17d6"],
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const typeSelect = document.getElementById("typeSelect");
const yearSelect = document.getElementById("yearSelect");
const heatmaps = document.getElementById("heatmaps");
const tooltip = document.getElementById("tooltip");
const summary = document.getElementById("summary");
const updated = document.getElementById("updated");

function level(count, maxCount) {
  if (count <= 0 || maxCount <= 0) return 0;
  if (maxCount === 1) return 1;
  const ratio = count / maxCount;
  let lvl = Math.floor(ratio * 3) + 1;
  if (lvl > 4) lvl = 4;
  return lvl;
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
  tooltip.style.left = `${x + 12}px`;
  tooltip.style.top = `${y + 12}px`;
  tooltip.classList.add("visible");
}

function hideTooltip() {
  tooltip.classList.remove("visible");
}

function getColors(type) {
  return TYPE_COLORS[type] || DEFAULT_COLORS;
}

function formatDistance(meters, units) {
  if (units.distance === "km") {
    return `${(meters / 1000).toFixed(1)} km`;
  }
  return `${(meters / 1609.344).toFixed(1)} mi`;
}

function formatDuration(seconds) {
  const minutes = Math.round(seconds / 60);
  if (minutes >= 60) {
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }
  return `${minutes}m`;
}

function buildLegend(colors) {
  const legend = document.createElement("div");
  legend.className = "legend";
  const label = document.createElement("span");
  label.textContent = "Less";
  legend.appendChild(label);
  colors.forEach((color) => {
    const swatch = document.createElement("span");
    swatch.style.background = color;
    legend.appendChild(swatch);
  });
  const more = document.createElement("span");
  more.textContent = "More";
  legend.appendChild(more);
  return legend;
}

function buildSummary(payload) {
  summary.innerHTML = "";

  const totals = {
    count: 0,
    distance: 0,
    moving_time: 0,
  };
  const typeTotals = {};
  const activeDays = new Set();

  Object.entries(payload.aggregates || {}).forEach(([year, yearData]) => {
    Object.entries(yearData || {}).forEach(([type, entries]) => {
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
        typeTotals[type].count += entry.count || 0;
      });
    });
  });

  const cards = [
    { title: "Total Workouts", value: totals.count.toLocaleString() },
    { title: "Total Distance", value: formatDistance(totals.distance, payload.units || { distance: "mi" }) },
    { title: "Total Time", value: formatDuration(totals.moving_time) },
    { title: "Active Days", value: activeDays.size.toLocaleString() },
  ];

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

  payload.types.forEach((type) => {
    const typeCard = document.createElement("div");
    typeCard.className = "summary-card";
    const title = document.createElement("div");
    title.className = "summary-title";
    title.textContent = `${type} Workouts`;
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

function buildHeatmapArea(aggregates, year, units, colors, type) {
  const heatmapArea = document.createElement("div");
  heatmapArea.className = "heatmap-area";

  const yearLabel = document.createElement("div");
  yearLabel.className = "year-label";
  yearLabel.textContent = year;
  heatmapArea.appendChild(yearLabel);

  const yearStart = new Date(year, 0, 1);
  const yearEnd = new Date(year, 11, 31);
  const start = mondayOnOrBefore(yearStart);
  const end = sundayOnOrAfter(yearEnd);

  const entries = Object.values(aggregates || {});
  const maxCount = entries.reduce((max, entry) => Math.max(max, entry.count || 0), 0);

  for (let month = 0; month < 12; month += 1) {
    const monthStart = new Date(year, month, 1);
    const weekIndex = Math.floor((monthStart - start) / (1000 * 60 * 60 * 24 * 7));
    const monthLabel = document.createElement("div");
    monthLabel.className = "month-label";
    monthLabel.textContent = MONTHS[month];
    monthLabel.style.left = `${LABEL_LEFT + weekIndex * (CELL + GAP)}px`;
    heatmapArea.appendChild(monthLabel);
  }

  DAYS.forEach((label, row) => {
    const dayLabel = document.createElement("div");
    dayLabel.className = "day-label";
    dayLabel.textContent = label;
    dayLabel.style.left = `${LABEL_LEFT - 6}px`;
    dayLabel.style.top = `${LABEL_TOP + row * (CELL + GAP) + 2}px`;
    heatmapArea.appendChild(dayLabel);
  });

  const grid = document.createElement("div");
  grid.className = "grid";
  grid.style.marginLeft = `${LABEL_LEFT}px`;
  grid.style.marginTop = `${LABEL_TOP}px`;

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

    const lvl = level(entry.count || 0, maxCount);
    cell.style.background = colors[lvl];

    const durationMinutes = Math.round((entry.moving_time || 0) / 60);
    const duration = durationMinutes >= 60
      ? `${Math.floor(durationMinutes / 60)}h ${durationMinutes % 60}m`
      : `${durationMinutes}m`;

    const lines = [
      dateStr,
      `${entry.count} workout${entry.count === 1 ? "" : "s"}`,
    ];

    if (type !== "WeightTraining") {
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

    cell.addEventListener("mouseenter", (event) => {
      showTooltip(tooltipText, event.clientX, event.clientY);
    });
    cell.addEventListener("mousemove", (event) => {
      showTooltip(tooltipText, event.clientX, event.clientY);
    });
    cell.addEventListener("mouseleave", hideTooltip);

    grid.appendChild(cell);
  }

  heatmapArea.appendChild(grid);
  return heatmapArea;
}

function buildCard(type, year, aggregates, units) {
  const card = document.createElement("div");
  card.className = "card";

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = `${type} · ${year}`;
  card.appendChild(title);

  const colors = getColors(type);
  const heatmapArea = buildHeatmapArea(aggregates, year, units, colors, type);
  card.appendChild(heatmapArea);
  card.appendChild(buildLegend(colors));

  return card;
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

  buildSummary(payload);

  const allTypesOption = document.createElement("option");
  allTypesOption.value = "all";
  allTypesOption.textContent = "All types";
  typeSelect.appendChild(allTypesOption);

  payload.types.forEach((type) => {
    const opt = document.createElement("option");
    opt.value = type;
    opt.textContent = type;
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

  function update() {
    const selectedType = typeSelect.value;
    const selectedYear = yearSelect.value;
    const types = selectedType === "all" ? payload.types : [selectedType];
    const years = selectedYear === "all" ? payload.years : [Number(selectedYear)];
    years.sort((a, b) => b - a);

    heatmaps.innerHTML = "";
    types.forEach((type) => {
      years.forEach((year) => {
        const aggregates = payload.aggregates?.[String(year)]?.[type] || {};
        const card = buildCard(type, year, aggregates, payload.units || { distance: "mi", elevation: "ft" });
        heatmaps.appendChild(card);
      });
    });
  }

  typeSelect.addEventListener("change", update);
  yearSelect.addEventListener("change", update);

  typeSelect.value = "all";
  yearSelect.value = "all";
  update();
}

init().catch((error) => {
  console.error(error);
});
