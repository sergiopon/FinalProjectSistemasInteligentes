/**
 * Pure render functions for batch upload results and heatmap (spec 026).
 */

import { ASPECT_ORDER, countUp, el, stagger, formatPercent, formatScore, getAspectName } from "./common.js";
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
    kpi(t("kpiClassified"), response.decision_counts.classify, "text-green-600"),
    kpi(t("kpiReview"), response.decision_counts.review, "text-amber-600"),
    kpi(t("kpiModel"), response.model_version, "text-brand-700"),
  ]));
}

function renderHeatCell(cellData) {
  const base = "px-3 py-2 text-center text-sm";
  if (!cellData || cellData.mentions === 0) {
    return el("td", { class: `heat-none ${base}` }, ["–"]);
  }
  const step = heatStep(cellData.negative_share);
  const heatClass = HEAT_CLASSES[step] || "heat-none";
  const lowSupport = cellData.mentions < MIN_SUPPORT;
  return el("td", { class: `${heatClass} ${base}` }, [
    el("span", { class: "block font-semibold tabular-nums" }, [formatPercent(cellData.negative_share ?? 0)]),
    el("span", { class: `block text-xs tabular-nums opacity-80 ${lowSupport ? "italic" : ""}` }, [
      countText(cellData.mentions, t("mention"), t("mentions")),
    ]),
  ]);
}

export function renderHeatmap(courses) {
  const lang = getLang();
  const swatch = (cls, text) => el("li", { class: `${cls} rounded px-2 py-0.5 text-xs` }, [text]);
  const legend = el("ul", { class: "mt-3 flex flex-wrap items-center gap-2" }, [
    swatch("heat-0", "0–19 %"),
    swatch("heat-1", "20–39 %"),
    swatch("heat-2", "40–59 %"),
    swatch("heat-3", "60–79 %"),
    swatch("heat-4", "80–100 %"),
    swatch("heat-none", t("heatNone")),
    el("li", { class: "text-xs italic text-slate-500" }, [t("heatLowSupport")]),
  ]);

  const thClass = "px-3 py-2 text-left text-xs font-semibold text-slate-600";
  const headerCells = [
    el("th", { scope: "col", class: `${thClass} sticky left-0 bg-slate-50` }, [t("colCourse")]),
    ...ASPECT_ORDER.map((grp) => el("th", { scope: "col", class: `${thClass} min-w-[7rem]` }, [getAspectName(grp, lang)])),
  ];
  const thead = el("thead", { class: "bg-slate-50" }, [el("tr", {}, headerCells)]);

  const rows = courses.map((course) => {
    const cellsByGroup = new Map((course.aspects || []).map((asp) => [asp.group, asp]));
    return el("tr", { class: "border-t border-slate-200" }, [
      el(
        "th",
        { scope: "row", class: "sticky left-0 whitespace-nowrap bg-white px-3 py-2 text-left text-sm font-medium text-slate-800" },
        [course.course]
      ),
      ...ASPECT_ORDER.map((grp) => renderHeatCell(cellsByGroup.get(grp))),
    ]);
  });
  const table = el("table", { class: "w-full border-collapse" }, [thead, el("tbody", {}, rows)]);
  const scroll = el(
    "div",
    { class: "mt-4 overflow-x-auto rounded-lg border border-slate-200", role: "region", "aria-label": t("tableScroll"), tabindex: "0" },
    [table]
  );
  return el("section", { class: "card" }, [
    el("h3", { class: "text-base font-semibold text-slate-900" }, [t("heatTitle")]),
    el("p", { class: "mt-1 text-sm text-slate-500" }, [t("heatCaption")]),
    legend,
    scroll,
  ]);
}

