import tempfile

from playwright.sync_api import sync_playwright

from gvc_bot.browser import launch
from gvc_bot.runner import Runner
from .fixture import config_for, fixture


def main():
    with tempfile.TemporaryDirectory() as directory, fixture() as (server, url), sync_playwright() as p:
        config = config_for(url, directory)
        context = launch(p, config)
        try:
            page = context.pages[0]
            result = Runner(page, config).run()
            assert result['status'] == 'preview'
            assert result['slot']['id'] == 'earlier'
            assert page.evaluate('window.selections') == 0
            assert server.bookings == 0
            print('PASS: local browser selected the earliest matching slot; zero selection clicks and zero bookings.')
            print('This is a local fixture demo, not a live GVC/Imperva demo.')
        finally:
            context.close()


if __name__ == '__main__':
    main()
