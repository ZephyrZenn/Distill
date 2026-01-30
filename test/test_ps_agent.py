
import asyncio
import unittest

from agent.ps_agent import PlanSolveAgent


class PsAgentTest(unittest.TestCase):
    
    def test_ps_agent(self):
        agent = PlanSolveAgent(
            max_iterations=12,
            max_tool_calls=24,
            max_refine=2,
            max_context_items=40,
        )
        def on_step(message: str):
            print(message)
        report = asyncio.run(agent.run("美股市场信息", on_step=on_step))
        print(report)