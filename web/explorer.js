/**
 * Course explorer: pick a course, see what to fix first and read the matching comments.
 */

import { ASPECT_ORDER, el, getAspectName } from "./common.js";
import { getLang, polName, t } from "./i18n.js";
import { MIN_SUPPORT, countText } from "./report.js";

const PAGE_SIZE = 25;
const TOP_PROBLEMS = 3;
const SELECT_CLASS =
  "min-h-[38px] rounded-lg border border-slate-300 bg-white px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500";

export function fill(template, values) {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));
}

function matchesAspect(row, group) {
  return (row.aspects || []).find((asp) => asp.group === group);
}

export function filterRows(rows, state) {
  const query = state.query.trim().toLowerCase();
  return rows.filter((row) => {
    if (state.course && row.course !== state.course) {
      return false;
    }
    let polarity = row.predicted;
    if (state.aspect) {
      const asp = matchesAspect(row, state.aspect);
      if (!asp) {
        return false;
      }
      polarity = asp.polarity;
    }
    if (state.polarity && polarity !== state.polarity) {
      return false;
    }
    return query === "" || row.text.toLowerCase().includes(query);
  });
}

function chip(label, active, onClick) {
  const cls = active
    ? "border-brand-600 bg-brand-600 text-white"
    : "border-slate-300 bg-white text-slate-700 hover:border-brand-500 hover:text-brand-700";
  const button = el(
    "button",
    { type: "button", class: `rounded-full border px-3 py-1 text-sm font-medium transition ${cls}`, "aria-pressed": String(active) },
    [label]
  );
  button.addEventListener("click", onClick);
  return button;
}

