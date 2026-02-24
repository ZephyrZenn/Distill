import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

_thread_pool: Optional[ThreadPoolExecutor] = None


def get_thread_pool_config() -> dict:
    """Get thread pool configuration from environment or defaults"""
    return {
        "max_workers": int(os.getenv("THREAD_POOL_MAX_WORKERS", "4")),
        "thread_name_prefix": os.getenv("THREAD_POOL_NAME_PREFIX", "Distill"),
    }


def init_thread_pool(
    max_workers: Optional[int] = None, thread_name_prefix: Optional[str] = None
):
    """Initialize the thread pool with configurable parameters"""
    global _thread_pool

    if _thread_pool is not None:
        logger.warning("Thread pool already initialized")
        return

    config = get_thread_pool_config()

    # Override with parameters if provided
    if max_workers is not None:
        config["max_workers"] = max_workers
    if thread_name_prefix is not None:
        config["thread_name_prefix"] = thread_name_prefix

    try:
        _thread_pool = ThreadPoolExecutor(
            max_workers=config["max_workers"],
            thread_name_prefix=config["thread_name_prefix"],
        )
        logger.info(f"Thread pool initialized with {config['max_workers']} workers")
    except Exception:
        logger.exception("Failed to initialize thread pool")
        raise


def get_thread_pool() -> ThreadPoolExecutor:
    """Get the thread pool, initializing it if necessary"""
    global _thread_pool

    if _thread_pool is None:
        init_thread_pool()

    return _thread_pool


def shutdown_thread_pool(wait: bool = True):
    """Shutdown the thread pool gracefully"""
    global _thread_pool

    if _thread_pool is not None:
        logger.info("Shutting down thread pool")
        _thread_pool.shutdown(wait=wait)
        _thread_pool = None
        logger.info("Thread pool shutdown complete")


def is_thread_pool_initialized() -> bool:
    """Check if the thread pool is initialized"""
    return _thread_pool is not None


def get_thread_pool_stats() -> dict:
    """Get thread pool statistics"""
    if _thread_pool is None:
        return {"initialized": False}

    return {
        "initialized": True,
        "max_workers": _thread_pool._max_workers,
        "thread_name_prefix": _thread_pool._thread_name_prefix,
    }
