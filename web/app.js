/**
 * Entry module for the web UI (specs 025 to 027).
 */

import { initBatch } from "./batch.js";
import { initTabs } from "./common.js";
import { getLang, setLang, t } from "./i18n.js";
import { initReview } from "./review.js";
import { initSingle } from "./single.js";

function applyLanguage(lang) {
  setLang(lang);
  const textMap = {
    "app-title": t("appTitle"),
    "app-intro": t("appIntro"),
    "tab-single": t("tabSingle"),
    "tab-batch": t("tabBatch"),
    "tab-review": t("tabReview"),
    "single-title": t("singleTitle"),
    "single-empty": t("singleEmpty"),
    "comment-label": t("commentLabel"),
    "analyze-button": t("analyzeBtn"),
    "samples-label": t("examplesLabel"),
    "batch-title": t("batchTitle"),
    "batch-empty": t("batchEmpty"),
    "dropzone-text": t("dropzoneText"),
    "choose-file": t("chooseFileBtn"),
    "file-hint": t("hintText"),
    "sample-csv-hint": t("sampleCsvHint"),
    "analyze-file": t("analyzeFileBtn"),
    "review-title": t("reviewTitle"),
    "review-empty": t("reviewEmpty"),
    "export-csv": t("exportBtn"),
    "review-caption": t("reviewCaption"),
  };
  for (const [id, val] of Object.entries(textMap)) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = val;
    }
  }
  const chips = document.querySelectorAll(".chip");
  if (chips.length >= 3) {
    chips[0].textContent = `⭐ ${t("exPositive")}`;
    chips[1].textContent = `⚠️ ${t("exMixed")}`;
    chips[2].textContent = `❌ ${t("exNegative")}`;
  }
  const toggle = document.getElementById("lang-toggle");
  if (toggle) {
    toggle.textContent = t("langToggle");
  }
}

function init() {
  const tablist = document.querySelector('[role="tablist"]');
  if (tablist) {
    initTabs(tablist);
  }
  const singlePanel = document.getElementById("panel-single");
  if (singlePanel) {
    initSingle(singlePanel);
  }
  const batchPanel = document.getElementById("panel-batch");
  if (batchPanel) {
    initBatch(batchPanel);
  }
  const reviewPanel = document.getElementById("panel-review");
  if (reviewPanel) {
    initReview(reviewPanel);
  }
  const langToggle = document.getElementById("lang-toggle");
  if (langToggle) {
    langToggle.addEventListener("click", () => {
      const nextLang = getLang() === "es" ? "en" : "es";
      applyLanguage(nextLang);
    });
  }
  applyLanguage("es");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
