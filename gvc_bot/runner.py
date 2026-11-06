import json
import random
import time
from dataclasses import asdict, dataclass
from datetime import date, time as clock_time
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as BrowserTimeout

from .state import StateStore


class PortalBlocked(RuntimeError):
    pass


class PortalChanged(RuntimeError):
    pass


@dataclass(frozen=True)
class Slot:
    id: str
    date: str
    time: str
    centre: str
    category: str


def matches(slot, config):
    slot_date = date.fromisoformat(slot.date)
    slot_time = clock_time.fromisoformat(slot.time)
    return (slot.centre == config.centre and slot.category == config.category
            and date.fromisoformat(config.date_from) <= slot_date <= date.fromisoformat(config.date_to)
            and clock_time.fromisoformat(config.time_from) <= slot_time <= clock_time.fromisoformat(config.time_to))


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}), flush=True)


class Runner:
    def __init__(self, page, config, *, sleep=time.sleep, log=emit):
        self.page, self.config = page, config.validate()
        self.sleep, self.log = sleep, log
        self.s = config.selectors
        self.store = StateStore(config.state_file)

    def guard(self, response=None):
        if response and response.status in {401, 403, 429}:
            raise PortalBlocked(f"Portal returned HTTP {response.status}; session or challenge intervention required")
        if response and response.status >= 400:
            raise PortalChanged(f"Portal returned HTTP {response.status}")
        if urlparse(self.page.url).netloc != urlparse(self.config.portal_url).netloc:
            raise PortalBlocked("Portal redirected to another host; verify the login flow")
        for key in ("challenge", "login"):
            selector = self.s.get(key)
            if selector and self.page.locator(selector).first.is_visible():
                raise PortalBlocked(f"Portal shows {key}; open a headed login session")
        content = self.page.locator("body").inner_text().lower()
        if any(marker in content for marker in ("incapsula incident id", "request unsuccessful. incident id", "verify you are human")):
            raise PortalBlocked("Browser challenge detected; no bypass has been established")

    def scan(self):
        response = self.page.goto(self.config.portal_url, wait_until="domcontentloaded")
        self.guard(response)
        self.page.locator(self.s["ready"]).wait_for(state="visible")
        for selector, value in self.config.form_values.items():
            self.page.locator(selector).select_option(value=value)
        # ready must indicate the completed availability result, not merely a page shell.
        self.page.locator(self.s["ready"]).wait_for(state="visible")
        self.guard()
        rows = self.page.locator(self.s["slot"])
        slots = []
        seen = set()
        for index in range(rows.count()):
            row = rows.nth(index)
            if not row.is_visible() or not row.is_enabled() or row.get_attribute("aria-disabled") == "true":
                continue
            values = {field: row.get_attribute(self.s[attr]) for field, attr in (
                ("id", "slot_id_attribute"), ("date", "date_attribute"), ("time", "time_attribute"),
                ("centre", "centre_attribute"), ("category", "category_attribute"))}
            if not all(values.values()):
                raise PortalChanged("A slot is missing required attributes; update the portal adapter")
            slot = Slot(**values)
            if slot.id in seen:
                raise PortalChanged("Duplicate slot identifiers; refusing ambiguous selection")
            seen.add(slot.id)
            try:
                accepted = matches(slot, self.config)
            except ValueError as exc:
                raise PortalChanged("Slot dates/times must be ISO YYYY-MM-DD and HH:MM") from exc
            if accepted:
                slots.append(slot)
        if rows.count() == 0 and not self.page.locator(self.s["empty"]).is_visible():
            raise PortalChanged("Neither slots nor an explicit empty result appeared")
        return sorted(slots, key=lambda slot: (slot.date, slot.time, slot.id))

    def submit(self, slot):
        if self.page.locator(self.s["confirmation"]).is_visible():
            raise PortalChanged("A confirmation is already visible; reconcile existing bookings first")
        # Journal before any slot click: some portals reserve on selection.
        self.store.write({"status": "pending", "slot": asdict(slot)})
        rows = self.page.locator(self.s["slot"])
        candidates = [rows.nth(i) for i in range(rows.count())
                      if rows.nth(i).get_attribute(self.s["slot_id_attribute"]) == slot.id]
        if len(candidates) != 1:
            raise PortalChanged("Selected slot disappeared or became ambiguous")
        candidates[0].click()
        self.page.locator(self.s["review"]).wait_for(state="visible")
        self.guard()
        for field, value in asdict(slot).items():
            actual = self.page.locator(self.s[f"review_{field}"]).inner_text().strip()
            if actual != value:
                raise PortalChanged(f"Booking review {field} does not match the selected slot")
        self.page.locator(self.s["submit"]).click()
        self.page.locator(self.s["confirmation"]).wait_for(state="visible")
        self.guard()
        reference = self.page.locator(self.s["confirmation_reference"]).inner_text().strip()
        if not reference:
            raise PortalChanged("Confirmation has no booking reference")
        self.store.write({"status": "confirmed", "slot": asdict(slot), "reference": reference})
        self.log("confirmed")  # Keep confirmation identifiers out of console logs.
        return {"status": "confirmed", "slot": asdict(slot)}

    def run(self, *, submit=False):
        with self.store.lock():
            if self.store.read() is not None:
                raise RuntimeError("A prior booking journal exists; reconcile it with the portal before another run")
            for check in range(1, self.config.max_checks + 1):
                try:
                    slots = self.scan()
                    if slots:
                        slot = slots[0]
                        if submit:
                            return self.submit(slot)
                        self.log("preview", slot=asdict(slot))
                        return {"status": "preview", "slot": asdict(slot)}
                    self.log("no_match", check=check)
                except BrowserTimeout:
                    # Never retry once a selection/submission could have happened.
                    if self.store.read() is not None or check == self.config.max_checks:
                        raise
                    self.log("timeout", check=check)
                if check < self.config.max_checks:
                    delay = min(self.config.poll_seconds * (2 ** min(check - 1, 4)), 900)
                    self.sleep(delay + random.uniform(0, delay * 0.1))
            return {"status": "exhausted"}
