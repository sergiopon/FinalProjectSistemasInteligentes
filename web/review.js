/**
 * Review queue view and local storage (spec 027).
 */

import { POLARITY_ORDER, el, getReasonText } from "./common.js";
import { buildQueueCsv, downloadCsv, EXPORT_FILE_NAME } from "./export.js";
import { getLang, polName, t } from "./i18n.js";
import { countText } from "./report.js";

export const STORAGE_PREFIX = "review-decisions:";
export const ACTIONS = ["accept", "relabel", "escalate"];

export function queueRows(response) {
  if (!response || !Array.isArray(response.rows)) {
    return [];
  }
  return response.rows.filter((r) => r.decision === "review");
}

export function loadDecisions(batchId) {
  let raw = null;
  try {
    raw = localStorage.getItem(STORAGE_PREFIX + batchId);
  } catch {
    return { decisions: {}, readable: false };
  }
  if (raw === null) {
    return { decisions: {}, readable: true };
  }
  let parsed = null;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { decisions: {}, readable: false };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { decisions: {}, readable: false };
  }
  const clean = {};
  for (const [key, value] of Object.entries(parsed)) {
    if (/^[0-9]+$/.test(key) && value && typeof value === "object") {
      if (ACTIONS.includes(value.action) && POLARITY_ORDER.includes(value.label)) {
        clean[key] = { action: value.action, label: value.label };
      }
    }
  }
  return { decisions: clean, readable: true };
}

export function saveDecisions(batchId, decisions) {
  try {
    localStorage.setItem(STORAGE_PREFIX + batchId, JSON.stringify(decisions));
    return true;
  } catch {
    return false;
  }
}

const STATUS_STYLE = Object.freeze({
  accept: { key: "statusAccepted", cls: "bg-brand-600 text-white" },
  relabel: { key: "statusRelabeled", cls: "bg-brand-600 text-white" },
  escalate: { key: "statusEscalated", cls: "bg-amber-500 text-white" },
});

function statusBadge(decision) {
  const style = decision ? STATUS_STYLE[decision.action] : null;
  if (!style) {
    return el("span", { class: "badge bg-slate-500 text-white" }, [t("statusPending")]);
  }
  const label = decision.action === "escalate" ? "" : `: ${polName(decision.label)}`;
  return el("span", { class: `badge ${style.cls}` }, [`${t(style.key)}${label}`]);
}

function polChip(pol) {
  return el("span", { class: `badge pol-${pol}` }, [polName(pol)]);
}

function choiceBtn(row, pol, record) {
  const suggested = pol === row.predicted;
  const ring = suggested
    ? "border-2 border-brand-600 bg-brand-50 text-brand-900"
    : "border border-slate-300 bg-white text-slate-700 hover:border-brand-500";
  const button = el(
    "button",
    { type: "button", class: `badge cursor-pointer !px-3 !py-1.5 text-xs transition ${ring}`, "aria-label": `${polName(pol)} #${row.row}` },
    [suggested ? `${polName(pol)} · ${t("suggested")}` : polName(pol)]
  );
  button.addEventListener("click", () => record(pol === row.predicted ? "accept" : "relabel", pol));
  return button;
}

function topProbability(row) {
  return Math.max(...Object.values(row.probabilities || { x: 1 }));
}

