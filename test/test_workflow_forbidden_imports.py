import ast
from pathlib import Path
import unittest


class WorkflowForbiddenImportsTest(unittest.TestCase):
    def _assert_no_forbidden_imports(self, py_file: Path, forbidden: set[str]):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in forbidden:
                self.fail(f"Forbidden import {node.module} in {py_file}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden:
                        self.fail(f"Forbidden import {alias.name} in {py_file}")

    def test_workflow_path_has_no_direct_db_tool_imports(self):
        workflow_dir = Path(__file__).resolve().parent.parent / "agent" / "workflow"
        forbidden = {"agent.tools.db_tool", "agent.tools.memory_tool"}
        for py_file in workflow_dir.glob("*.py"):
            self._assert_no_forbidden_imports(py_file, forbidden)

    def test_workflow_lib_path_has_no_db_coupling_imports(self):
        lib_dir = Path(__file__).resolve().parent.parent / "distill_workflow_lib"
        forbidden = {
            "agent.tools.db_tool",
            "agent.tools.memory_tool",
            "core.db",
            "core.db.pool",
            "psycopg",
            "pgvector",
        }
        for py_file in lib_dir.glob("*.py"):
            self._assert_no_forbidden_imports(py_file, forbidden)


if __name__ == "__main__":
    unittest.main()
