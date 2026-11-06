import json
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Config:
    portal_url: str
    centre: str
    category: str
    date_from: str
    date_to: str
    selectors: dict[str, str]
    time_from: str = "00:00"
    time_to: str = "23:59"
    poll_seconds: float = 60
    max_checks: int = 10
    timeout_ms: int = 15000
    headless: bool = False
    profile_dir: str = ".local/profile"
    state_file: str = ".local/booking.json"
    # Optional form select elements; values must match portal option values.
    form_values: dict[str, str] = field(default_factory=dict)

    def validate(self):
        url = urlparse(self.portal_url)
        local = url.hostname in {"127.0.0.1", "localhost", "::1"}
        if not url.hostname or (url.scheme != "https" and not (local and url.scheme == "http")):
            raise ValueError("portal_url must use HTTPS (HTTP allowed for local fixtures)")
        if url.username or url.password:
            raise ValueError("Do not put credentials in portal_url")
        if not self.centre.strip() or not self.category.strip():
            raise ValueError("centre and category are required")
        if date.fromisoformat(self.date_from) > date.fromisoformat(self.date_to):
            raise ValueError("date_from must not be after date_to")
        if time.fromisoformat(self.time_from) > time.fromisoformat(self.time_to):
            raise ValueError("time_from must not be after time_to")
        if self.poll_seconds < 30 or self.max_checks < 1 or self.timeout_ms < 100:
            raise ValueError("poll_seconds >= 30, max_checks >= 1 and timeout_ms >= 100 required")
        required = {"ready", "slot", "slot_id_attribute", "date_attribute", "time_attribute",
                    "centre_attribute", "category_attribute", "empty", "review", "review_id",
                    "review_date", "review_time", "review_centre", "review_category", "submit",
                    "confirmation", "confirmation_reference"}
        missing = [key for key in required if not isinstance(self.selectors.get(key), str)
                   or not self.selectors[key].strip()]
        if missing:
            raise ValueError(f"Missing selectors: {', '.join(sorted(missing))}")
        return self


def load_config(path: str) -> Config:
    source = Path(path).resolve()
    config = Config(**json.loads(source.read_text())).validate()
    for key in ("profile_dir", "state_file"):
        target = Path(getattr(config, key))
        if not target.is_absolute():
            setattr(config, key, str(source.parent / target))
    return config