export function initReview(panel) {
  const empty = panel.querySelector("#review-empty");
  const summary = panel.querySelector("#review-summary");
  const notice = panel.querySelector("#review-notice");
  const exportBtn = panel.querySelector("#export-csv");
  const tableContainer = panel.querySelector("#review-table");
  const progress = panel.querySelector("#review-progress");
  const progressBar = panel.querySelector("#review-progress-bar");
  const tabCount = document.getElementById("review-count");

  if (!empty || !summary || !notice || !exportBtn || !tableContainer) {
    return;
  }

  let state = { batchId: null, rows: [], decisions: {} };
  const view = { course: "", pendingOnly: false };
  let loaded = false;

  function refreshToggles() {
    for (const btn of panel.querySelectorAll(".clamp-toggle")) {
      const p = panel.querySelector(`#${btn.getAttribute("aria-controls")}`);
      if (p && p.classList.contains("clamp")) {
        btn.hidden = p.scrollHeight <= p.clientHeight + 1;
      }
    }
  }

  function updateSummary() {
    const total = state.rows.length;
    if (!loaded) {
      return;
    }
    const decided = Object.keys(state.decisions).length;
    const pending = Math.max(0, total - decided);
    if (tabCount) {
      tabCount.textContent = String(pending);
      tabCount.classList.toggle("hidden", pending === 0);
    }
    if (total === 0) {
      summary.textContent = t("reviewNone");
      summary.hidden = false;
      exportBtn.disabled = true;
      progress?.classList.add("hidden");
      return;
    }
    summary.textContent = `${countText(pending, t("comment"), t("comments"))} ${t("reviewPending")} · ${decided} ${t("reviewDecided")}`;
    summary.hidden = false;
    exportBtn.disabled = false;
    progress?.classList.remove("hidden");
    if (progressBar) {
      progressBar.style.width = `${Math.round((decided / total) * 100)}%`;
    }
  }

  function buildRow(row) {
    const rowKey = String(row.row);
    const statusSlot = el("div", {});
    const paint = () => statusSlot.replaceChildren(statusBadge(state.decisions[rowKey]));

    const pComment = el("p", { class: "clamp text-sm text-slate-700", id: `comment-${row.row}` }, [row.text]);
    const toggleBtn = el(
      "button",
      { type: "button", class: "clamp-toggle mt-1 text-xs font-medium text-brand-600 hover:underline", "aria-expanded": "false", "aria-controls": `comment-${row.row}`, hidden: "" },
      [t("showMore")]
    );
    toggleBtn.addEventListener("click", () => {
      const clamped = pComment.classList.toggle("clamp");
      toggleBtn.setAttribute("aria-expanded", clamped ? "false" : "true");
      toggleBtn.textContent = clamped ? t("showMore") : t("showLess");
    });

    function record(action, label) {
      state.decisions[rowKey] = { action, label };
      paint();
      updateSummary();
      notice.textContent = saveDecisions(state.batchId, state.decisions) ? "" : t("saveFail");
      if (view.pendingOnly) {
        renderTable();
      }
    }
    const choices = POLARITY_ORDER.map((pol) => choiceBtn(row, pol, record));
    const unsure = el("button", { type: "button", class: "btn !min-h-[30px] !px-3 text-xs" }, [t("dontKnow")]);
    unsure.addEventListener("click", () => record("escalate", row.predicted));

    paint();
    const cell = (cls, children) => el("td", { class: `px-3 py-3 align-top ${cls}` }, children);
    return el("tr", { class: "border-t border-slate-200 transition hover:bg-slate-50/70" }, [
      cell("whitespace-nowrap text-sm", [
        el("span", { class: "block font-medium tabular-nums text-slate-900" }, [`#${row.row}`]),
        el("span", { class: "block text-xs text-slate-500" }, [row.course ?? t("noCourse")]),
      ]),
      cell("min-w-[16rem] max-w-md", [pComment, toggleBtn]),
      cell("min-w-[9rem] text-xs text-slate-600", [getReasonText(row.reason, getLang())]),
      cell("min-w-[16rem]", [
        el("p", { class: "mb-2 text-xs text-slate-500" }, [t("reviewQuestion")]),
        el("div", { class: "flex flex-wrap items-center gap-1.5" }, [...choices, unsure]),
        el("div", { class: "mt-2" }, [statusSlot]),
      ]),
    ]);
  }

  function visibleRows() {
    return state.rows
      .filter((r) => !view.course || r.course === view.course)
      .filter((r) => !view.pendingOnly || !state.decisions[String(r.row)])
      .sort((x, y) => topProbability(x) - topProbability(y));
  }

  function controls() {
    const courses = [...new Set(state.rows.map((r) => r.course).filter(Boolean))].sort();
    const select = el(
      "select",
      { class: "min-h-[34px] rounded-lg border border-slate-300 bg-white px-2 text-sm", "aria-label": t("filterCourse") },
      [el("option", { value: "" }, [t("allCoursesShort")]), ...courses.map((c) => el("option", { value: c }, [c]))]
    );
    select.value = view.course;
    select.addEventListener("change", () => {
      view.course = select.value;
      renderTable();
    });
    const check = el("input", { type: "checkbox", class: "h-4 w-4" });
    check.checked = view.pendingOnly;
    check.addEventListener("change", () => {
      view.pendingOnly = check.checked;
      renderTable();
    });
    return el("div", { class: "mb-3 flex flex-wrap items-center gap-4 text-sm text-slate-700" }, [
      el("label", { class: "flex items-center gap-2" }, [t("filterCourse"), select]),
      el("label", { class: "flex items-center gap-2" }, [check, t("onlyPending")]),
    ]);
  }

  function renderTable() {
    if (state.rows.length === 0) {
      tableContainer.replaceChildren();
      updateSummary();
      return;
    }
    const th = (key) => el("th", { scope: "col", class: "px-3 py-2 text-left text-xs font-semibold text-slate-600" }, [t(key)]);
    const thead = el("thead", { class: "bg-slate-50" }, [
      el("tr", {}, ["colRow", "colComment", "colReason", "colAction"].map(th)),
    ]);
    const rows = visibleRows();
    const table = el("table", { class: "w-full border-collapse" }, [thead, el("tbody", {}, rows.slice(0, 50).map(buildRow))]);
    tableContainer.replaceChildren(
      controls(),
      el(
        "div",
        { class: "overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-card", role: "region", "aria-label": t("tableScroll"), tabindex: "0" },
        [table]
      )
    );
    updateSummary();
    setTimeout(refreshToggles, 0);
  }

  document.addEventListener("batch-loaded", (e) => {
    const { batchId, response } = e.detail;
    const { decisions, readable } = loadDecisions(batchId);
    state = { batchId, rows: queueRows(response), decisions };
    view.course = "";
    view.pendingOnly = false;
    loaded = true;
    empty.hidden = true;
    notice.textContent = readable ? "" : t("readFail");
    renderTable();
  });

  document.addEventListener("lang-changed", () => {
    notice.textContent = "";
    if (loaded) {
      renderTable();
    }
  });

  exportBtn.addEventListener("click", () => {
    downloadCsv(buildQueueCsv(state.rows, state.decisions), EXPORT_FILE_NAME);
  });

  document.addEventListener("tab-shown", (e) => {
    if (e.detail && e.detail.panelId === "panel-review") {
      refreshToggles();
    }
  });

  window.addEventListener("resize", refreshToggles);
}