export function createExplorer(response) {
  const state = { course: null, aspect: null, polarity: "", query: "", shown: PAGE_SIZE };
  const root = el("section", { class: "card space-y-5", id: "explorer" });
  const listSlot = el("div", {});

  function update(patch) {
    Object.assign(state, patch, { shown: PAGE_SIZE });
    render();
  }

  function courseChips() {
    const chips = [chip(t("allCourses"), state.course === null, () => update({ course: null }))];
    for (const course of response.courses) {
      chips.push(chip(course.course, state.course === course.course, () => update({ course: course.course })));
    }
    return el("div", { class: "flex flex-wrap gap-2" }, chips);
  }

  function problemItem(entry, rank) {
    const share = entry.mentions > 0 ? entry.negative / entry.mentions : 0;
    const bar = el("div", { class: "h-full rounded-full bg-brand-600" });
    bar.style.width = `${Math.round(share * 100)}%`;
    const low = entry.low_support ? el("span", { class: "ml-2 text-xs italic text-slate-500" }, [t("lowDataNote")]) : null;
    const open = el("button", { type: "button", class: "btn !min-h-[34px] !px-3 text-xs" }, [t("viewComments")]);
    open.addEventListener("click", () => update({ aspect: entry.group, polarity: "negative" }));
    return el("li", { class: "flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3" }, [
      el("span", { class: "flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white" }, [String(rank)]),
      el("div", { class: "min-w-0 flex-1" }, [
        el("p", { class: "text-sm font-medium text-slate-900" }, [
          getAspectName(entry.group, getLang()),
          el("span", { class: "ml-2 font-normal text-slate-500" }, [
            fill(t("negOf"), { neg: entry.negative, total: entry.mentions }),
          ]),
          low,
        ]),
        el("div", { class: "mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100" }, [bar]),
      ]),
      open,
    ]);
  }

  function courseSummary() {
    const course = response.courses.find((c) => c.course === state.course);
    if (!course) {
      return el("p", { class: "rounded-lg bg-slate-50 p-3 text-sm text-slate-600" }, [t("exploreHint")]);
    }
    const priorities = course.priorities || [];
    if (priorities.length === 0) {
      return el("p", { class: "text-sm text-slate-500" }, [t("noPriorities")]);
    }
    const top = priorities[0];
    const lead = fill(t("urgentLead"), {
      course: course.course,
      aspect: getAspectName(top.group, getLang()),
      neg: top.negative,
      total: top.mentions,
    });
    const rest = priorities.slice(TOP_PROBLEMS);
    const items = priorities.slice(0, TOP_PROBLEMS).map((entry, i) => problemItem(entry, i + 1));
    return el("div", { class: "space-y-3" }, [
      el("p", { class: "rounded-lg bg-brand-50 p-3 text-sm font-medium text-brand-900" }, [lead]),
      el("h4", { class: "h-section" }, [t("fixFirst")]),
      el("p", { class: "text-xs text-slate-500" }, [t("fixFirstCaption")]),
      el("ol", { class: "space-y-2" }, items),
      rest.length
        ? el("details", { class: "text-sm" }, [
            el("summary", { class: "cursor-pointer text-brand-700" }, [t("otherAspects")]),
            el("ol", { class: "mt-2 space-y-2" }, rest.map((entry, i) => problemItem(entry, i + 1 + TOP_PROBLEMS))),
          ])
        : null,
    ]);
  }

  function filters() {
    const aspect = el("select", { class: SELECT_CLASS, "aria-label": t("filterAspect") }, [
      el("option", { value: "" }, [t("allAspects")]),
      ...ASPECT_ORDER.map((g) => el("option", { value: g }, [getAspectName(g, getLang())])),
    ]);
    aspect.value = state.aspect || "";
    aspect.addEventListener("change", () => update({ aspect: aspect.value || null }));
    const polarity = el("select", { class: SELECT_CLASS, "aria-label": t("filterSentiment") }, [
      el("option", { value: "" }, [t("allSentiments")]),
      ...["negative", "neutral", "positive"].map((p) => el("option", { value: p }, [polName(p)])),
    ]);
    polarity.value = state.polarity;
    polarity.addEventListener("change", () => update({ polarity: polarity.value }));
    const search = el("input", { type: "search", class: `${SELECT_CLASS} min-w-[14rem] flex-1`, placeholder: t("searchPlaceholder"), "aria-label": t("searchPlaceholder") });
    search.value = state.query;
    search.addEventListener("input", () => {
      state.query = search.value;
      state.shown = PAGE_SIZE;
      renderList();
    });
    const clear = el("button", { type: "button", class: "btn !min-h-[38px] text-sm" }, [t("clearFilters")]);
    clear.addEventListener("click", () => update({ aspect: null, polarity: "", query: "" }));
    return el("div", { class: "flex flex-wrap items-center gap-2" }, [aspect, polarity, search, clear]);
  }

  function rowItem(row) {
    const asp = state.aspect ? matchesAspect(row, state.aspect) : null;
    const polarity = asp ? asp.polarity : row.predicted;
    const aspectChips = (row.aspects || []).map((a) => {
      const tone = a.group === state.aspect ? `pol-${a.polarity}` : "border border-slate-300 bg-white text-slate-600";
      return el("span", { class: `badge ${tone} !text-[11px]` }, [getAspectName(a.group, getLang())]);
    });
    return el("li", { class: "rounded-lg border border-slate-200 bg-white p-3" }, [
      el("div", { class: "flex flex-wrap items-center gap-2" }, [
        el("span", { class: `badge pol-${polarity}` }, [polName(polarity)]),
        ...aspectChips,
        row.decision === "review" ? el("span", { class: "badge bg-amber-500 text-white" }, [t("needsReview")]) : null,
        state.course === null && row.course ? el("span", { class: "text-xs text-slate-500" }, [row.course]) : null,
      ]),
      el("p", { class: "mt-2 text-sm text-slate-700" }, [row.text]),
    ]);
  }

  function renderList() {
    const matches = filterRows(response.rows, state);
    const visible = matches.slice(0, state.shown);
    const head = el("p", { class: "text-sm font-medium text-slate-700" }, [
      fill(t("showing"), { n: visible.length, total: matches.length }),
    ]);
    const body =
      matches.length === 0
        ? el("p", { class: "rounded-lg bg-slate-50 p-4 text-sm text-slate-500" }, [t("noMatches")])
        : el("ul", { class: "space-y-2" }, visible.map(rowItem));
    const more =
      matches.length > visible.length
        ? el("button", { type: "button", class: "btn mt-3" }, [t("showMoreComments")])
        : null;
    more?.addEventListener("click", () => {
      state.shown += PAGE_SIZE;
      renderList();
    });
    listSlot.replaceChildren(head, body, ...(more ? [more] : []));
  }

  function render() {
    root.replaceChildren(
      el("div", {}, [
        el("h3", { class: "text-base font-semibold text-slate-900" }, [t("exploreTitle")]),
        el("p", { class: "mt-1 text-sm text-slate-500" }, [
          countText(response.row_count, t("comment"), t("comments")),
        ]),
      ]),
      courseChips(),
      courseSummary(),
      el("h4", { class: "h-section" }, [t("commentsTitle")]),
      filters(),
      listSlot
    );
    renderList();
  }

  render();
  return {
    node: root,
    select(course, aspect, polarity) {
      update({ course, aspect, polarity });
      root.scrollIntoView({ behavior: "smooth", block: "start" });
    },
  };
}

export { MIN_SUPPORT };
