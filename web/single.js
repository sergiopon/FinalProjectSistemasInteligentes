/**
 * Single comment analysis view (spec 025).
 */

import {
  POLARITY_ORDER,
  clearError,
  el,
  formatPercent,
  formatScore,
  getAspectName,
  getReasonText,
  postJson,
  setBusy,
  showError,
} from "./common.js";
import { SAMPLE_COMMENTS, getLang, t } from "./i18n.js";

export const MAX_TEXT_CHARS = 2000;

export function textLength(value) {
  return [...String(value ?? "").trim()].length;
}

function buildDecisionLine(decision, reason) {
  const lang = getLang();
  if (decision === "classify") {
    return el("p", {}, [t("decisionClassify")]);
  }
  const badge = el("span", { class: "badge" }, [t("needsReview")]);
  const reasonText = getReasonText(reason, lang) ? ` ${getReasonText(reason, lang)}` : "";
  return el("p", {}, [`${t("decisionReview")} `, badge, reasonText]);
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
  return [el("h4", {}, [t("classProbs")]), ...rows];
}

function buildAspectsSection(aspects) {
  const lang = getLang();
  if (!aspects || aspects.length === 0) {
    return [el("h4", {}, [t("aspectsTitle")]), el("p", {}, [t("noAspects")])];
  }
  const items = aspects.map((asp) => {
    const name = getAspectName(asp.group, lang);
    const text = `${name}: ${asp.polarity} (score ${formatScore(asp.score)})`;
    return el("li", {}, [text]);
  });
  return [el("h4", {}, [t("aspectsTitle")]), el("ul", { class: "aspect-list" }, items)];
}

function buildInfluencesSection(influences) {
  if (!influences || influences.length === 0) {
    return [
      el("h4", {}, [t("influencesTitle")]),
      el("p", {}, [t("noInfluences")]),
    ];
  }
  const items = influences.map((item) => {
    const sign = item.delta >= 0 ? "+" : "-";
    const text = `${item.word}: ${sign}${formatScore(Math.abs(item.delta))}`;
    return el("li", {}, [text]);
  });
  const caption = el("p", { class: "caption" }, [t("influencesCaption")]);
  return [
    el("h4", {}, [t("influencesTitle")]),
    el("ul", { class: "influence-list" }, items),
    caption,
  ];
}

function renderResultCard(data) {
  const setLabels =
    data.conformal_set && data.conformal_set.length > 0
      ? data.conformal_set.join(", ")
      : t("noClass");
  const confText = formatPercent(data.confidence_level);

  const card = el("article", { class: "card" }, [
    el("h3", {}, [t("resultTitle")]),
    el("p", {}, [`${t("predicted")} ${data.predicted}`]),
    buildDecisionLine(data.decision, data.reason),
    el("p", {}, [`${t("predSet")} ${confText}: ${setLabels}`]),
    ...buildProbabilitiesSection(data.probabilities, data.predicted),
    ...buildAspectsSection(data.aspects),
    ...buildInfluencesSection(data.influences),
    el("p", { class: "caption" }, [`${t("modelPrefix")} ${data.model_version}`]),
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

  if (!textarea || !counter || !button || !loading || !errors || !result) {
    return;
  }

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

  const chips = panel.querySelectorAll(".chip");
  for (const chip of chips) {
    chip.addEventListener("click", () => {
      const type = chip.dataset.sample;
      if (SAMPLE_COMMENTS[type]) {
        textarea.value = SAMPLE_COMMENTS[type];
        updateCounter();
      }
    });
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
