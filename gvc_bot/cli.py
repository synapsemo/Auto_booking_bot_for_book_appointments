import argparse
import sys

from playwright.sync_api import sync_playwright

from .browser import launch
from .config import load_config
from .runner import Runner


def main():
    parser = argparse.ArgumentParser(description="Appointment browser runner; live portal integration requires verified selectors")
    parser.add_argument("command", choices=["login", "run"])
    parser.add_argument("--config", default="config.local.json")
    parser.add_argument("--submit", action="store_true", help="Enable real slot selection and final submission (default: preview only)")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == "login":
            config.headless = False
        with sync_playwright() as playwright:
            context = launch(playwright, config)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                if args.command == "login":
                    page.goto(config.portal_url, wait_until="domcontentloaded")
                    input("Complete login and any challenge in the browser. Press Enter here to save and close: ")
                    return 0
                result = Runner(page, config).run(submit=args.submit)
                return 0 if result["status"] in {"preview", "confirmed"} else 2
            finally:
                context.close()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # Browser exception text can contain credentials/URLs/HTML. Do not dump it.
        if isinstance(exc, (ValueError, RuntimeError, FileNotFoundError)):
            print(f"Stopped: {exc}", file=sys.stderr)
        else:
            print(f"Stopped: {type(exc).__name__}; check session, selectors and local booking journal before retrying.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
