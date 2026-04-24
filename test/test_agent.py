import asyncio
import os
import unittest
from dotenv import load_dotenv

from agent import SummarizeAgenticWorkflow
from core.config.loader import load_config


class AgentTest(unittest.TestCase):
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

    def test_agent(self):
        agent = SummarizeAgenticWorkflow()

        # 边执行边输出的回调函数
        def on_step(message: str):
            print(f"[STEP] {message}")

        result, _, _, _, _ = asyncio.run(
            agent.summarize(
                task_id="test",
                hour_gap=24,
                group_ids=[5],
                focus="AI Competition Analysis",
                on_step=on_step,
                ui_language="en",
            )
        )
        print("\n=== 最终结果 ===")
        print(result)
        with open("result4.md", "w") as f:
            f.write(result)

    def test_embedding(self):
        from agent.tools.memory_tool import backfill_embeddings

        result = asyncio.run(backfill_embeddings())
        print(result)
