from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from poirot.backend.agents.journal.events import RunEvent, utc_now_iso


class RunJournal:
    def __init__(self, run_id: str, events_path: str | Path) -> None:
        self.run_id = run_id
        self.events_path = Path(events_path)

    def append(self, event_type: str, payload: dict[str, Any] | None = None) -> RunEvent:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        event = RunEvent(
            event_id=f"evt-{uuid4().hex}",
            run_id=self.run_id,
            event_type=event_type,
            payload=payload or {},
            created_at=utc_now_iso(),
        )
        with self.events_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event
