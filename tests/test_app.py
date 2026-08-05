import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.api.routes.line import _quote_analytics


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_public_line_is_documented(self) -> None:
        self.assertIn("/line", app.openapi()["paths"])

    def test_quote_analytics_marks_only_reliable_positive_signal(self) -> None:
        positive = SimpleNamespace(model_probability=0.6, uncertainty=0.2)
        uncertain = SimpleNamespace(model_probability=0.9, uncertainty=0.7)

        self.assertEqual(_quote_analytics(2.0, positive)["signal"], "attention")
        self.assertEqual(_quote_analytics(1.5, positive)["signal"], "neutral")
        self.assertEqual(_quote_analytics(2.0, uncertain)["signal"], "insufficient_data")
        self.assertIsNone(_quote_analytics(2.0, None)["value_edge"])

    def test_local_frontend_cors(self) -> None:
        response = self.client.options(
            "/sources/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")

    def test_sourcecraft_frontend_cors(self) -> None:
        response = self.client.options(
            "/sources/health",
            headers={
                "Origin": "https://bvai.sourcecraft.site",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "https://bvai.sourcecraft.site")

    def test_hosted_database_url_is_async(self) -> None:
        settings = Settings(DATABASE_URL="postgresql://user:pass@db:5432/betvalue")
        self.assertTrue(settings.DATABASE_URL.startswith("postgresql+asyncpg://"))


if __name__ == "__main__":
    unittest.main()
