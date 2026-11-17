/**
 * Batch upload and heatmap flow (spec 026).
 */

import { ApiError, clearError, icon, stagger, postBody, setBusy, showError } from "./common.js";
import { t } from "./i18n.js";
import { countText, renderCourse, renderHeatmap, renderSummary } from "./report.js";

export const MAX_UPLOAD_BYTES = 2097152;

export function checkFile(file) {
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return t("errNotCsv");
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return t("errTooBig");
  }
  return null;
}

export async function sha256Hex(buffer) {
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

const DRAG_CLASSES = ["is-dragover", "border-brand-600", "bg-blue-100", "scale-[1.01]"];

export function initBatch(panel) {
  const dropzone = panel.querySelector("#dropzone");
  const dropText = panel.querySelector("#dropzone-text");
  const dropIcon = panel.querySelector("#drop-icon");
  const chooseFileBtn = panel.querySelector("#choose-file");
  const fileInput = panel.querySelector("#file-input");
  const fileStatus = panel.querySelector("#file-status");
  const fileError = panel.querySelector("#file-error");
  const analyzeBtn = panel.querySelector("#analyze-file");
  const loading = panel.querySelector("#batch-loading");
  const errors = panel.querySelector("#batch-errors");
  const result = panel.querySelector("#batch-result");
  const empty = panel.querySelector("#batch-empty");

  if (!dropzone || !chooseFileBtn || !fileInput || !fileStatus || !fileError || !analyzeBtn || !loading || !errors || !result) {
    return;
  }

  let selectedFile = null;
  let lastResponse = null;

  if (dropIcon) {
    dropIcon.replaceChildren(icon("upload", 24));
  }

  function showSelected() {
    fileStatus.textContent = selectedFile
      ? `${t("selected")}: ${selectedFile.name} (${countText(selectedFile.size, t("byte"), t("bytes"))})`
      : t("noFileSelected");
  }

  function renderResult() {
    if (!lastResponse) {
      return;
    }
    result.replaceChildren(
      renderSummary(lastResponse),
      renderHeatmap(lastResponse.courses),
      ...stagger(lastResponse.courses.map(renderCourse), 120)
    );
  }

  function setDrag(active) {
    for (const cls of DRAG_CLASSES) {
      dropzone.classList.toggle(cls, active);
    }
    if (dropText) {
      dropText.textContent = active ? t("dropzoneRelease") : t("dropzoneText");
    }
  }

  function handleFile(file) {
    if (!file) {
      return;
    }
    const message = checkFile(file);
    if (message) {
      fileError.textContent = message;
      selectedFile = null;
      analyzeBtn.disabled = true;
    } else {
      fileError.textContent = "";
      selectedFile = file;
      analyzeBtn.disabled = false;
    }
    showSelected();
  }

  document.addEventListener("lang-changed", () => {
    fileError.textContent = "";
    showSelected();
    renderResult();
  });

  chooseFileBtn.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", (e) => {
    handleFile(e.target.files && e.target.files[0]);
  });

  dropzone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    setDrag(true);
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    setDrag(true);
  });

  dropzone.addEventListener("dragleave", (e) => {
    if (!dropzone.contains(e.relatedTarget)) {
      setDrag(false);
    }
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    setDrag(false);
    handleFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
  });

  window.addEventListener("dragover", (e) => {
    e.preventDefault();
  });

  window.addEventListener("drop", (e) => {
    e.preventDefault();
  });

  analyzeBtn.addEventListener("click", async () => {
    if (!selectedFile) {
      return;
    }
    clearError(errors);
    setBusy(analyzeBtn, result, loading, true);
    let buffer;
    try {
      buffer = await selectedFile.arrayBuffer();
    } catch {
      showError(errors, new ApiError(t("errRead"), null));
      setBusy(analyzeBtn, result, loading, false);
      analyzeBtn.disabled = !selectedFile;
      return;
    }

    try {
      const response = await postBody("/predict-batch", buffer, "text/csv; charset=utf-8");
      const batchId = await sha256Hex(buffer);
      if (empty) {
        empty.hidden = true;
      }
      lastResponse = response;
      renderResult();
      document.dispatchEvent(new CustomEvent("batch-loaded", { detail: { batchId, response } }));
    } catch (error) {
      showError(errors, error);
    } finally {
      setBusy(analyzeBtn, result, loading, false);
      analyzeBtn.disabled = !selectedFile;
    }
  });
}
