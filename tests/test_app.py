from pathlib import Path
import tempfile
import unittest

import httpx

from ai_financial_intelligence.main import create_app
from ai_financial_intelligence.settings import AppSettings, ProxyConfig


def build_settings(temp_dir: tempfile.TemporaryDirectory[str]) -> AppSettings:
    return AppSettings(
        mock_mode=True,
        proxy=ProxyConfig(enabled=True, url="http://127.0.0.1:4780"),
        database_path=Path(temp_dir.name) / "analysis.db",
        default_asset="BTCUSDT",
        default_timeframe="4h",
        fred_api_key=None,
        event_feed_url=None,
    )


class AppRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(build_settings(self.temp_dir))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_home_page_renders_form_and_empty_state(self) -> None:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertIn("开始分析", response.text)
        self.assertIn("尚无分析记录", response.text)
        self.assertIn("BTCUSDT", response.text)
        self.assertIn("DOGEUSDT", response.text)

    async def test_post_analyze_returns_structured_report_page(self) -> None:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/analyze",
                data={"asset": "BTCUSDT", "timeframe": "4h"},
            )
            follow_up = await client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertIn("分析已完成", response.text)
        self.assertIn("Peter", response.text)
        self.assertIn("Venturus", response.text)
        self.assertIn("Pivot", response.text)
        self.assertIn("Reality Check", response.text)
        self.assertIn("多头逻辑", response.text)
        self.assertIn("空头逻辑", response.text)
        self.assertIn("情景概率分布", response.text)
        self.assertIn("失效条件", response.text)
        self.assertIn("仅供研究参考，不构成投资建议", response.text)
        self.assertIn("Recent Analysis", follow_up.text)
        self.assertIn("BTCUSDT / 4h", follow_up.text)


if __name__ == "__main__":
    unittest.main()
