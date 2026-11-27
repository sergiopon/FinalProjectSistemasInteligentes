/**
 * Single comment analysis view (spec 025).
 */

import {
  ASPECT_ORDER,
  POLARITY_ORDER,
  clearError,
  el,
  formatPercent,
  formatScore,
  getAspectName,
  getReasonText,
  icon,
  postJson,
  stagger,
  setBusy,
  showError,
} from "./common.js";
import { SAMPLE_COMMENTS, getLang, polName, t } from "./i18n.js";

export const MAX_TEXT_CHARS = 2000;

export function textLength(value) {
  return [...String(value ?? "").trim()].length;
}

const POL_TEXT = Object.freeze({
  negative: "pol-negative",
  neutral: "pol-neutral",
  positive: "pol-positive",
});

const NUM = "tabular-nums";

function polBadge(pol, extra = "") {
  return el("span", { class: `badge ${POL_TEXT[pol] || "pol-neutral"} ${extra}`.trim() }, [polName(pol)]);
}

function subCard(title, children, extra = "") {
  return el("section", { class: `card !p-5 ${extra}`.trim() }, [
    el("h3", { class: "h-section mb-3" }, [title]),
    ...children,
  ]);
}

function buildDecisionCard(data) {
  const review = data.decision !== "classify";
  const header = el(
    "div",
    { class: `flex items-center gap-3 px-5 py-4 text-white ${review ? "bg-amber-500" : "bg-green-600"}` },
    [
      el("span", { class: "flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/20" }, [icon(review ? "user" : "check", 22)]),
      el("div", { class: "min-w-0" }, [
        el("p", { class: "text-base font-semibold leading-tight" }, [review ? t("decisionReview") : t("decisionClassify")]),
        review && data.reason ? el("p", { class: "text-sm opacity-90" }, [getReasonText(data.reason, getLang())]) : null,
      ]),
    ]
  );
  const body = el("div", { class: "flex flex-wrap items-end justify-between gap-4 p-5" }, [
    el("div", {}, [
      el("p", { class: "h-section" }, [t("predicted")]),
      el("p", { class: "mt-1 text-3xl font-semibold capitalize leading-none text-slate-900" }, [polName(data.predicted)]),
    ]),
    el("div", { class: "flex flex-wrap items-center gap-2" }, [
      polBadge(data.predicted),
      el("span", { class: `badge bg-slate-700 text-white ${NUM}` }, [`${t("confidence")} ${formatPercent(data.confidence_level)}`]),
      el("span", { class: "badge bg-slate-200 text-slate-700" }, [`${t("modelPrefix")} ${data.model_version}`]),
    ]),
  ]);
  return el("section", { class: "card overflow-hidden !p-0 md:col-span-2" }, [header, body]);
}

function buildProbabilities(probabilities, predicted) {
  const rows = POLARITY_ORDER.map((pol) => {
    const p = probabilities[pol] ?? 0;
    const fill = el("div", {
      class: `h-full rounded-full transition-all duration-700 ease-out ${pol === predicted ? `fill-${pol}` : "bg-slate-300"}`,
    });
    fill.style.width = "0%";
    requestAnimationFrame(() => requestAnimationFrame(() => {
      fill.style.width = `${Math.round(p * 100)}%`;
    }));
    return el("div", { class: "grid grid-cols-[5rem_1fr_3.5rem] items-center gap-3", role: "img", "aria-label": `${polName(pol)} ${formatPercent(p)}` }, [
      el("span", { class: "text-sm capitalize text-slate-700" }, [polName(pol)]),
      el("div", { class: "h-3 overflow-hidden rounded-full bg-slate-200" }, [fill]),
      el("span", { class: `text-right text-sm font-semibold ${NUM} text-slate-800` }, [formatPercent(p)]),
    ]);
  });
  return subCard(t("classProbs"), [el("div", { class: "space-y-3" }, rows)]);
}

function certainty(size) {
  if (size === 1) {
    return { text: t("certHigh"), cls: "bg-green-600" };
  }
  if (size === 2) {
    return { text: t("certMid"), cls: "bg-amber-500" };
  }
  return { text: t("certLow"), cls: "bg-red-600" };
}

function buildConformal(data) {
  const set = data.conformal_set || [];
  const cert = certainty(set.length);
  const chips = POLARITY_ORDER.map((pol) => {
    const inSet = set.includes(pol);
    return el(
      "div",
      {
        class: inSet
          ? `flex flex-1 flex-col items-center gap-1 rounded-lg border-2 border-transparent px-3 py-2 ${POL_TEXT[pol]} shadow-pop animate-pop`
          : "flex flex-1 flex-col items-center gap-1 rounded-lg border-2 border-dashed border-slate-300 bg-slate-100 px-3 py-2 text-slate-500 opacity-50",
      },
      [
        el("span", { class: `text-sm font-semibold capitalize ${inSet ? "" : "line-through"}` }, [polName(pol)]),
        el("span", { class: "text-[11px] uppercase tracking-wide opacity-90" }, [inSet ? t("retained") : t("discarded")]),
      ]
    );
  });
  return subCard(t("predSet"), [
    el("div", { class: "flex items-center justify-between gap-2" }, [
      el("p", { class: "text-xs text-slate-500" }, [t("predSetHint").replace("{p}", formatPercent(data.confidence_level))]),
      el("span", { class: `badge text-white ${cert.cls}` }, [cert.text]),
    ]),
    el("div", { class: "mt-3 flex gap-2" }, chips),
    set.length === 0 ? el("p", { class: "mt-2 text-sm text-slate-500" }, [t("noClass")]) : null,
  ]);
}

