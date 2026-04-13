from __future__ import annotations
import json, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

class SessionLogger:
    def __init__(self, log_dir: Path, session_id: str):
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"session_{session_id}.json"
        self._entries: list[dict] = []

    def log_event(self, event_type, data):
        self._entries.append({"timestamp": time.time(),
                               "event_type": event_type, "data": data})
        self._flush()

    def log_turn(self, turn_id, user_msg, assistant_msg, categories_updated,
                 gap_report_dict=None):
        data = {"turn_id": turn_id, "user_message": user_msg,
                "assistant_message": assistant_msg,
                "categories_updated": categories_updated}
        if gap_report_dict:
            data["gap_report"] = gap_report_dict
        self._entries.append({"timestamp": time.time(),
                               "event_type": "turn", "data": data})
        self._flush()

    def log_session_end(self, state):
        self.log_event("session_end", state.get_coverage_report())

    def get_log_path(self) -> Path:
        return self._log_path

    def _flush(self):
        try:
            with open(self._log_path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2, ensure_ascii=False)
        except Exception:
            pass