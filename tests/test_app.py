import unittest

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_public_line_is_documented(self) -> None:
        self.assertIn("/line", app.openapi()["paths"])

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

    def test_hosted_database_url_is_async(self) -> None:
        settings = Settings(DATABASE_URL="postgresql://user:pass@db:5432/betvalue")
        self.assertTrue(settings.DATABASE_URL.startswith("postgresql+asyncpg://"))


if __name__ == "__main__":
    unittest.main()