function buildAspects(aspects) {
  const lang = getLang();
  const byGroup = new Map((aspects || []).map((asp) => [asp.group, asp]));
  const cells = ASPECT_ORDER.map((group) => {
    const asp = byGroup.get(group);
    const nameClass = asp ? "font-medium text-slate-800" : "text-slate-400";
    const name = el("span", { class: `text-sm ${nameClass}` }, [getAspectName(group, lang)]);
    if (!asp) {
      return el("li", { class: "rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 opacity-70" }, [
        name,
        el("p", { class: "mt-1 text-xs text-slate-400" }, [t("notMentioned")]),
      ]);
    }
    const fill = el("div", { class: `h-full rounded-full transition-all duration-700 ease-out fill-${asp.polarity}` });
    fill.style.width = "0%";
    requestAnimationFrame(() => requestAnimationFrame(() => {
      fill.style.width = `${Math.round(asp.score * 100)}%`;
    }));
    return el("li", { class: "rounded-lg border border-slate-200 bg-white p-3 shadow-card" }, [
      el("div", { class: "flex items-start justify-between gap-2" }, [name, polBadge(asp.polarity)]),
      el("div", { class: "mt-2 flex items-center gap-2" }, [
        el("div", { class: "h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200" }, [fill]),
        el("span", { class: `text-xs font-semibold ${NUM} text-slate-600` }, [formatScore(asp.score)]),
      ]),
    ]);
  });
  const mentioned = ASPECT_ORDER.filter((g) => byGroup.has(g)).length;
  return el("section", { class: "card !p-5 md:col-span-2" }, [
    el("div", { class: "mb-3 flex items-center justify-between" }, [
      el("h3", { class: "h-section" }, [t("aspectsTitle")]),
      el("span", { class: `text-xs ${NUM} text-slate-500` }, [`${mentioned}/${ASPECT_ORDER.length} ${t("aspectsCoverage")}`]),
    ]),
    el("ul", { class: "grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3" }, stagger(cells, 45)),
  ]);
}

function buildInfluences(influences, predicted) {
  if (!influences || influences.length === 0) {
    return subCard(t("influencesTitle"), [el("p", { class: "text-sm text-slate-500" }, [t("noInfluences")])], "md:col-span-2");
  }
  const items = influences.map((item) => {
    const against = item.delta < 0;
    return el("li", { class: `badge ${against ? "bg-amber-500" : "bg-brand-600"} text-white ${NUM}` }, [
      `${item.word} ${against ? "↓" : "↑"} ${formatScore(Math.abs(item.delta))}`,
    ]);
  });
  return subCard(
    t("influencesTitle"),
    [
      el("ul", { class: "flex flex-wrap gap-2" }, stagger(items, 50)),
      el("p", { class: "mt-3 text-xs text-slate-500" }, [t("influencesCaption").replace("{label}", polName(predicted))]),
    ],
    "md:col-span-2"
  );
}

function renderResultCard(data) {
  const cards = [
    buildDecisionCard(data),
    buildProbabilities(data.probabilities, data.predicted),
    buildConformal(data),
    buildAspects(data.aspects),
    buildInfluences(data.influences, data.predicted),
  ];
  return el("div", { class: "grid gap-4 transition-all duration-300 ease-in-out md:grid-cols-2" }, stagger(cards, 90));
}

function skeletonBlock(cls) {
  return el("div", { class: `animate-pulse rounded-xl border border-slate-200 bg-white p-5 ${cls}` }, [
    el("div", { class: "h-3 w-1/3 rounded bg-slate-200" }),
    el("div", { class: "mt-4 h-3 w-full rounded bg-slate-200" }),
    el("div", { class: "mt-3 h-3 w-5/6 rounded bg-slate-200" }),
    el("div", { class: "mt-3 h-3 w-2/3 rounded bg-slate-200" }),
  ]);
}

function renderSkeleton() {
  return el("div", { class: "grid gap-4 md:grid-cols-2", "aria-label": t("resultAnalyzing") }, [
    el("div", { class: "animate-pulse rounded-xl bg-slate-300 p-5 md:col-span-2" }, [
      el("div", { class: "h-4 w-1/3 rounded bg-slate-400/70" }),
      el("div", { class: "mt-3 h-8 w-1/4 rounded bg-slate-400/70" }),
    ]),
    skeletonBlock(""),
    skeletonBlock(""),
    skeletonBlock("md:col-span-2"),
  ]);
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

  const bar = panel.querySelector("#counter-bar");
  let lastData = null;

  function updateCounter() {
    const n = textLength(textarea.value);
    if (bar) {
      bar.style.width = `${Math.min(100, (n / MAX_TEXT_CHARS) * 100)}%`;
    }
    if (n > MAX_TEXT_CHARS) {
      counter.textContent = `${n} / ${MAX_TEXT_CHARS} ${t("charsUnit")}. ${t("overLimit")}`;
      counter.classList.add("text-pol-neg");
      button.disabled = true;
    } else {
      counter.textContent = `${n} / ${MAX_TEXT_CHARS} ${t("charsUnit")}`;
      counter.classList.remove("text-pol-neg");
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
    if (empty) {
      empty.hidden = true;
    }
    result.replaceChildren(renderSkeleton());
    try {
      const data = await postJson("/predict", { text: textarea.value });
      lastData = data;
      result.replaceChildren(renderResultCard(data));
    } catch (error) {
      showError(errors, error);
      if (lastData) {
        result.replaceChildren(renderResultCard(lastData));
      } else {
        result.replaceChildren();
        if (empty) {
          empty.hidden = false;
        }
      }
    } finally {
      setBusy(button, result, loading, false);
      updateCounter();
    }
  });

  document.addEventListener("lang-changed", () => {
    updateCounter();
    if (lastData) {
      result.replaceChildren(renderResultCard(lastData));
    }
  });

  updateCounter();
}
