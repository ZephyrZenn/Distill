from __future__ import annotations

import importlib
import sys
from pathlib import Path
import unittest


class WorkflowLibSubpackageImportTest(unittest.TestCase):
    def test_subpackage_source_importable_via_local_path(self):
        repo_root = Path(__file__).resolve().parent.parent
        package_src = repo_root / "packages" / "distill_workflow_lib" / "src"

        # Simulate skill-side local/path install resolution by importing from package src path.
        sys.path.insert(0, str(package_src))
        try:
            for mod_name in [
                "distill_workflow_lib",
                "distill_workflow_lib.api",
                "distill_workflow_lib.providers",
            ]:
                sys.modules.pop(mod_name, None)

            package = importlib.import_module("distill_workflow_lib")
            api = importlib.import_module("distill_workflow_lib.api")

            self.assertIn("packages/distill_workflow_lib/src", package.__file__)
            self.assertIn("packages/distill_workflow_lib/src", api.__file__)
            self.assertTrue(hasattr(api, "run_workflow_from_articles"))
        finally:
            if str(package_src) in sys.path:
                sys.path.remove(str(package_src))


if __name__ == "__main__":
    unittest.main()
