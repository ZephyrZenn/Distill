
import asyncio
import unittest

from agent.ps_agent import PlanSolveAgent


class PsAgentTest(unittest.TestCase):
    
    def test_ps_agent(self):
        agent = PlanSolveAgent(
            max_context_items=15,
            debug=True,
        )
        def on_step(message: str):
            print(message)
        report = asyncio.run(agent.run("当前AI行业动态", on_step=on_step))
        print(report)