/**
 * Review queue view and local storage (spec 027).
 */

import { POLARITY_ORDER, REASON_TEXT, el } from "./common.js";
import { buildQueueCsv, downloadCsv, EXPORT_FILE_NAME } from "./export.js";
import { countText } from "./report.js";

export const STORAGE_PREFIX = "review-decisions:";
export const ACTIONS = ["accept", "relabel"];

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

function getStatusText(decision) {
  if (!decision) {
    return "Pending";
  }
  if (decision.action === "accept") {
    return `Accepted as ${decision.label}`;
  }
  if (decision.action === "relabel") {
    return `Relabeled as ${decision.label}`;
  }
  return "Pending";
}

export function initReview(panel) {
  const empty = panel.querySelector("#review-empty");
  const summary = panel.querySelector("#review-summary");
  const notice = panel.querySelector("#review-notice");
  const exportBtn = panel.querySelector("#export-csv");
  const tableContainer = panel.querySelector("#review-table");

  let state = { batchId: null, rows: [], decisions: {} };

  function refreshToggles() {
    const toggles = panel.querySelectorAll(".clamp-toggle");
    for (const btn of toggles) {
      const targetId = btn.getAttribute("aria-controls");
      const p = panel.querySelector(`#${targetId}`);
      if (p && p.classList.contains("clamp")) {
        btn.hidden = p.scrollHeight <= p.clientHeight + 1;
      }
    }
  }

  function updateSummary() {
    const total = state.rows.length;
    if (total === 0) {
      summary.textContent = "No comments need review.";
      summary.hidden = false;
      exportBtn.disabled = true;
      return;
    }
    const decided = Object.keys(state.decisions).length;
    const countPart = countText(total, "comment needs", "comments need");
    summary.textContent = `${countPart} review. ${decided} decided.`;
    summary.hidden = false;
    exportBtn.disabled = false;
  }

  function renderTable() {
    if (state.rows.length === 0) {
      tableContainer.replaceChildren();
      updateSummary();
      return;
    }

    const headers = ["Row", "Course", "Comment", "Predicted", "Set", "Reason", "Decision"].map(
      (h) => el("th", { scope: "col" }, [h])
    );
    const thead = el("thead", {}, [el("tr", {}, headers)]);

    const tbodyRows = state.rows.map((row) => {
      const rowKey = String(row.row);
      const decision = state.decisions[rowKey];

      const pComment = el("p", { class: "clamp", id: `comment-${row.row}` }, [row.text]);
      const toggleBtn = el(
        "button",
        {
          type: "button",
          class: "link-button clamp-toggle",
          "aria-expanded": "false",
          "aria-controls": `comment-${row.row}`,
          hidden: "",
        },
        ["Show more"]
      );
      toggleBtn.addEventListener("click", () => {
        const isClamped = pComment.classList.toggle("clamp");
        toggleBtn.setAttribute("aria-expanded", isClamped ? "false" : "true");
        toggleBtn.textContent = isClamped ? "Show more" : "Show less";
      });

      const setLabels =
        row.conformal_set && row.conformal_set.length > 0
          ? row.conformal_set.join(", ")
          : "no class";

      const reasonText = REASON_TEXT[row.reason] || row.reason;

      const pStatus = el("p", { id: `status-${row.row}` }, [getStatusText(decision)]);

      const acceptBtn = el(
        "button",
        {
          type: "button",
          "aria-label": `Accept row ${row.row} as ${row.predicted}`,
        },
        ["Accept"]
      );

      const relabelLabel = el(
        "label",
        {
          class: "visually-hidden",
          for: `relabel-${row.row}`,
        },
        [`New class for row ${row.row}`]
      );

      const select = el(
        "select",
        { id: `relabel-${row.row}` },
        POLARITY_ORDER.map((pol) => {
          const opt = el("option", { value: pol }, [pol]);
          const selectedVal = decision && decision.action === "relabel" ? decision.label : row.predicted;
          if (pol === selectedVal) {
            opt.setAttribute("selected", "");
          }
          return opt;
        })
      );

      const relabelBtn = el(
        "button",
        {
          type: "button",
          "aria-label": `Relabel row ${row.row}`,
        },
        ["Relabel"]
      );

      function recordDecision(action, label) {
        state.decisions[rowKey] = { action, label };
        pStatus.textContent = getStatusText(state.decisions[rowKey]);
        updateSummary();
        const ok = saveDecisions(state.batchId, state.decisions);
        if (!ok) {
          notice.textContent = "Your browser could not save this decision. Export the queue to keep it.";
        } else {
          notice.textContent = "";
        }
      }

      acceptBtn.addEventListener("click", () => recordDecision("accept", row.predicted));
      relabelBtn.addEventListener("click", () => recordDecision("relabel", select.value));

      const actionsDiv = el("div", { class: "decision-actions" }, [
        acceptBtn,
        relabelLabel,
        select,
        relabelBtn,
      ]);

      return el("tr", {}, [
        el("td", { class: "num" }, [String(row.row)]),
        el("td", {}, [row.course ?? "No course"]),
        el("td", { class: "comment-cell" }, [pComment, toggleBtn]),
        el("td", {}, [row.predicted]),
        el("td", {}, [setLabels]),
        el("td", {}, [reasonText]),
        el("td", {}, [pStatus, actionsDiv]),
      ]);
    });

    const tbody = el("tbody", {}, tbodyRows);
    const table = el("table", { class: "queue" }, [thead, tbody]);
    const scrollRegion = el(
      "div",
      {
        class: "table-scroll",
        role: "region",
        "aria-label": "Review queue table, scrolls sideways",
        tabindex: "0",
      },
      [table]
    );

    tableContainer.replaceChildren(scrollRegion);
    updateSummary();
    setTimeout(refreshToggles, 0);
  }

  document.addEventListener("batch-loaded", (e) => {
    const { batchId, response } = e.detail;
    const { decisions, readable } = loadDecisions(batchId);
    state = {
      batchId,
      rows: queueRows(response),
      decisions,
    };
    if (empty) {
      empty.hidden = true;
    }
    if (!readable) {
      notice.textContent = "Saved decisions for this file could not be read and were ignored.";
    } else {
      notice.textContent = "";
    }
    renderTable();
  });

  exportBtn.addEventListener("click", () => {
    const csv = buildQueueCsv(state.rows, state.decisions);
    downloadCsv(csv, EXPORT_FILE_NAME);
  });

  document.addEventListener("tab-shown", (e) => {
    if (e.detail && e.detail.panelId === "panel-review") {
      refreshToggles();
    }
  });

  window.addEventListener("resize", refreshToggles);
}
