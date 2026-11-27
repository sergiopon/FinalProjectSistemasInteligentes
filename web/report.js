/**
 * Pure render functions for batch upload results and heatmap (spec 026).
 */

import { ASPECT_ORDER, countUp, el, stagger, formatPercent, getAspectName } from "./common.js";
import { getLang, t } from "./i18n.js";

export const MIN_SUPPORT = 5;
export const HEAT_CLASSES = ["heat-0", "heat-1", "heat-2", "heat-3", "heat-4"];

export function heatStep(share) {
  if (share === null || share === undefined) {
    return null;
  }
  const pct = Math.round(share * 100);
  if (pct < 20) {
    return 0;
  }
  if (pct < 40) {
    return 1;
  }
  if (pct < 60) {
    return 2;
  }
  if (pct < 80) {
    return 3;
  }
  return 4;
}

function locale() {
  return getLang() === "es" ? "es-ES" : "en-US";
}

export function countText(count, singular, plural) {
  return `${count.toLocaleString(locale())} ${count === 1 ? singular : plural}`;
}

function kpi(label, value, tone = "text-slate-900") {
  const number = el("p", { class: `mt-1 text-2xl font-semibold tabular-nums ${tone}` }, [typeof value === "number" ? "0" : value]);
  if (typeof value === "number") {
    countUp(number, value, (n) => Math.round(n).toLocaleString(locale()));
  }
  return el("div", { class: "card lift !p-4" }, [el("p", { class: "h-section" }, [label]), number]);
}

export function renderSummary(response) {
  return el("div", { class: "grid grid-cols-2 gap-3 sm:grid-cols-4" }, stagger([
    kpi(t("kpiComments"), response.row_count),
    kpi(t("kpiClassified"), response.decision_counts.classify, "text-brand-700"),
    kpi(t("kpiReview"), response.decision_counts.review, "text-amber-600"),
    kpi(t("kpiModel"), response.model_version, "text-brand-700"),
  ]));
}

function renderHeatCell(course, cellData, group, onPick) {
  const base = "px-2 py-1 text-center text-sm";
  if (!cellData || cellData.mentions === 0) {
    return el("td", { class: `heat-none ${base}` }, ["–"]);
  }
  const lowSupport = cellData.mentions < MIN_SUPPORT;
  const heatClass = lowSupport ? "heat-none" : HEAT_CLASSES[heatStep(cellData.negative_share)] || "heat-none";
  const label = `${course.course}, ${getAspectName(group, getLang())}`;
  const button = el(
    "button",
    { type: "button", class: "block w-full rounded px-1 py-1 transition hover:ring-2 hover:ring-brand-600", "aria-label": label },
    [
      el("span", { class: `block font-semibold tabular-nums ${lowSupport ? "italic opacity-70" : ""}` }, [
        formatPercent(cellData.negative_share ?? 0),
      ]),
      el("span", { class: "block text-xs tabular-nums opacity-80" }, [
        lowSupport ? t("lowDataCell") : countText(cellData.mentions, t("mention"), t("mentions")),
      ]),
    ]
  );
  button.addEventListener("click", () => onPick(course.course, group));
  return el("td", { class: `${heatClass} ${base}` }, [button]);
}

export function renderHeatmap(courses, onPick) {
  const lang = getLang();
  const swatch = (cls, text) => el("li", { class: `${cls} rounded px-2 py-0.5 text-xs` }, [text]);
  const legend = el("ul", { class: "mt-3 flex flex-wrap items-center gap-2" }, [
    swatch("heat-0", "0–19 %"),
    swatch("heat-1", "20–39 %"),
    swatch("heat-2", "40–59 %"),
    swatch("heat-3", "60–79 %"),
    swatch("heat-4", "80–100 %"),
    swatch("heat-none", t("heatNone")),
  ]);
  const thClass = "px-1 py-2 text-left text-[11px] font-semibold leading-tight text-slate-600 align-bottom break-words";
  const headerCells = [
    el("th", { scope: "col", class: `${thClass} bg-slate-50` }, [t("colCourse")]),
    ...ASPECT_ORDER.map((grp) => el("th", { scope: "col", class: thClass }, [getAspectName(grp, lang)])),
  ];
  const thead = el("thead", { class: "bg-slate-50" }, [el("tr", {}, headerCells)]);
  const rows = courses.map((course) => {
    const cellsByGroup = new Map((course.aspects || []).map((asp) => [asp.group, asp]));
    return el("tr", { class: "border-t border-slate-200" }, [
      el("th", { scope: "row", class: "break-words bg-white px-2 py-1 text-left text-xs font-medium text-slate-800" }, [course.course]),
      ...ASPECT_ORDER.map((grp) => renderHeatCell(course, cellsByGroup.get(grp), grp, onPick)),
    ]);
  });
  const table = el("table", { class: "w-full table-fixed border-collapse" }, [thead, el("tbody", {}, rows)]);
  return el("section", { class: "card" }, [
    el("h3", { class: "text-base font-semibold text-slate-900" }, [t("heatTitle")]),
    el("p", { class: "mt-1 text-sm text-slate-500" }, [t("heatCaption")]),
    el("p", { class: "mt-1 text-sm font-medium text-brand-700" }, [t("heatPick")]),
    legend,
    el("div", { class: "mt-4 overflow-x-auto rounded-lg border border-slate-200", role: "region", "aria-label": t("tableScroll"), tabindex: "0" }, [table]),
  ]);
}
