import ast
from pathlib import Path
import unittest


class WorkflowForbiddenImportsTest(unittest.TestCase):
    def _is_forbidden_module(self, module_name: str, forbidden_roots: set[str], allowed_from: set[str]) -> bool:
        if module_name in allowed_from:
            return False
        return any(module_name == root or module_name.startswith(f"{root}.") for root in forbidden_roots)

    def _assert_no_forbidden_imports(
        self,
        py_file: Path,
        forbidden_roots: set[str],
        allowed_from: set[str] | None = None,
    ):
        allowed_from = allowed_from or set()
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if self._is_forbidden_module(node.module, forbidden_roots, allowed_from):
                    self.fail(f"Forbidden import {node.module} in {py_file}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if self._is_forbidden_module(alias.name, forbidden_roots, allowed_from):
                        self.fail(f"Forbidden import {alias.name} in {py_file}")

    def test_ps_agent_and_backend_use_distill_lib_for_migrated_surfaces(self):
        root = Path(__file__).resolve().parent.parent
        targets = [
            root / "agent" / "ps_agent" / "__init__.py",
            root / "agent" / "ps_agent" / "tools" / "__init__.py",
            root / "agent" / "ps_agent" / "nodes" / "planner" / "bootstrap.py",
            root / "agent" / "ps_agent" / "nodes" / "planner" / "structure.py",
            root / "agent" / "ps_agent" / "nodes" / "evaluator" / "audit_analyzer.py",
            root / "agent" / "ps_agent" / "nodes" / "evaluator" / "batch_audit.py",
            root / "agent" / "ps_agent" / "nodes" / "evaluator" / "plan_reviewer.py",
            root / "agent" / "ps_agent" / "nodes" / "evaluator" / "summary_reviewer.py",
            root / "apps" / "backend" / "services" / "setting_service.py",
            root / "apps" / "backend" / "services" / "task_service.py",
            root / "apps" / "backend" / "services" / "feed_service.py",
            root / "apps" / "backend" / "router" / "setting.py",
            root / "apps" / "backend" / "models" / "converters.py",
            root / "apps" / "backend" / "main.py",
            root / "agent" / "tools" / "__init__.py",
        ]

        forbidden_roots = {
            "agent.utils",
            "agent.tools",
            "agent.tools.search_tool",
            "agent.tools.filter_tool",
            "agent.tools.writing_tool",
            "core.llm_client",
            "core.crawler",
            "core.config",
            "core.models.config",
        }
        allowed_from = {
            "core.db.pool",
            "core.constants",
            "core.embedding",
            "core.prompt.context_manager",
            "agent.tools.db_tool",
            "agent.tools.memory_tool",
        }
        for py_file in targets:
            self._assert_no_forbidden_imports(py_file, forbidden_roots, allowed_from)


if __name__ == "__main__":
    unittest.main()
