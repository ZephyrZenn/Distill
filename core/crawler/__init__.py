"""Compatibility shim for crawler package exports.

Canonical implementation lives in distill_lib.core.crawler.
"""

from distill_lib.core.crawler import fetch_all_contents

__all__ = ["fetch_all_contents"]
