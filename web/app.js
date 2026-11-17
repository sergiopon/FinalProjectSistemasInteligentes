/**
 * Entry module for the web UI (specs 025 to 027).
 */

import { initBatch } from "./batch.js";
import { icon, initTabs } from "./common.js";
import { SAMPLE_COMMENTS, getLang, setLang, t } from "./i18n.js";
import { initReview } from "./review.js";
import { initSingle } from "./single.js";

const HEALTH_INTERVAL_MS = 15000;

function applyLanguage(lang) {
  setLang(lang);
  document.documentElement.lang = lang;
  document.title = t("appTitle");
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-sample]")) {
    node.title = SAMPLE_COMMENTS[node.dataset.sample] || "";
  }
  for (const btn of document.querySelectorAll("[data-lang]")) {
    btn.setAttribute("aria-pressed", btn.dataset.lang === lang ? "true" : "false");
  }
  document.dispatchEvent(new CustomEvent("lang-changed", { detail: { lang } }));
  checkHealth();
}

let lastHealth = null;

function paintHealth() {
  const dot = document.getElementById("api-dot");
  const text = document.getElementById("api-status-text");
  if (!dot || !text) {
    return;
  }
  dot.className = "h-2 w-2 rounded-full";
  if (lastHealth === null) {
    dot.classList.add("bg-slate-300");
    text.textContent = t("apiChecking");
  } else if (lastHealth.ok) {
    dot.classList.add("bg-emerald-500");
    text.textContent = `${t("apiOnline")} · ${lastHealth.version}`;
  } else {
    dot.classList.add("bg-rose-500");
    text.textContent = t("apiOffline");
  }
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const body = response.ok ? await response.json() : null;
    lastHealth = body ? { ok: true, version: body.model_version || "" } : { ok: false };
  } catch {
    lastHealth = { ok: false };
  }
  paintHealth();
}

function init() {
  const mark = document.getElementById("brand-mark");
  if (mark) {
    mark.replaceChildren(icon("spark", 20));
  }
  const tablist = document.querySelector('[role="tablist"]');
  if (tablist) {
    initTabs(tablist);
  }
  for (const [id, start] of [
    ["panel-single", initSingle],
    ["panel-batch", initBatch],
    ["panel-review", initReview],
  ]) {
    const panel = document.getElementById(id);
    if (panel) {
      start(panel);
    }
  }
  for (const btn of document.querySelectorAll("[data-lang]")) {
    btn.addEventListener("click", () => {
      if (btn.dataset.lang !== getLang()) {
        applyLanguage(btn.dataset.lang);
      }
    });
  }
  applyLanguage("es");
  setInterval(checkHealth, HEALTH_INTERVAL_MS);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
