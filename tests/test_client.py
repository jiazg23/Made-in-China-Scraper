import logging
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main as scraper
from test_parsing import SUPPLIER_PROFILE_HTML, TEXT_RESULTS_HTML


# The input from the reported Apify run.
REPORTED_INPUT = {
    "failOnNoResults": False, "includeSupplierDetails": True,
    "saveCsvFile": True, "searchMode": "keyword", "searchTerms": ["monitors"],
    "skipFailedImages": True, "useApifyProxy": True,
    "maxUniqueSuppliersPerKeyword": 10, "maxPagesText": 1,
    "maxUniqueSuppliersPerImage": 10, "maxPagesImage": 1,
    "csvOutputMode": "combined", "csvFilename": "made_in_china_results.csv",
}


def response(status=200, body=TEXT_RESULTS_HTML, url=scraper.TEXT_SEARCH_URL):
    return SimpleNamespace(status_code=status, text=body, url=url)


class FakeActor:
    def __init__(self, actor_input):
        self.get_input = AsyncMock(return_value=actor_input)
        self.push_data = AsyncMock()
        self.set_value = AsyncMock()
        self.log = logging.getLogger("test_actor")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def saved_values(self):
        return {call.args[0]: call.args[1] for call in self.set_value.await_args_list}


class StartupRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def run_actor(self, actor_input, session, actor):
        with patch.object(scraper, "Actor", actor), \
             patch.object(scraper, "get_proxy_url", AsyncMock(return_value="http://proxy.example:8000")), \
             patch.object(scraper, "build_mic_session", return_value=session):
            await scraper.main()

    async def test_reported_input_searches_and_exports_after_homepage_403(self):
        actor = FakeActor(dict(REPORTED_INPUT))
        session = Mock()
        session.get.side_effect = [
            response(403, "Access denied", scraper.BASE_URL + "/"),
            response(), response(body=SUPPLIER_PROFILE_HTML),
        ]
        await self.run_actor(REPORTED_INPUT, session, actor)
        saved = actor.saved_values()
        summary = saved["RUN_SUMMARY.json"]
        self.assertEqual(summary["warm_up"]["http_status"], 403)
        self.assertEqual(summary["inputs"]["monitors"]["status"], "completed")
        self.assertEqual(summary["unique_suppliers"], 1)
        self.assertEqual(summary["supplier_details"]["enriched"], 1)
        self.assertIn("warm_up_debug.html", saved)
        self.assertIn("Image Supplier Co.", saved["made_in_china_results.csv"])
        self.assertEqual(actor.push_data.await_count, 1)
        session.close.assert_called_once()

    async def test_blocked_search_saves_summary_and_obeys_strict_flag(self):
        for strict in (False, True):
            with self.subTest(strict=strict):
                actor_input = {**REPORTED_INPUT, "failOnNoResults": strict}
                actor = FakeActor(actor_input)
                session = Mock()
                session.get.return_value = response(403, "Access denied")
                if strict:
                    with self.assertRaisesRegex(RuntimeError, "No Made-in-China supplier results"):
                        await self.run_actor(actor_input, session, actor)
                else:
                    await self.run_actor(actor_input, session, actor)
                saved = actor.saved_values()
                summary = saved["RUN_SUMMARY.json"]
                self.assertEqual(summary["unique_suppliers"], 0)
                self.assertEqual(summary["inputs"]["monitors"]["status"], "failed")
                self.assertEqual(summary["inputs"]["monitors"]["http_status"], 403)
                self.assertIn("keyword_monitors_page_1_debug.html", saved)
                actor.push_data.assert_not_awaited()
                session.close.assert_called_once()

    async def test_strict_mode_keeps_successful_keywords_when_another_is_blocked(self):
        actor_input = {**REPORTED_INPUT, "searchTerms": ["blocked", "monitors"], "failOnNoResults": True}
        actor = FakeActor(actor_input)
        session = Mock()
        session.get.side_effect = [
            response(body="<html>Home</html>"), response(403, "Access denied"),
            response(), response(body=SUPPLIER_PROFILE_HTML),
        ]
        await self.run_actor(actor_input, session, actor)
        self.assertEqual(actor.saved_values()["RUN_SUMMARY.json"]["unique_suppliers"], 1)


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_proxy_group_overrides_legacy_switch_and_uses_session(self):
        config = {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]}
        proxy = SimpleNamespace(new_url=AsyncMock(return_value="http://proxy.example:8000"))
        create = AsyncMock(return_value=proxy)
        with patch.object(scraper.Actor, "create_proxy_configuration", create):
            url = await scraper.get_proxy_url(False, config)
        self.assertEqual(url, "http://proxy.example:8000")
        create.assert_awaited_once_with(actor_proxy_input=config)
        self.assertRegex(proxy.new_url.await_args.kwargs["session_id"], r"^[a-f0-9]{32}$")

    async def test_proxy_off_does_not_initialize_proxy(self):
        with patch.object(scraper.Actor, "create_proxy_configuration", AsyncMock()) as create:
            self.assertIsNone(await scraper.get_proxy_url(False))
            create.assert_not_awaited()

    async def test_proxy_failure_does_not_leak_credentials_or_fall_back_to_direct(self):
        create = AsyncMock(side_effect=RuntimeError("http://user:secret@proxy.example:8000"))
        with patch.object(scraper.Actor, "create_proxy_configuration", create):
            with self.assertRaisesRegex(RuntimeError, "Proxy initialization failed") as caught:
                await scraper.get_proxy_url(True)
        self.assertNotIn("secret", str(caught.exception))


class ClientTests(unittest.TestCase):
    def test_transient_get_retry_succeeds(self):
        session = Mock()
        session.get.side_effect = [response(503, "Temporarily unavailable"), response()]
        with patch.object(scraper.time, "sleep"):
            html, url = scraper.MadeInChinaClient(session).text_search("monitors", 1)
        self.assertEqual(html, TEXT_RESULTS_HTML)
        self.assertIn("word=monitors", url)
        self.assertEqual(session.get.call_count, 2)

    def test_403_is_not_retried_and_retains_diagnostics(self):
        session = Mock()
        session.get.return_value = response(403, "Access denied")
        with self.assertRaises(scraper.FetchError) as caught:
            scraper.MadeInChinaClient(session).text_search("monitors", 1)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.body, "Access denied")
        session.get.assert_called_once()

    def test_network_failures_are_bounded_and_wrapped(self):
        session = Mock()
        session.get.side_effect = scraper.BrowserRequestException("network error")
        with patch.object(scraper.time, "sleep"):
            with self.assertRaises(scraper.FetchError):
                scraper.MadeInChinaClient(session).warm_up()
        self.assertEqual(session.get.call_count, 4)

    def test_upload_uses_supported_multipart_api(self):
        session = Mock()
        session.post.return_value = response(body="{}", url=scraper.IMAGE_UPLOAD_URL)
        session.post.return_value.json = lambda: {
            "code": 200, "data": {"id": "abc123", "url": scraper.BASE_URL + "/img-search/abc123.html"},
        }
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "product.png"
            Image.new("RGB", (5, 7), "red").save(image)
            result = scraper.MadeInChinaClient(session).upload_image(str(image))
        self.assertEqual(result["id"], "abc123")
        self.assertIn("multipart", session.post.call_args.kwargs)
        self.assertNotIn("files", session.post.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
