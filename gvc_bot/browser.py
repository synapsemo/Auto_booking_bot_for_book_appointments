import os
import shutil
from pathlib import Path
from urllib.parse import urlparse


def launch(playwright, config):
    profile = Path(config.profile_dir)
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile.chmod(0o700)
    options = {"headless": config.headless, "accept_downloads": False}
    executable = os.environ.get("BROWSER_EXECUTABLE") or shutil.which("chromium")
    if executable:
        options["executable_path"] = executable
    # Keep cloud egress through its configured proxy. Local tests stay local.
    if urlparse(config.portal_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        proxy = os.environ.get("BOT_PROXY_SERVER") or os.environ.get("HTTPS_PROXY")
        if proxy:
            options["proxy"] = {"server": proxy}
    context = playwright.chromium.launch_persistent_context(str(profile), **options)
    context.set_default_timeout(config.timeout_ms)
    context.set_default_navigation_timeout(config.timeout_ms)
    return context
