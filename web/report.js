/**
 * Pure render functions for batch upload results and heatmap (spec 026).
 */

import { ASPECT_NAMES, ASPECT_ORDER, el, formatPercent, formatScore, getAspectName } from "./common.js";
import { getLang } from "./i18n.js";

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

export function countText(count, singular, plural) {
  return `${count.toLocaleString("en-US")} ${count === 1 ? singular : plural}`;
}

export function renderSummary(response) {
  const rowCountText = countText(response.row_count, "comment", "comments");
  const classifyCount = response.decision_counts.classify.toLocaleString("en-US");
  const reviewCount = response.decision_counts.review.toLocaleString("en-US");
  const text = `${rowCountText} analyzed: ${classifyCount} classified, ${reviewCount} sent to review. Model ${response.model_version}.`;
  return el("p", {}, [text]);
}

function renderHeatCell(cellData) {
  if (!cellData || cellData.mentions === 0) {
    return el("td", { class: "heat-none" }, ["No mentions"]);
  }
  const step = heatStep(cellData.negative_share);
  const heatClass = HEAT_CLASSES[step] || "heat-none";
  const shareSpan = el("span", { class: "cell-share num" }, [
    formatPercent(cellData.negative_share ?? 0),
  ]);
  const countSpanClass = cellData.mentions < MIN_SUPPORT ? "cell-count num low-support" : "cell-count num";
  const countSpan = el("span", { class: countSpanClass }, [
    countText(cellData.mentions, "mention", "mentions"),
  ]);
  return el("td", { class: heatClass }, [shareSpan, countSpan]);
}

export function renderHeatmap(courses) {
  const legendItems = [
    el("li", {}, [el("span", { class: "swatch heat-0" }, ["0 to 19 %"])]),
    el("li", {}, [el("span", { class: "swatch heat-1" }, ["20 to 39 %"])]),
    el("li", {}, [el("span", { class: "swatch heat-2" }, ["40 to 59 %"])]),
    el("li", {}, [el("span", { class: "swatch heat-3" }, ["60 to 79 %"])]),
    el("li", {}, [el("span", { class: "swatch heat-4" }, ["80 to 100 %"])]),
    el("li", {}, [el("span", { class: "swatch heat-none" }, ["No mentions"])]),
    el("li", {}, [el("em", {}, ["Count in italics"]), ": Fewer than 5 mentions"]),
  ];
  const legend = el("ul", { class: "legend" }, legendItems);

  const headerCells = [
    el("th", { scope: "col" }, ["Course"]),
    ...ASPECT_ORDER.map((grp) => el("th", { scope: "col" }, [getAspectName(grp, getLang())])),
  ];
  const thead = el("thead", {}, [el("tr", {}, headerCells)]);

  const rows = courses.map((course) => {
    const cellsByGroup = new Map(
      (course.aspects || []).map((asp) => [asp.group, asp])
    );
    const rowCells = [
      el("th", { scope: "row" }, [course.course]),
      ...ASPECT_ORDER.map((grp) => renderHeatCell(cellsByGroup.get(grp))),
    ];
    return el("tr", {}, rowCells);
  });
  const tbody = el("tbody", {}, rows);
  const table = el("table", { class: "heatmap" }, [thead, tbody]);

  const scrollRegion = el(
    "div",
    {
      class: "table-scroll",
      role: "region",
      "aria-label": "Heatmap table, scrolls sideways",
      tabindex: "0",
    },
    [table]
  );

  return el("section", {}, [
    el("h3", {}, ["Negative share by course and aspect"]),
    el("p", { class: "caption" }, [
      "Each cell shows the share of mentions with negative sentiment and the number of mentions.",
    ]),
    legend,
    scrollRegion,
  ]);
}

function renderPriorities(priorities) {
  if (!priorities || priorities.length === 0) {
    return [el("p", {}, ["No aspect was mentioned in this course."])];
  }
  const items = priorities.map((p) => {
    const name = getAspectName(p.group, getLang());
    const mentionsText = countText(p.mentions, "mention", "mentions");
    const supportSuffix = p.low_support ? ", fewer than 5 mentions" : "";
    const text = `${name}, score ${formatScore(p.score)} (${mentionsText}, ${p.negative} negative${supportSuffix})`;
    return el("li", {}, [text]);
  });
  return [el("ol", { class: "priorities" }, items)];
}

function renderTopics(topics) {
  if (!topics || topics.length === 0) {
    return [el("p", {}, ["No topics were found for this course."])];
  }
  const items = topics.map((t) => {
    const terms = (t.terms || []).join(", ");
    const text = `${terms} (${countText(t.size, "comment", "comments")})`;
    const bquote = el("blockquote", {}, [t.quote]);
    return el("li", {}, [text, bquote]);
  });
  return [el("ul", {}, items)];
}

function renderQuotes(quotes) {
  if (!quotes || quotes.length === 0) {
    return [el("p", {}, ["No representative comments for this course."])];
  }
  return quotes.map((q) => el("blockquote", {}, [q]));
}

export function renderCourse(course) {
  const commentText = countText(course.comment_count, "comment", "comments");
  const pcounts = course.polarity_counts || { negative: 0, neutral: 0, positive: 0 };
  const infoText = `${commentText}, ${course.review_count} sent to review. Polarity: ${pcounts.negative} negative, ${pcounts.neutral} neutral, ${pcounts.positive} positive.`;

  return el("section", { class: "course" }, [
    el("h3", {}, [course.course]),
    el("p", {}, [infoText]),
    el("h4", {}, ["What to fix first"]),
    el("p", { class: "caption" }, [
      "Ranked by how often an aspect is mentioned times its smoothed negative share.",
    ]),
    ...renderPriorities(course.priorities),
    el("h4", {}, ["Topics"]),
    ...renderTopics(course.topics),
    el("h4", {}, ["Representative comments"]),
    el("p", { class: "caption" }, [
      "Names, emails, phone numbers and id numbers are masked.",
    ]),
    ...renderQuotes(course.quotes),
  ]);
}
