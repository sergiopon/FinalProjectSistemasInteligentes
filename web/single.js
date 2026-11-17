/**
 * Single comment analysis view (spec 025).
 */

import {
  ASPECT_NAMES,
  POLARITY_ORDER,
  REASON_TEXT,
  clearError,
  el,
  formatPercent,
  formatScore,
  postJson,
  setBusy,
  showError,
} from "./common.js";

export const MAX_TEXT_CHARS = 2000;

export function textLength(value) {
  return [...value.trim()].length;
}

function buildDecisionLine(decision, reason) {
  if (decision === "classify") {
    return el("p", {}, ["Decision: classify"]);
  }
  const badge = el("span", { class: "badge" }, ["Needs review"]);
  const reasonText = REASON_TEXT[reason] ? ` ${REASON_TEXT[reason]}` : "";
  return el("p", {}, ["Decision: ", badge, reasonText]);
}

function buildProbabilitiesSection(probabilities, predicted) {
  const rows = [];
  for (const pol of POLARITY_ORDER) {
    const p = probabilities[pol] ?? 0;
    const pct = Math.round(p * 100);
    const fillClass = pol === predicted ? "fill-predicted" : "fill-other";
    const fill = el("span", { class: `prob-fill ${fillClass}` });
    fill.style.width = `${pct}%`;
    const track = el("span", { class: "prob-track" }, [fill]);
    const row = el(
      "div",
      {
        class: "prob-row",
        role: "img",
        "aria-label": `${pol} ${formatPercent(p)}`,
      },
      [
        el("span", { class: "prob-label" }, [pol]),
        track,
        el("span", { class: "prob-value num" }, [formatPercent(p)]),
      ]
    );
    rows.push(row);
  }
  return [el("h4", {}, ["Class probabilities"]), ...rows];
}

function buildAspectsSection(aspects) {
  if (!aspects || aspects.length === 0) {
    return [el("h4", {}, ["Aspects"]), el("p", {}, ["No aspect detected in this comment."])];
  }
  const items = aspects.map((asp) => {
    const name = ASPECT_NAMES[asp.group] || asp.group;
    const text = `${name}: ${asp.polarity} (score ${formatScore(asp.score)})`;
    return el("li", {}, [text]);
  });
  return [el("h4", {}, ["Aspects"]), el("ul", { class: "aspect-list" }, items)];
}

function buildInfluencesSection(influences) {
  if (!influences || influences.length === 0) {
    return [
      el("h4", {}, ["Words that changed the prediction most"]),
      el("p", {}, ["No single word changed the prediction."]),
    ];
  }
  const items = influences.map((item) => {
    const sign = item.delta >= 0 ? "+" : "-";
    const text = `${item.word}: ${sign}${formatScore(Math.abs(item.delta))}`;
    return el("li", {}, [text]);
  });
  const caption = el("p", { class: "caption" }, [
    "Each value is the drop in the probability of the predicted class when the word is removed. " +
      "A negative value means the word pulled against it.",
  ]);
  return [
    el("h4", {}, ["Words that changed the prediction most"]),
    el("ul", { class: "influence-list" }, items),
    caption,
  ];
}

function renderResultCard(data) {
  const setLabels =
    data.conformal_set && data.conformal_set.length > 0
      ? data.conformal_set.join(", ")
      : "no class";
  const confText = formatPercent(data.confidence_level);

  const card = el("article", { class: "card" }, [
    el("h3", {}, ["Result"]),
    el("p", {}, [`Predicted: ${data.predicted}`]),
    buildDecisionLine(data.decision, data.reason),
    el("p", {}, [`Prediction set at ${confText}: ${setLabels}`]),
    ...buildProbabilitiesSection(data.probabilities, data.predicted),
    ...buildAspectsSection(data.aspects),
    ...buildInfluencesSection(data.influences),
    el("p", { class: "caption" }, [`Model ${data.model_version}`]),
  ]);
  return card;
}

export function initSingle(panel) {
  const textarea = panel.querySelector("#comment-text");
  const counter = panel.querySelector("#comment-counter");
  const button = panel.querySelector("#analyze-button");
  const loading = panel.querySelector("#single-loading");
  const errors = panel.querySelector("#single-errors");
  const result = panel.querySelector("#single-result");
  const empty = panel.querySelector("#single-empty");

  function updateCounter() {
    const n = textLength(textarea.value);
    if (n > MAX_TEXT_CHARS) {
      counter.textContent = `${n} / ${MAX_TEXT_CHARS} characters. Shorten the comment to ${MAX_TEXT_CHARS} characters.`;
      counter.classList.add("over-limit");
      button.disabled = true;
    } else {
      counter.textContent = `${n} / ${MAX_TEXT_CHARS} characters`;
      counter.classList.remove("over-limit");
      button.disabled = n === 0;
    }
  }

  textarea.addEventListener("input", updateCounter);

  button.addEventListener("click", async () => {
    clearError(errors);
    setBusy(button, result, loading, true);
    try {
      const data = await postJson("/predict", { text: textarea.value });
      if (empty) {
        empty.hidden = true;
      }
      result.replaceChildren(renderResultCard(data));
    } catch (error) {
      showError(errors, error);
    } finally {
      setBusy(button, result, loading, false);
      updateCounter();
    }
  });

  updateCounter();
}
