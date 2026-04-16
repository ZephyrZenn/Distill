import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.backend.router.brief import router


class OptionalExpansionRouterTest(unittest.TestCase):
    def test_expand_optional_topic_endpoint_returns_content(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch(
            "apps.backend.router.brief.brief_service.expand_optional_topic",
            AsyncMock(
                return_value={
                    "brief_id": 12,
                    "topic_id": "1-ai-pricing",
                    "topic": "AI Pricing",
                    "content": "## AI Pricing\nDeep analysis.",
                    "ext_info": [],
                }
            ),
        ):
            response = client.post("/briefs/12/expand/1-ai-pricing")

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(body["topicId"], "1-ai-pricing")
        self.assertIn("Deep analysis.", body["content"])

    def test_expand_optional_topic_endpoint_returns_404_for_missing_topic(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch(
            "apps.backend.router.brief.brief_service.expand_optional_topic",
            AsyncMock(side_effect=LookupError("Expandable topic not found")),
        ):
            response = client.post("/briefs/12/expand/missing")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
