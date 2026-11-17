/**
 * Batch upload and heatmap flow (spec 026).
 */

import { ApiError, clearError, postBody, setBusy, showError } from "./common.js";
import { countText, renderCourse, renderHeatmap, renderSummary } from "./report.js";

export const MAX_UPLOAD_BYTES = 2097152;

export function checkFile(file) {
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return "Choose a file whose name ends in .csv.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "This file is over 2 MB. Choose a file of 2 MB or less.";
  }
  return null;
}

export async function sha256Hex(buffer) {
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function initBatch(panel) {
  const dropzone = panel.querySelector("#dropzone");
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

  function handleFile(file) {
    if (!file) {
      return;
    }
    const message = checkFile(file);
    if (message) {
      fileError.textContent = message;
      selectedFile = null;
      fileStatus.textContent = "No file selected.";
      analyzeBtn.disabled = true;
    } else {
      fileError.textContent = "";
      selectedFile = file;
      const sizeText = countText(file.size, "byte", "bytes");
      fileStatus.textContent = `Selected: ${file.name} (${sizeText})`;
      analyzeBtn.disabled = false;
    }
  }

  chooseFileBtn.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    handleFile(file);
  });

  dropzone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dropzone.classList.add("is-dragover");
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("is-dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("is-dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-dragover");
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    handleFile(file);
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
      showError(
        errors,
        new ApiError("The file could not be read. Choose it again.", null)
      );
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
      result.replaceChildren(
        renderSummary(response),
        renderHeatmap(response.courses),
        ...response.courses.map(renderCourse)
      );
      document.dispatchEvent(
        new CustomEvent("batch-loaded", {
          detail: { batchId, response },
        })
      );
    } catch (error) {
      showError(errors, error);
    } finally {
      setBusy(analyzeBtn, result, loading, false);
      analyzeBtn.disabled = !selectedFile;
    }
  });
}
