import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from playwright.sync_api import TimeoutError as BrowserTimeout, sync_playwright

from demo.fixture import config_for, fixture
from gvc_bot.browser import launch
from gvc_bot.runner import PortalBlocked, PortalChanged, Runner, Slot, matches
from gvc_bot.state import StateStore


class BrowserFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        cls.fixture = fixture()
        cls.server, cls.url = cls.fixture.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.__exit__(None, None, None)
        cls.p.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = config_for(self.url, self.temp.name)
        self.context = launch(self.p, self.config)
        self.page = self.context.pages[0]
        self.server.bookings = 0
        self.waits = []

    def tearDown(self):
        self.context.close()
        self.temp.cleanup()

    def runner(self, mode=''):
        self.config.portal_url = self.url + ('?mode=' + mode if mode else '')
        return Runner(self.page, self.config, sleep=self.waits.append, log=lambda *a, **kw: None)

    def test_preview_filters_and_does_not_click(self):
        result = self.runner().run()
        self.assertEqual(result['slot']['id'], 'earlier')
        self.assertEqual(result['status'], 'preview')
        self.assertEqual(self.page.evaluate('window.selections'), 0)
        self.assertEqual(self.server.bookings, 0)
        self.assertFalse(Path(self.config.state_file).exists())

    def test_submit_records_receipt_and_prevents_repeat(self):
        runner = self.runner()
        self.assertEqual(runner.run(submit=True)['status'], 'confirmed')
        self.assertEqual(self.server.bookings, 1)
        self.assertEqual(runner.store.read()['reference'], 'LOCAL-DEMO-001')
        with self.assertRaises(RuntimeError):
            runner.run(submit=True)
        self.assertEqual(self.server.bookings, 1)

    def test_lost_confirmation_never_retries_submission(self):
        runner = self.runner('lost-confirmation')
        with self.assertRaises(BrowserTimeout):
            runner.run(submit=True)
        self.assertEqual(self.server.bookings, 1)
        self.assertEqual(runner.store.read()['status'], 'pending')
        with self.assertRaises(RuntimeError):
            runner.run(submit=True)
        self.assertEqual(self.server.bookings, 1)

    def test_mismatched_review_stops_before_final_click(self):
        runner = self.runner('mismatch')
        with self.assertRaises(PortalChanged):
            runner.run(submit=True)
        self.assertEqual(self.server.bookings, 0)
        self.assertEqual(runner.store.read()['status'], 'pending')

    def test_challenge_login_rate_limit_stop(self):
        for mode in ('challenge', 'login', 'rate-limit'):
            with self.subTest(mode=mode), self.assertRaises(PortalBlocked):
                self.runner(mode).run()
        self.assertEqual(self.server.bookings, 0)
        self.assertEqual(self.waits, [])

    def test_changed_markup_and_duplicate_identifiers_stop(self):
        for mode in ('changed', 'invalid-date', 'duplicate'):
            with self.subTest(mode=mode), self.assertRaises(PortalChanged):
                self.runner(mode).run()

    def test_empty_results_use_bounded_backoff(self):
        self.config.max_checks = 3
        self.assertEqual(self.runner('empty').run()['status'], 'exhausted')
        self.assertEqual(len(self.waits), 2)
        self.assertTrue(60 <= self.waits[0] <= 66)
        self.assertTrue(120 <= self.waits[1] <= 132)

    def test_exact_centre_category_date_and_time(self):
        slot = Slot('x', '2030-01-01', '09:00', 'Demo centre', 'Tourism')
        self.assertTrue(matches(slot, self.config))
        for altered in (replace(slot, centre='Other'), replace(slot, category='Work'),
                        replace(slot, date='2029-12-31'), replace(slot, time='08:59')):
            self.assertFalse(matches(altered, self.config))

    def test_exclusive_lock_and_corrupt_journal(self):
        runner = self.runner()
        with runner.store.lock(), self.assertRaises(RuntimeError):
            runner.run()
        Path(self.config.state_file).write_text('invalid JSON')
        with self.assertRaises(json.JSONDecodeError):
            runner.run()


class ConfigurationTests(unittest.TestCase):
    def test_reject_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            for change in ({'portal_url': 'http://example.com'}, {'poll_seconds': 0},
                           {'date_from': '2031-01-01'}, {'time_from': '20:00'},
                           {'max_checks': 0}, {'selectors': {}}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    config = config_for('http://127.0.0.1/', directory)
                    replace(config, **change).validate()


if __name__ == '__main__':
    unittest.main()
