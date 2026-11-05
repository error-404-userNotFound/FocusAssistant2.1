"""Single-process state, exclusive instance lock, atomic private JSON writes."""
from dataclasses import fields
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile

from .models import Control, Event, LABELS, Session, Settings, State


class StorageError(RuntimeError):
    pass


def timestamp(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def decode(data):
    if not isinstance(data, dict) or data.get("format_version") != 2:
        raise StorageError("Unsupported or damaged state file. The original file has been preserved.")
    state = State()
    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        raise StorageError("Saved settings are malformed; the file has been preserved.")
    state.settings = Settings(**{f.name: settings.get(f.name, f.default) for f in fields(Settings)})
    if not all(isinstance(v, bool) if k == "auto_close" else isinstance(v, str)
               for k, v in vars(state.settings).items()):
        raise StorageError("Saved settings contain invalid values; the file has been preserved.")
    state.storage_warnings = [w for w in data.get("storage_warnings", []) if isinstance(w, str)]
    for key, cls in (("sessions", Session), ("controls", Control), ("pages", Event), ("applications", Event)):
        rows = data.get(key, [])
        if not isinstance(rows, list):
            raise StorageError(f"Saved {key} is not a list; the file has been preserved.")
        seen = set()
        for row in rows:
            try:
                obj = cls(**row)
                if cls is Session:
                    valid = (isinstance(obj.id, str) and isinstance(obj.task, str)
                             and timestamp(obj.started_at) and isinstance(obj.paused, bool)
                             and (obj.ended_at is None or timestamp(obj.ended_at) and obj.ended_at >= obj.started_at))
                elif cls is Control:
                    valid = (isinstance(obj.session_id, str) and timestamp(obj.occurred_at)
                             and obj.kind in ("started", "paused", "resumed", "ended"))
                else:
                    valid = (timestamp(obj.occurred_at) and obj.label in LABELS
                             and obj.kind in ("webpage", "application")
                             and obj.source in ("pending", "model", "rule", "cache", "override", "unavailable")
                             and all(isinstance(getattr(obj, k), str) for k in
                                     ("id", "session_id", "url", "title", "host", "cache_key", "reason", "bundle", "page_key"))
                             and isinstance(obj.is_override, bool)
                             and isinstance(obj.attempts, int) and 0 <= obj.attempts <= 3
                             and isinstance(obj.override_note, str)
                             and (obj.closed_at is None or timestamp(obj.closed_at))
                             and (obj.intervention is None or isinstance(obj.intervention, str)))
                identity = getattr(obj, "id", None)
                if not valid or identity is not None and identity in seen:
                    raise ValueError("Invalid or duplicate record")
                seen.add(identity)
                getattr(state, key).append(obj)
            except (TypeError, ValueError, AttributeError):
                state.storage_warnings.append(f"Skipped a malformed or duplicate {key} record.")
    cache = data.get("cache", {})
    if isinstance(cache, dict):
        state.cache = {k: v for k, v in cache.items() if isinstance(k, str) and isinstance(v, dict)
                       and v.get("label") in LABELS and isinstance(v.get("reason"), str)
                       and v.get("source") in ("rule", "model", "override")}
    current_id = data.get("current_session_id")
    state.current_session_id = current_id if isinstance(current_id, str) else None
    heartbeat = data.get("last_heartbeat")
    state.last_heartbeat = heartbeat if timestamp(heartbeat) else None
    state.revision = data.get("revision", 0) if isinstance(data.get("revision", 0), int) else 0
    state.storage_warnings = sorted(set(state.storage_warnings))
    return state


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "state.json"
        self.lock = (self.directory / "instance.lock").open("a+")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.lock.close()
            raise StorageError("Focus Assistant is already using this data directory.") from exc
        try:
            self.state = decode(json.loads(self.path.read_text())) if self.path.exists() else State()
        except (ValueError, OSError, StorageError, TypeError) as exc:
            self.close()
            raise StorageError(f"Cannot read saved sessions: {exc} The saved file has been preserved.") from exc

    def save(self):
        self.state.revision += 1
        fd, temporary = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(self.state.to_dict(), handle, allow_nan=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def close(self):
        if not self.lock.closed:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()
