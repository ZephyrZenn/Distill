
import sys
import logging
from unittest.mock import MagicMock

# Mock DB dependencies before importing agent
sys.modules["psycopg"] = MagicMock()
sys.modules["psycopg_pool"] = MagicMock()
sys.modules["core.db.pool"] = MagicMock()

from agent.ps_agent import PlanSolveAgent

logging.basicConfig(level=logging.INFO)

try:
    print("Initializing Agent...")
    agent = PlanSolveAgent(lazy_init=True)
    print("Compiling Graph...")
    graph = agent.graph
    print("Graph Compiled Successfully!")
    print("Nodes:", graph.nodes.keys())
except Exception as e:
    print(f"Graph Construction Failed: {e}")
    sys.exit(1)
