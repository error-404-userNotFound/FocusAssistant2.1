from dataclasses import asdict, dataclass, field
import time
import uuid

LABELS = ("relevant", "uncertain", "distracting")
BROWSERS = {"com.apple.Safari": "Safari", "com.google.Chrome": "Google Chrome"}


def identifier():
    return str(uuid.uuid4())


@dataclass
class Settings:
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = ""
    relevant_domains: str = ""
    distracting_domains: str = ""
    relevant_keywords: str = ""
    distracting_keywords: str = ""
    auto_close: bool = False


@dataclass
class Session:
    id: str
    task: str
    started_at: float
    ended_at: float | None = None
    paused: bool = False


@dataclass
class Control:
    session_id: str
    occurred_at: float
    kind: str


@dataclass
class Event:
    id: str
    session_id: str
    occurred_at: float
    kind: str
    url: str
    title: str
    host: str
    cache_key: str
    label: str = "uncertain"
    reason: str = "Waiting for classification."
    source: str = "pending"
    intervention: str | None = None
    is_override: bool = False
    page_key: str = ""
    bundle: str = ""
    attempts: int = 0
    override_note: str = ""
    closed_at: float | None = None


@dataclass(frozen=True)
class Snapshot:
    bundle: str
    app_name: str
    url: str = ""
    title: str = ""
    text: str = ""
    window_id: str = ""
    tab_id: str = ""
    error: str = ""
    text_source: str = ""
    document_id: str = ""
    process_id: int = 0
    page_fullscreen: bool = False
    observed_at: float = field(default_factory=time.time)


@dataclass
class Decision:
    label: str
    reason: str
    source: str
    attempts: int = 1


@dataclass(frozen=True)
class OverrideVerdict:
    approved: bool
    reason: str


@dataclass
class State:
    settings: Settings = field(default_factory=Settings)
    sessions: list[Session] = field(default_factory=list)
    controls: list[Control] = field(default_factory=list)
    pages: list[Event] = field(default_factory=list)
    applications: list[Event] = field(default_factory=list)
    cache: dict = field(default_factory=dict)
    current_session_id: str | None = None
    last_heartbeat: float | None = None
    storage_warnings: list[str] = field(default_factory=list)
    revision: int = 0

    @property
    def current(self):
        return next((s for s in self.sessions if s.id == self.current_session_id and s.ended_at is None), None)

    def to_dict(self):
        return {"format_version": 2, **asdict(self)}
