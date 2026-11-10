"""Composition root: process hardening, wiring, request context, error mapping and static files."""

from __future__ import annotations

import os

os.umask(0o077)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import json  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import FastAPI, Request, Response  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from api.adapters.anonymizer import SpacyAnonymizer  # noqa: E402
from api.adapters.explainer import OcclusionExplainer  # noqa: E402
from api.adapters.log_config import configure_logging  # noqa: E402
from api.adapters.model_store import TrustedModelStore  # noqa: E402
from api.adapters.monitoring import (  # noqa: E402
    InMemoryMetricsStore,
    ReferenceDriftDetector,
    utc_now_iso,
)
from api.adapters.settings import load_settings  # noqa: E402
from api.adapters.sklearn_models import SklearnAspectModel, SklearnPolarityModel  # noqa: E402
from api.adapters.text_analysis import CentroidSummarizer, KMeansTopicModel  # noqa: E402
from api.application.analyze import AnalyzeBatch, AnalyzeComment  # noqa: E402
from api.application.course_report import BuildCourseReport  # noqa: E402
from api.domain.decision import DecisionCosts  # noqa: E402
from api.domain.errors import AppError, ConfigError, ModelIntegrityError  # noqa: E402
from api.domain.safety import resolve_within  # noqa: E402
from api.routes import Services, build_router  # noqa: E402

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
CONFIG_PATH: Path = REPO_ROOT / "config" / "app.json"
WEB_DIR: Path = REPO_ROOT / "web"
ALPHA_TOLERANCE: float = 1e-9
SERVER_ERROR_STATUS: int = 500
LOGGER = logging.getLogger(__name__)
CLIENT_ERRORS: Mapping[str, tuple[int, str]] = types.MappingProxyType(
    {
        "internal_error": (500, "Internal error."),
        "invalid_input": (422, "The request is invalid."),
        "invalid_csv": (422, "The CSV file is invalid."),
        "payload_too_large": (413, "The upload exceeds the size limit."),
        "unsupported_media_type": (415, "Unsupported content type."),
        "not_found": (404, "Resource not found."),
        "model_unavailable": (503, "The model is not available."),
        "method_not_allowed": (405, "Method not allowed."),
    }
)
SECURITY_HEADERS: Mapping[str, str] = types.MappingProxyType(
    {
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cache-Control": "no-store",
    }
)


def apply_security_headers(response: Response) -> None:
    """Set the SEC-22 response headers."""
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value


def error_response(code: str, request_id: str) -> JSONResponse:
    """Build the client-facing error body for a stable error code."""
    status, message = CLIENT_ERRORS[code]
    body = {"error": code, "message": message, "request_id": request_id}
    return JSONResponse(body, status_code=status)


def _float_tuple(value: object, key: str) -> tuple[float, ...]:
    if not isinstance(value, tuple) or not all(isinstance(item, float) for item in value):
        raise ModelIntegrityError(f"bundle key {key} has an invalid type")
    return value


def _terms_tuple(value: object) -> tuple[tuple[str, ...], ...]:
    if isinstance(value, tuple) and all(
        isinstance(topic, tuple) and all(isinstance(term, str) for term in topic) for topic in value
    ):
        return tuple(tuple(str(term) for term in topic) for topic in value)
    raise ModelIntegrityError("bundle key topic_terms has an invalid type")


def _vocabulary(vectorizer: object) -> frozenset[str]:
    vocabulary = getattr(vectorizer, "vocabulary_", None)
    if not isinstance(vocabulary, dict):
        raise ModelIntegrityError("topic vectorizer has no vocabulary")
    return frozenset(str(term) for term in vocabulary)


def _read_reference(models_dir: Path, version: str) -> dict[str, object]:
    path = resolve_within(models_dir, Path(version) / "reference_stats.json")
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelIntegrityError("reference stats unreadable") from error
    if not isinstance(loaded, dict):
        raise ModelIntegrityError("reference stats are not an object")
    return loaded


def load_services(config_path: Path = CONFIG_PATH) -> Services:
    """Load the settings and the active bundle and wire the adapters and use cases.

    Args:
        config_path: Location of config/app.json.

    Returns:
        The services used by the routes.

    Raises:
        ConfigError: The configured alpha does not match the model confidence level.
        ModelIntegrityError: The bundle holds a value of an unexpected type.
    """
    configure_logging()
    settings = load_settings(config_path)
    store = TrustedModelStore(settings.models_dir)
    info = store.info()
    bundle = store.bundle()
    if abs((1 - settings.conformal.alpha) - info.confidence_level) > ALPHA_TOLERANCE:
        raise ConfigError("alpha does not match the model confidence level")
    polarity = SklearnPolarityModel(
        bundle["polarity_pipeline"], bundle["conformal_classifier"], info.confidence_level
    )
    aspects = SklearnAspectModel(
        bundle["aspect_pipeline"], _float_tuple(bundle["aspect_thresholds"], "aspect_thresholds")
    )
    anonymizer = SpacyAnonymizer()
    vectorizer = bundle["topic_vectorizer"]
    topics = KMeansTopicModel(
        vectorizer, bundle["topic_kmeans"], _terms_tuple(bundle["topic_terms"])
    )
    reference = _read_reference(settings.models_dir, info.version)
    costs = DecisionCosts(
        settings.costs.error_cost,
        settings.costs.review_cost,
        settings.costs.review_if_set_not_singleton,
    )
    LOGGER.info("startup model_version=%s", info.version)
    return Services(
        model_info=info,
        analyze_comment=AnalyzeComment(polarity, aspects, OcclusionExplainer(polarity), costs),
        analyze_batch=AnalyzeBatch(polarity, aspects, anonymizer, costs),
        course_report=BuildCourseReport(anonymizer, CentroidSummarizer(vectorizer), topics),
        drift=ReferenceDriftDetector(reference, _vocabulary(vectorizer)),
        metrics=InMemoryMetricsStore(),
        limits=settings.limits,
        clock=utc_now_iso,
    )


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request id, turn unhandled errors into a generic 500 and add the headers."""
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception("unhandled_error request_id=%s route=%s", request_id, request.url.path)
        response = error_response("internal_error", request_id)
    response.headers["X-Request-ID"] = request_id
    apply_security_headers(response)
    LOGGER.info(
        "request request_id=%s route=%s status=%d duration_ms=%.1f",
        request_id,
        request.url.path,
        response.status_code,
        (time.perf_counter() - start) * 1000.0,
    )
    return response


def _register_handlers(app: FastAPI) -> None:
    """Map application, validation and HTTP errors to the client error bodies."""

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        status = CLIENT_ERRORS.get(exc.code, CLIENT_ERRORS["internal_error"])[0]
        log = LOGGER.warning if status < SERVER_ERROR_STATUS else LOGGER.error
        log(
            "app_error request_id=%s code=%s detail=%s",
            request.state.request_id,
            exc.code,
            exc.detail,
        )
        return error_response(exc.code, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response("invalid_input", request.state.request_id)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return error_response(
            codes.get(exc.status_code, "internal_error"), request.state.request_id
        )


def build_app(factory: Callable[[], Services], web_dir: Path = WEB_DIR) -> FastAPI:
    """Build the application.

    Args:
        factory: Builds the services at startup; an exception aborts startup.
        web_dir: Directory of the static web interface.

    Returns:
        The FastAPI application.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = factory()
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.middleware("http")(request_context)
    _register_handlers(app)
    app.include_router(build_router())
    app.mount("/", StaticFiles(directory=web_dir, html=True, check_dir=False), name="web")
    return app


app: FastAPI = build_app(load_services)