function renderPriorities(priorities) {
  if (!priorities || priorities.length === 0) {
    return el("p", { class: "text-sm text-slate-500" }, [t("noPriorities")]);
  }
  const lang = getLang();
  const max = Math.max(...priorities.map((p) => p.score), 0.0001);
  const items = priorities.map((p, i) => {
    const bar = el("div", { class: "h-full rounded-full bg-brand-600 transition-all duration-700 ease-out" });
    bar.style.width = "0%";
    requestAnimationFrame(() => requestAnimationFrame(() => {
      bar.style.width = `${Math.round((p.score / max) * 100)}%`;
    }));
    const low = p.low_support ? `, ${t("lowSupport")}` : "";
    const detail = `${countText(p.mentions, t("mention"), t("mentions"))}, ${p.negative} ${t("negativeWord")}${low}`;
    return el("li", { class: "flex items-center gap-3" }, [
      el(
        "span",
        { class: "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-semibold text-white" },
        [String(i + 1)]
      ),
      el("div", { class: "min-w-0 flex-1" }, [
        el("div", { class: "flex flex-wrap items-baseline justify-between gap-x-3" }, [
          el("span", { class: "text-sm font-medium text-slate-800" }, [getAspectName(p.group, lang)]),
          el("span", { class: "text-xs tabular-nums text-slate-500" }, [`${t("score")} ${formatScore(p.score)} · ${detail}`]),
        ]),
        el("div", { class: "mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100" }, [bar]),
      ]),
    ]);
  });
  return el("ol", { class: "space-y-3" }, stagger(items, 80));
}

function quote(text) {
  return el(
    "blockquote",
    { class: "rounded-lg border-l-4 border-brand-600 bg-slate-50 px-3 py-2 text-sm italic text-slate-700" },
    [text]
  );
}

function renderTopics(topics) {
  if (!topics || topics.length === 0) {
    return el("p", { class: "text-sm text-slate-500" }, [t("noTopics")]);
  }
  const items = topics.map((tp) =>
    el("li", {}, [
      el("p", { class: "text-sm font-medium text-slate-800" }, [
        `${(tp.terms || []).join(", ")} `,
        el("span", { class: "font-normal text-slate-500" }, [`(${countText(tp.size, t("comment"), t("comments"))})`]),
      ]),
      quote(tp.quote),
    ])
  );
  return el("ul", { class: "space-y-2" }, items);
}

function renderQuotes(quotes) {
  if (!quotes || quotes.length === 0) {
    return el("p", { class: "text-sm text-slate-500" }, [t("noQuotes")]);
  }
  return el("div", { class: "space-y-2" }, quotes.map(quote));
}

function section(title, caption, body) {
  return el("div", {}, [
    el("h4", { class: "h-section" }, [title]),
    caption ? el("p", { class: "mb-3 mt-1 text-xs text-slate-500" }, [caption]) : el("div", { class: "mb-3" }),
    body,
  ]);
}

export function renderCourse(course) {
  const pc = course.polarity_counts || { negative: 0, neutral: 0, positive: 0 };
  const pill = (cls, n, word) => el("span", { class: `badge ${cls}` }, [`${n} ${word}`]);
  const info = `${countText(course.comment_count, t("comment"), t("comments"))}, ${course.review_count} ${t("courseInfo")}`;
  return el("section", { class: "card space-y-6" }, [
    el("div", { class: "flex flex-wrap items-center justify-between gap-3" }, [
      el("div", {}, [
        el("h3", { class: "text-lg font-semibold text-slate-900" }, [course.course]),
        el("p", { class: "text-sm text-slate-500" }, [info]),
      ]),
      el("div", { class: "flex flex-wrap gap-2" }, [
        pill("pol-negative", pc.negative, t("negativeWord")),
        pill("pol-neutral", pc.neutral, t("neutralWord")),
        pill("pol-positive", pc.positive, t("positiveWord")),
      ]),
    ]),
    el("div", { class: "grid gap-6 lg:grid-cols-2" }, [
      section(t("fixFirst"), t("fixFirstCaption"), renderPriorities(course.priorities)),
      section(t("topicsTitle"), null, renderTopics(course.topics)),
    ]),
    section(t("quotesTitle"), t("quotesCaption"), renderQuotes(course.quotes)),
  ]);
}
