import os
import unittest

from dotenv import load_dotenv

from agent import init_agent
from core.config.loader import load_config
from apps.backend.services.feed_service import (
    import_opml_config,
    retrieve_new_feeds_sync,
)
from apps.backend.services.group_service import create_group

# Load environment variables before importing any modules that might use them
load_dotenv()

cfg = None

class FeedServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global cfg
        # Ensure environment variables are loaded
        load_dotenv()
        # Verify required environment variables
        required_vars = [
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "POSTGRES_DB",
            "TAVILY_API_KEY",
        ]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )
        cfg = load_config()
        init_agent()

    def test_import_opml_config(self):
        import_opml_config("feed.opml")

    def test_create_group(self):
        create_group("Test", "Test Group", [1, 2])
        
    def test_retrieve_new_feeds(self):
        retrieve_new_feeds_sync()
