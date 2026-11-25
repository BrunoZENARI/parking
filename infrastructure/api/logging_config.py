import os
import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")

_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_QUIET_PATHS = {"/health", "/parking/occupation"}  # appelés en boucle par le dashboard

logger = logging.getLogger("parking.http")


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


def setup_logging() -> None:
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [parking] [cid=%(correlation_id)s] %(name)s: %(message)s"
    )
    handlers = [logging.StreamHandler()]
    log_file = os.getenv("LOG_FILE")
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for h in handlers:
        h.addFilter(CorrelationIdFilter())
        h.setFormatter(fmt)
    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(logging.INFO)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        incoming = request.headers.get("X-Correlation-ID", "")
        # L'identifiant est opaque : on rejette tout ce qui n'a pas la forme attendue
        cid = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("%s %s -> 500", request.method, request.url.path)
            raise
        else:
            ms = (time.perf_counter() - start) * 1000
            level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO
            logger.log(level, "%s %s -> %s (%.1f ms)",
                       request.method, request.url.path, response.status_code, ms)
            response.headers["X-Correlation-ID"] = cid
            return response
        finally:
            correlation_id_var.reset(token)