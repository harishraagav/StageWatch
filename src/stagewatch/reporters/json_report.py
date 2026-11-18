from __future__ import annotations

import json

from ..models import RunRecord


def render_json(run: RunRecord) -> str:
    return json.dumps(run.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)
