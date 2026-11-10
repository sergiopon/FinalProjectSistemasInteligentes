"""The six JSON routes of docs/contracts.md section 6, wired to the use cases by api.main."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, Request
from pydantic import ValidationError

from api.adapters.csv_reader import parse_csv_body, read_body_limited
from api.adapters.http_schemas import (
    BatchResponse,
    DriftReportJson,
    MetricsResponse,
    ModelInfoJson,
    PredictRequest,
    PredictResponse,
    batch_response,
    drift_report_json,
    metrics_response,
    model_info_json,
    predict_response,
)
from api.adapters.settings import LimitSettings
from api.application.analyze import AnalyzeBatch, AnalyzeComment
from api.application.course_report import BuildCourseReport
from api.domain.entities import Comment
from api.domain.errors import (
    InvalidInputError,
    ModelUnavailableError,
    UnsupportedMediaTypeError,
)
from api.domain.reports import ModelInfo
from api.ports.monitoring import DriftDetector, MetricsStore

LOGGER = logging.getLogger(__name__)
MS_PER_SECOND: float = 1000.0


@dataclass(frozen=True, slots=True)
class Services:
    """Collaborators of the routes, built once at startup."""

    model_info: ModelInfo
    analyze_comment: AnalyzeComment
    analyze_batch: AnalyzeBatch
    course_report: BuildCourseReport
    drift: DriftDetector
    metrics: MetricsStore
    limits: LimitSettings
    clock: Callable[[], str]


def services_of(request: Request) -> Services:
    """Return the services loaded at startup.

    Args:
        request: The current request.

    Returns:
        The services stored in the application state.

    Raises:
        ModelUnavailableError: The services are missing or of another type.
    """
    services: object = getattr(request.app.state, "services", None)
    if not isinstance(services, Services):
        raise ModelUnavailableError("services not loaded")
    return services


def media_type(request: Request) -> str:
    """Return the lowercase content type without parameters, or "" when absent."""
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * MS_PER_SECOND


async def _csv_body(request: Request, services: Services) -> bytes:
    """Read a text/csv body in memory within the upload limit."""
    if media_type(request) != "text/csv":
        raise UnsupportedMediaTypeError("expected text/csv")
    return await read_body_limited(
        request.stream(), request.headers.get("content-length"), services.limits
    )


async def health(request: Request) -> dict[str, str]:
    """Liveness of the service and the loaded model version."""
    return {"status": "ok", "model_version": services_of(request).model_info.version}


async def model(request: Request) -> ModelInfoJson:
    """Metadata of the active model."""
    return model_info_json(services_of(request).model_info)


async def predict(request: Request) -> PredictResponse:
    """Analyze one comment sent as application/json."""
    services = services_of(request)
    start = time.perf_counter()
    if media_type(request) != "application/json":
        raise UnsupportedMediaTypeError("predict expects application/json")
    try:
        payload = PredictRequest.model_validate_json(await request.body())
    except ValidationError as error:
        raise InvalidInputError("predict body failed validation") from error
    analysis = services.analyze_comment.execute(Comment(text=payload.text))
    services.metrics.record("/predict", _elapsed_ms(start), (analysis.decision.decision,))
    return predict_response(analysis, services.model_info.version)


async def predict_batch(request: Request) -> BatchResponse:
    """Analyze a text/csv upload and build the course reports."""
    services = services_of(request)
    start = time.perf_counter()
    body = await _csv_body(request, services)
    comments = parse_csv_body(body, services.limits)
    analyses = services.analyze_batch.execute(comments)
    reports = services.course_report.execute(comments, analyses)
    decisions = tuple(item.decision.decision for item in analyses)
    services.metrics.record("/predict-batch", _elapsed_ms(start), decisions)
    LOGGER.info("batch request_id=%s rows=%d", request.state.request_id, len(comments))
    return batch_response(analyses, reports, services.model_info.version)


async def drift(request: Request) -> DriftReportJson:
    """Compare a text/csv upload with the training reference."""
    services = services_of(request)
    body = await _csv_body(request, services)
    comments = parse_csv_body(body, services.limits)
    report = services.drift.compare(
        tuple(item.text for item in comments), hashlib.sha256(body).hexdigest(), services.clock()
    )
    services.metrics.record_drift(report)
    return drift_report_json(report)


async def metrics(request: Request) -> MetricsResponse:
    """Request counters, latency percentiles and the last drift report."""
    return metrics_response(services_of(request).metrics.snapshot())


def build_router() -> APIRouter:
    """Build the router with the six routes."""
    router = APIRouter()
    router.add_api_route("/health", health, methods=["GET"])
    router.add_api_route("/model", model, methods=["GET"])
    router.add_api_route("/predict", predict, methods=["POST"])
    router.add_api_route("/predict-batch", predict_batch, methods=["POST"])
    router.add_api_route("/drift", drift, methods=["POST"])
    router.add_api_route("/metrics", metrics, methods=["GET"])
    return router
