/**
 * Common helpers and constants for the web UI (specs 025 to 027).
 */

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
    el("p", { class: "banner-title" }, ["The request failed"]),
    el("p", {}, [error.message]),
  ];
  if (error.requestId) {
    children.push(el("p", { class: "caption" }, [`Request id: ${error.requestId}`]));
  }
  const banner = el("div", { class: "banner", role: "alert" }, children);
  slot.replaceChildren(banner);
}

export function clearError(slot) {
  slot.replaceChildren();
}

export function setBusy(button, region, bar, busy) {
  if (busy) {
    button.dataset.label = button.textContent || "";
    button.disabled = true;
    button.textContent = "Analyzing\u2026";
    region.setAttribute("aria-busy", "true");
    bar.hidden = false;
  } else {
    button.textContent = button.dataset.label || "Analyze";
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
