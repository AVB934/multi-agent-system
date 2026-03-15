from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(trace_id: str, stage: str, message: str, **extra: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "stage": stage,
        "message": message,
    }
    payload.update(extra)
    logging.getLogger("mas").info(json.dumps(payload, separators=(",", ":")))

