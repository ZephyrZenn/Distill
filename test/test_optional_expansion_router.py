import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.backend.router.brief import router


class OptionalExpansionRouterTest(unittest.TestCase):
    def test_expand_returns_202_and_fires_background_task(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        brief = MagicMock()
        brief.expandable_topics = [{"topic_id": "1-ai-pricing", "focal_point": {"topic": "AI Pricing"}}]

        with patch("apps.backend.router.brief.brief_service.get_brief_by_id", return_value=brief), \
             patch("apps.backend.router.brief.brief_service.expand_optional_topic", AsyncMock(return_value=None)):
            response = client.post("/briefs/12/expand/1-ai-pricing")

        self.assertEqual(response.status_code, 202)

    def test_expand_returns_404_when_topic_missing(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch("apps.backend.router.brief.brief_service.get_brief_by_id", return_value=None):
            response = client.post("/briefs/12/expand/missing")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
