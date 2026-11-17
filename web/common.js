/**
 * Common helpers and constants for the web UI (specs 025 to 027).
 */

import { t } from "./i18n.js";

export const POLARITY_ORDER = Object.freeze(["negative", "neutral", "positive"]);

export const ASPECT_ORDER = Object.freeze([
  "content",
  "assessment",
  "feedback",
  "methodology_clarity",
  "materials",
  "organization_schedule",
  "platform",
  "communication_climate",
  "workload_pace",
]);

export const ASPECT_NAMES = Object.freeze({
  content: "Content",
  assessment: "Assessment",
  feedback: "Feedback",
  methodology_clarity: "Methodology and clarity",
  materials: "Materials",
  organization_schedule: "Organization and schedule",
  platform: "Platform",
  communication_climate: "Communication and climate",
  workload_pace: "Workload and pace",
});

export const ASPECT_NAMES_ES = Object.freeze({
  content: "Contenido",
  assessment: "Evaluación",
  feedback: "Retroalimentación",
  methodology_clarity: "Metodología y claridad",
  materials: "Materiales",
  organization_schedule: "Organización y horario",
  platform: "Plataforma",
  communication_climate: "Comunicación y clima",
  workload_pace: "Ritmo y carga de trabajo",
});

export const REASON_TEXT = Object.freeze({
  empty_set: "No class reached the confidence level",
  set_not_singleton: "More than one class is plausible",
  label_outside_set: "Top class is outside the prediction set",
  expected_cost: "Confidence below the review threshold",
});

export const REASON_TEXT_ES = Object.freeze({
  empty_set: "Ninguna clase alcanzó el nivel de confianza",
  set_not_singleton: "Más de una clase es plausible",
  label_outside_set: "La clase predicha está fuera del conjunto conformal",
  expected_cost: "Confianza por debajo del umbral de revisión",
});

export function getAspectName(group, lang = "es") {
  if (lang === "es") {
    return ASPECT_NAMES_ES[group] || ASPECT_NAMES[group] || group;
  }
  return ASPECT_NAMES[group] || group;
}

export function getReasonText(reason, lang = "es") {
  if (lang === "es") {
    return REASON_TEXT_ES[reason] || REASON_TEXT[reason] || reason;
  }
  return REASON_TEXT[reason] || reason;
}

export function formatPercent(value) {
  return `${Math.round(value * 100)} %`;
}

export function formatScore(value) {
  return value.toFixed(2);
}

export function el(tag, attributes = {}, children = []) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value !== null && value !== undefined) {
      element.setAttribute(key, String(value));
    }
  }
  for (const child of children) {
    if (typeof child === "string") {
      element.append(document.createTextNode(child));
    } else if (child) {
      element.append(child);
    }
  }
  return element;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const ICON_PATHS = Object.freeze({
  spark: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15z",
  upload: "M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2",
  check: "M5 13l4 4L19 7",
  alert: "M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
  user: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM4 21v-1a6 6 0 016-6h4a6 6 0 016 6v1",
  edit: "M4 20h4L19 9a2.8 2.8 0 00-4-4L4 16v4z",
  flag: "M5 21V4m0 0h11l-2 4 2 4H5",
});

export function icon(name, size = 18) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICON_PATHS[name] || "");
  svg.append(path);
  return svg;
}

export function stagger(nodes, stepMs = 60) {
  nodes.forEach((node, index) => {
    node.classList.add("animate-fade-up");
    node.style.animationDelay = `${index * stepMs}ms`;
  });
  return nodes;
}

export function countUp(node, target, format = (n) => String(Math.round(n)), durationMs = 800) {
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !Number.isFinite(target)) {
    node.textContent = format(target);
    return;
  }
  const start = performance.now();
  function frame(now) {
    const progress = Math.min(1, (now - start) / durationMs);
    const eased = 1 - Math.pow(1 - progress, 3);
    node.textContent = format(target * eased);
    if (progress < 1) {
      requestAnimationFrame(frame);
    }
  }
  requestAnimationFrame(frame);
}

export class ApiError extends Error {
  constructor(message, requestId = null) {
    super(message);
    this.name = "ApiError";
    this.requestId = requestId;
  }
}

async function request(path, init) {
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new ApiError(
        "The server did not respond. Check that the service is running.",
        null
      );
    }
    throw error;
  }
  const headerId = response.headers.get("X-Request-ID");
  let body = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    const message = body && typeof body.message === "string" ? body.message : "The request failed.";
    const requestId = (body && body.request_id) || headerId || null;
    throw new ApiError(message, requestId);
  }
  if (body === null) {
    throw new ApiError("The server returned an unexpected response.", headerId || null);
  }
  return body;
}

export async function postJson(path, payload) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function postBody(path, body, contentType) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": contentType },
    body,
  });
}

export function showError(slot, error) {
  const children = [
    el("p", { class: "font-semibold" }, [t("errorTitle")]),
    el("p", { class: "text-sm" }, [error.message]),
  ];
  if (error.requestId) {
    children.push(el("p", { class: "mt-1 text-xs opacity-90" }, [`${t("requestId")}: ${error.requestId}`]));
  }
  const banner = el(
    "div",
    { class: "mt-4 rounded-lg border border-red-700 bg-red-600 p-4 text-white shadow-pop animate-pop", role: "alert" },
    children
  );
  slot.replaceChildren(banner);
}

export function clearError(slot) {
  slot.replaceChildren();
}

export function setBusy(button, region, bar, busy) {
  if (busy) {
    button.dataset.label = button.textContent || "";
    button.disabled = true;
    button.textContent = t("analyzing");
    region.setAttribute("aria-busy", "true");
    bar.hidden = false;
  } else {
    button.textContent = button.dataset.label || t("analyzeBtn");
    button.disabled = false;
    region.setAttribute("aria-busy", "false");
    bar.hidden = true;
  }
}

export function initTabs(tablist) {
  const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
  function activateTab(target) {
    for (const tab of tabs) {
      const isTarget = tab === target;
      tab.setAttribute("aria-selected", isTarget ? "true" : "false");
      tab.setAttribute("tabindex", isTarget ? "0" : "-1");
      const panelId = tab.getAttribute("aria-controls");
      if (panelId) {
        const panel = document.getElementById(panelId);
        if (panel) {
          panel.hidden = !isTarget;
        }
      }
    }
    const targetPanelId = target.getAttribute("aria-controls") || "";
    document.dispatchEvent(
      new CustomEvent("tab-shown", { detail: { panelId: targetPanelId } })
    );
  }

  tablist.addEventListener("click", (event) => {
    const tab = event.target.closest('[role="tab"]');
    if (tab && tabs.includes(tab)) {
      activateTab(tab);
    }
  });

  tablist.addEventListener("keydown", (event) => {
    const current = document.activeElement;
    const index = tabs.indexOf(current);
    if (index === -1) {
      return;
    }
    let nextIndex = null;
    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % tabs.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = tabs.length - 1;
    }
    if (nextIndex !== null) {
      event.preventDefault();
      const target = tabs[nextIndex];
      target.focus();
      activateTab(target);
    }
  });
}
