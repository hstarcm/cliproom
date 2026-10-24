"""Observability (SPECS.md §7, SR-4, AC17).

- Prometheus metrics on /metrics (prometheus-client)
- OTel traces → OTLP collector → Tempo (manual spans only — FastAPI server
  spans are NOT instrumented because http.url attributes would carry room IDs,
  violating SR-4)
- Structured JSON logs with trace_id → OTLP → Loki
- No room IDs, member tokens, names, or filenames ever enter telemetry.
"""

from __future__ import annotations

import json
import logging
import sys
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# --- metrics (§7) ------------------------------------------------------------
uploads_total = Counter("cliproom_uploads", "File upload attempts", ["result"])
upload_duration = Histogram("cliproom_upload_duration_seconds", "Upload duration in seconds")
ws_clients = Gauge("cliproom_ws_clients", "Currently connected room WebSocket clients")
sweeper_last_success = Gauge(
    "cliproom_sweeper_last_success_timestamp",
    "Unix timestamp of the last successful sweeper run",
)
items_total = Counter("cliproom_items", "Items created", ["kind"])

TRACER = None
_OTLP_HANDLER = None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry["trace_id"] = _current_trace_id()
        return json.dumps(entry)


def _current_trace_id() -> str | None:
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            return format(ctx.trace_id, "032x")
    except Exception:  # noqa: BLE001 — telemetry must never break the app
        pass
    return None


def setup_telemetry(settings) -> None:
    global TRACER, _OTLP_HANDLER
    logging.basicConfig(level=settings.log_level, stream=sys.stdout, force=True)
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.setFormatter(JsonFormatter())

    # fresh deploy = healthy; real sweeps update it (prevents instant alert)
    sweeper_last_success.set(time.time())

    if not settings.otel_exporter_otlp_endpoint:
        logging.getLogger("cliproom.telemetry").info("OTel export disabled (no endpoint)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "cliproom-api"}))
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
            )
        )
        trace.set_tracer_provider(provider)
        TRACER = trace.get_tracer("cliproom")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("cliproom.telemetry").warning("trace export unavailable: %s", type(exc).__name__)

    try:
        pass  # type: ignore
    except Exception:
        pass
    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource

        logger_provider = LoggerProvider(resource=Resource.create({"service.name": "cliproom-api"}))
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/logs")
            )
        )
        handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        root.addHandler(handler)
        _OTLP_HANDLER = handler
        logging.getLogger("cliproom.telemetry").info(
            "otel export initialised: traces+logs -> %s", settings.otel_exporter_otlp_endpoint
        )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("cliproom.telemetry").warning("log export unavailable: %s", type(exc).__name__)


def tracer():
    """Manual span helper; no-op safe when OTel is not configured."""
    if TRACER is None:
        import contextlib

        @contextlib.contextmanager
        def _noop(name: str, **attrs):
            yield

        return _noop
    return TRACER.start_as_current_span


def metrics_response():
    from fastapi import Response

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
