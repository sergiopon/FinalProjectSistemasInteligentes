/**
 * CSV export helpers for the review queue (spec 027).
 */

export const FORMULA_PREFIXES = ["=", "+", "-", "@", "\t", "\r"];
export const EXPORT_FILE_NAME = "review-queue.csv";
export const EXPORT_HEADER = [
  "row",
  "course",
  "comment",
  "predicted",
  "prediction_set",
  "reason",
  "review_action",
  "final_label",
];

export function escapeCell(value) {
  let str = String(value ?? "");
  for (const prefix of FORMULA_PREFIXES) {
    if (str.startsWith(prefix)) {
      str = "'" + str;
      break;
    }
  }
  const escaped = str.replaceAll('"', '""');
  return `"${escaped}"`;
}

export function buildQueueCsv(rows, decisions) {
  const headerLine = EXPORT_HEADER.map(escapeCell).join(",");
  const lines = [headerLine];

  for (const r of rows) {
    const rowKey = String(r.row);
    const decision = decisions && decisions[rowKey];
    const confSet = Array.isArray(r.conformal_set) ? r.conformal_set.join("|") : "";
    const action = (decision && decision.action) ?? "";
    const label = (decision && decision.label) ?? "";

    const cells = [
      escapeCell(r.row),
      escapeCell(r.course ?? ""),
      escapeCell(r.text ?? ""),
      escapeCell(r.predicted ?? ""),
      escapeCell(confSet),
      escapeCell(r.reason ?? ""),
      escapeCell(action),
      escapeCell(label),
    ];
    lines.push(cells.join(","));
  }

  return "\ufeff" + lines.join("\r\n") + "\r\n";
}

export function downloadCsv(text, fileName) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
