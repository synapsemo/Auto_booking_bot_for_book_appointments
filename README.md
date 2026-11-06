# GVC appointment bot (Python)

Python 3.11+ / Playwright appointment runner with persistent browser sessions,
date/time/centre/category filters, bounded polling, preview mode, and an optional
submission path with a durable booking journal.

**Status: the local browser workflow is implemented; live GVC integration and an
Imperva bypass are not implemented or verified.** The country-specific portal,
authenticated page structure, and appointment preferences have not been supplied.
`config.example.json` contains selectors for the local fixture, not discovered GVC
selectors. It is a template, not a working live-site configuration. This project
does not claim that Playwright, stealth plugins, curl_cffi, or ScrapFly guarantee
access. It currently detects challenges and stops for intervention.

## Install and run the demo

Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# Only if Chromium is not already installed:
.venv/bin/python -m playwright install chromium
.venv/bin/python -m demo.run
.venv/bin/python -m unittest discover -s tests -v
```

The cloud machine already has `/usr/bin/chromium`. The runner uses that when
available, or Playwright's installed browser otherwise. `BROWSER_EXECUTABLE`
overrides the path. Linux hosts may also need Playwright's documented browser OS
dependencies (`python -m playwright install --with-deps chromium`).

The demo launches a temporary local server and a real headless browser, finds the
earliest matching fixture slot, and asserts **zero selection clicks and zero
booking requests**. It deletes its temporary browser profile on exit. The test
suite also submits bookings only to the local fixture to exercise receipt
handling, review mismatches, and ambiguous submission recovery. No real account
or appointment is used by the demo or tests.

## Configure a portal

```bash
cp config.example.json config.local.json
```

Edit `config.local.json` with the exact appointment URL, centre, category, dates,
and verified selectors. Dates are inclusive `YYYY-MM-DD`; times are inclusive
24-hour `HH:MM` in the **visa centre's local time**, without timezone conversion.
The template uses 2030 fixture dates deliberately; replace them with your dates.
Relative profile and journal paths resolve relative to the configuration file.

The current adapter supports one availability page whose slot elements expose
ID, date, time, centre, and category attributes. Optional `form_values` maps CSS
selectors for HTML `<select>` elements to their option values. `ready` must only
be visible after the availability request completes, including filter changes.
Configure `empty` to match an explicit no-appointments message. `slot` must match
only actual appointment options, never a generic navigation or calendar button.

On sites with calendar pagination, frames, multi-step applicant forms, non-ISO
date strings, or separate APIs, implement the corresponding adapter behavior in
`gvc_bot/runner.py` after inspecting the real portal. Those flows cannot be
inferred from the homepage or the fixture. The current implementation will stop
on missing or ambiguous data instead of inventing slot details.

## Login and preview

On a machine with a display or a cloud desktop:

```bash
.venv/bin/python -m gvc_bot.cli login --config config.local.json
# Sign in inside the browser, then press Enter in the terminal.
.venv/bin/python -m gvc_bot.cli run --config config.local.json
```

Login is interactive. Passwords, OTPs, and passport information are not read from
chat or stored in config. Cookies persist in the ignored `.local/profile`
directory, which is sensitive: do not commit or share it. A session may expire
or be tied to a browser/network identity. An existing session does not guarantee
Imperva access. If the portal blocks access or presents a challenge, the runner
stops. It does not automatically solve CAPTCHAs or bypass Imperva.

The default run is preview-only, as requested for the first demo. It returns the
earliest match and never clicks a slot. An empty result is polled with increasing
delays and jitter, bounded by `max_checks`. `poll_seconds` must be at least 30.
HTTP 401/403/429, login screens, detected challenges, and unexpected markup stop
the run. Exit codes: `0` match/confirmation, `1` error, `2` checks exhausted,
`130` interrupted.

For a separately authorized real booking, the optional command is:

```bash
.venv/bin/python -m gvc_bot.cli run --config config.local.json --submit
```

This path requires the exact review fields and confirmation reference to be
configured and tested. Before any slot selection, a `pending` journal is saved.
The bot verifies the review's slot ID, date, time, centre, and category before
the final click. It records `confirmed` only after a confirmation and nonempty
reference appear. This does not validate applicant identity or payment forms;
those require a portal-specific adapter before real use.

If selection or submission has an uncertain outcome, the journal remains
`pending`; future runs refuse to proceed. Check the portal's booking history
manually before archiving a pending journal. Never delete it simply to retry.
Keep the same journal for the same applicant. A filesystem lock prevents
concurrent runs against that journal; browser profiles also must not be shared
by concurrent processes. After a process crash, confirm it is stopped before
removing a stale `.lock` file.

## Cloud network and live verification

The initial request to `https://gvcworld.eu` was denied by the **cloud egress
proxy** (CONNECT 403), before reaching the site. That was not an observed
Imperva response. Network draft additions for `gvcworld.eu` and
`www.gvcworld.eu` were saved; review/save them in environment settings and publish
the environment to activate the configuration. The country-specific portal and
its required hosts may need further additions after they are known.

Browser requests inherit `HTTPS_PROXY`; `BOT_PROXY_SERVER` can select an explicitly
configured proxy outside the managed environment. TLS verification remains on.
Loopback fixtures use local connections. No paid scraping service is required
or configured, and no account credentials are embedded in this repository.

Before calling this a working GVC auto-booking solution, the remaining work is:

1. Supply the exact country portal, centre/category, and appointment preferences.
2. Establish access and inspect the authenticated flow using a test account
   through a secure browser session.
3. Implement and test its real selectors/adapter and any required access strategy.
4. Demonstrate a live preview that stops before booking, as requested.

Passing the local tests does not satisfy those live acceptance criteria.
