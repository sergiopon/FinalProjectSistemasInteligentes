/**
 * Entry module for the web UI (specs 025 to 027).
 */

import { initBatch } from "./batch.js";
import { initTabs } from "./common.js";
import { initReview } from "./review.js";
import { initSingle } from "./single.js";

window.addEventListener("DOMContentLoaded", () => {
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
});
