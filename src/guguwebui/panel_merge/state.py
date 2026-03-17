from __future__ import annotations

import datetime
from typing import Any, Dict

from fastapi import FastAPI


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def get_pairing_state(app: FastAPI) -> Dict[str, Any]:
    state = getattr(app.state, "pairing_state", None)
    if state is None:
        state = {
            "enabled_until": None,  # datetime
            "pending": {},  # request_id -> {ip,name,created_at}
            "results": {},  # request_id -> {status, token?}
            "connects": {},  # connect_id -> {base_url, request_id, slave_name, created_at}
        }
        app.state.pairing_state = state
    return state

