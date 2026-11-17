"""Preview server for the Web UI (serves static web/ and handles API endpoints)."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self) -> None:
        for header, val in SECURITY_HEADERS.items():
            self.send_header(header, val)
        self.send_header("X-Request-ID", uuid.uuid4().hex)
        super().end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            body = json.dumps({"status": "ok", "model_version": "preview"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        if self.path == "/predict":
            self._handle_predict(raw_body)
        elif self.path == "/predict-batch":
            self._handle_predict_batch(raw_body)
        else:
            self.send_error(404, "Not Found")

    def _handle_predict(self, raw_body: bytes) -> None:
        try:
            data = json.loads(raw_body.decode("utf-8"))
            text = str(data.get("text", "")).strip()
        except Exception:
            self.send_error(422, "Invalid input")
            return

        text_lower = text.lower()
        # Keyword heuristic: this is a MOCK, not the trained model.
        neg_words = [
            "difícil", "dificil", "injust", "malo", "mala", "mal ", "tarde", "pésim", "pesim", "horrible",
            "pesada", "desmedid", "nunca", "no correspond", "no sirve", "asquerosa", "asqueroso",
            "suspend", "ojala", "ojalá", "terrible", "aburrid", "deficiente", "no llegó", "no llego",
            "falta de", "excesiv", "caótic", "caotic", "pobre",
        ]
        pos_words = [
            "excelent", "claro", "claras", "bueno", "buena", "gustó", "gusto", "increíble", "increible",
            "aprend", "recomiendo", "completo", "interesante", "genial", "fantástic", "fantastic",
        ]
        is_neg = any(w in text_lower for w in neg_words)
        is_pos = any(w in text_lower for w in pos_words)
        is_mixed = is_neg and is_pos

        if is_mixed:
            predicted = "neutral"
            probs = {"negative": 0.42, "neutral": 0.46, "positive": 0.12}
            conformal_set = ["negative", "neutral"]
            decision = "review"
            reason = "set_not_singleton"
        elif is_neg:
            predicted = "negative"
            probs = {"negative": 0.78, "neutral": 0.18, "positive": 0.04}
            conformal_set = ["negative"]
            decision = "classify"
            reason = "confident"
        elif is_pos:
            predicted = "positive"
            probs = {"negative": 0.05, "neutral": 0.18, "positive": 0.77}
            conformal_set = ["positive"]
            decision = "classify"
            reason = "confident"
        else:
            predicted = "neutral"
            probs = {"negative": 0.31, "neutral": 0.38, "positive": 0.31}
            conformal_set = ["negative", "neutral", "positive"]
            decision = "review"
            reason = "set_not_singleton"

        aspects = []
        if any(w in text_lower for w in ["parcial", "examen", "evaluacion", "evaluación", "nota"]):
            aspects.append({"group": "assessment", "polarity": "negative" if is_neg else "positive", "score": 0.91})
        if any(w in text_lower for w in ["profesor", "profe", "clase", "explic", "metodolog"]):
            aspects.append({"group": "methodology_clarity", "polarity": "negative" if is_neg else "positive", "score": 0.88})
        if any(w in text_lower for w in ["contenido", "tema", "temas", "material"]):
            aspects.append({"group": "content", "polarity": "positive" if is_pos else "neutral", "score": 0.85})
        if not aspects:
            aspects.append({"group": "content", "polarity": predicted, "score": 0.75})

        words = [w for w in text.split() if len(w) > 3]
        influences = []
        if words:
            influences.append({"word": words[0], "delta": 0.28})
            if len(words) > 1:
                influences.append({"word": words[-1], "delta": -0.12})

        response = {
            "model_version": "v001",
            "text": text,
            "predicted": predicted,
            "probabilities": probs,
            "conformal_set": conformal_set,
            "confidence_level": 0.9,
            "decision": decision,
            "reason": reason,
            "aspects": aspects,
            "influences": influences,
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def _handle_predict_batch(self, raw_body: bytes) -> None:
        try:
            stream = io.StringIO(raw_body.decode("utf-8-sig", errors="replace"))
            reader = csv.DictReader(stream)
            rows = []
            courses = {}
            row_idx = 1
            classify_cnt = 0
            review_cnt = 0

            for r in reader:
                feedback = r.get("feedback") or r.get("comentario") or r.get("text") or "Comentario de curso"
                course = r.get("curso") or r.get("course") or "Curso General"
                
                # simulate prediction
                f_lower = feedback.lower()
                is_neg = any(w in f_lower for w in ["difícil", "injusto", "malo", "tarde", "pésimo", "pesada", "no"])
                is_mixed = "pero" in f_lower or "aunque" in f_lower
                if is_mixed:
                    predicted = "neutral"
                    decision = "review"
                    reason = "set_not_singleton"
                    conformal = ["negative", "neutral"]
                    probs = {"negative": 0.44, "neutral": 0.48, "positive": 0.08}
                    review_cnt += 1
                elif is_neg:
                    predicted = "negative"
                    decision = "classify"
                    reason = "confident"
                    conformal = ["negative"]
                    probs = {"negative": 0.82, "neutral": 0.15, "positive": 0.03}
                    classify_cnt += 1
                else:
                    predicted = "positive"
                    decision = "classify"
                    reason = "confident"
                    conformal = ["positive"]
                    probs = {"negative": 0.04, "neutral": 0.16, "positive": 0.80}
                    classify_cnt += 1

                row_obj = {
                    "row": row_idx,
                    "course": course,
                    "text": feedback,
                    "predicted": predicted,
                    "probabilities": probs,
                    "conformal_set": conformal,
                    "decision": decision,
                    "reason": reason,
                    "aspects": [{"group": "content", "polarity": predicted, "score": 0.82}],
                }
                rows.append(row_obj)

                if course not in courses:
                    courses[course] = {"comments": [], "reviews": 0, "neg": 0, "neu": 0, "pos": 0}
                courses[course]["comments"].append(feedback)
                if decision == "review":
                    courses[course]["reviews"] += 1
                if predicted == "negative":
                    courses[course]["neg"] += 1
                elif predicted == "neutral":
                    courses[course]["neu"] += 1
                else:
                    courses[course]["pos"] += 1

                row_idx += 1
                if row_idx > 5000:
                    break

            course_reports = []
            for c_name, c_data in courses.items():
                total_c = len(c_data["comments"])
                neg_share = round(c_data["neg"] / total_c, 4) if total_c else 0.0
                aspect_cells = [
                    {"group": "content", "mentions": total_c, "negative": c_data["neg"], "neutral": c_data["neu"], "positive": c_data["pos"], "negative_share": neg_share},
                    {"group": "assessment", "mentions": max(1, total_c // 2), "negative": max(1, c_data["neg"] // 2), "neutral": 1, "positive": 1, "negative_share": 0.45},
                    {"group": "feedback", "mentions": max(1, total_c // 3), "negative": 1, "neutral": 1, "positive": 1, "negative_share": 0.25},
                    {"group": "methodology_clarity", "mentions": max(1, total_c // 2), "negative": 0, "neutral": 1, "positive": 3, "negative_share": 0.05},
                    {"group": "materials", "mentions": 0, "negative": 0, "neutral": 0, "positive": 0, "negative_share": None},
                    {"group": "organization_schedule", "mentions": 2, "negative": 1, "neutral": 1, "positive": 0, "negative_share": 0.5},
                    {"group": "platform", "mentions": 0, "negative": 0, "neutral": 0, "positive": 0, "negative_share": None},
                    {"group": "communication_climate", "mentions": 1, "negative": 0, "neutral": 0, "positive": 1, "negative_share": 0.0},
                    {"group": "workload_pace", "mentions": max(1, total_c // 4), "negative": 1, "neutral": 1, "positive": 0, "negative_share": 0.6},
                ]
                priorities = [
                    {"rank": 1, "group": "assessment", "mentions": max(1, total_c // 2), "negative": max(1, c_data["neg"] // 2), "prevalence": 0.5, "smoothed_negative_share": 0.45, "score": 0.22, "low_support": total_c < 5},
                    {"rank": 2, "group": "workload_pace", "mentions": max(1, total_c // 4), "negative": 1, "prevalence": 0.25, "smoothed_negative_share": 0.6, "score": 0.15, "low_support": True},
                ]
                topics = [
                    {"topic": 0, "size": max(1, total_c // 2), "terms": ["parciales", "tiempo", "ejercicios"], "quote": c_data["comments"][0]},
                    {"topic": 1, "size": max(1, total_c // 2), "terms": ["claridad", "explicacion", "temas"], "quote": c_data["comments"][-1]},
                ]
                course_reports.append({
                    "course": c_name,
                    "comment_count": total_c,
                    "review_count": c_data["reviews"],
                    "polarity_counts": {"negative": c_data["neg"], "neutral": c_data["neu"], "positive": c_data["pos"]},
                    "aspects": aspect_cells,
                    "priorities": priorities,
                    "topics": topics,
                    "quotes": c_data["comments"][:3],
                })

            response = {
                "model_version": "v001",
                "row_count": len(rows),
                "decision_counts": {"classify": classify_cnt, "review": review_cnt},
                "rows": rows,
                "courses": course_reports,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

        except Exception as exc:
            self.send_error(422, f"Invalid CSV: {exc}")


def run() -> None:
    port = 8000
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, PreviewHandler)
    print(f"Server running at http://127.0.0.1:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
