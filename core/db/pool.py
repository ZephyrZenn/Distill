import asyncio
import logging
import os
from contextlib import asynccontextmanager, contextmanager
from typing import Callable
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, AsyncConnectionPool, PoolTimeout

logger = logging.getLogger(__name__)

# 配置 psycopg_pool 的日志，确保能看到详细的连接错误信息
_pool_logger = logging.getLogger("psycopg.pool")
_pool_logger.setLevel(logging.DEBUG)

_sync_pool: ConnectionPool | None = None
_async_pool: AsyncConnectionPool | None = None

_pool_monitor_task: asyncio.Task | None = None


def _get_conninfo() -> str:
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = int(os.getenv("POSTGRES_PORT", 5432))
    database = os.getenv("POSTGRES_DB")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def _get_conninfo_masked() -> str:
    """返回脱敏的连接字符串，用于日志输出"""
    user = os.getenv("POSTGRES_USER")
    host = os.getenv("POSTGRES_HOST")
    port = int(os.getenv("POSTGRES_PORT", 5432))
    database = os.getenv("POSTGRES_DB")
    return f"postgresql://{user}:***@{host}:{port}/{database}"


def get_pool() -> ConnectionPool | None:
    global _sync_pool
    def check_connection(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    if _sync_pool is None:
        try:
            logger.debug(f"Creating sync connection pool: {_get_conninfo_masked()}")
            _sync_pool = ConnectionPool(
                conninfo=_get_conninfo(),
                min_size=1,
                max_size=10,
                # 1) 借出前健康检查，避免拿到 BAD/closed
                check=check_connection,
                # 2) 空闲回收：避免 idle 被 LB/防火墙断开后留在池里
                max_idle=300,  # 5min，可按环境调 60~900
                # 3) 生命周期轮换：避免长连接偶发失效
                max_lifetime=1800,  # 30min，可按环境调 900~3600
                # 4) 从池里获取连接的等待时间
                timeout=10,  # 秒
                open=True,
            )
        except Exception as e:
            logger.error(f"Error creating connection pool: {e}", exc_info=True)
            return None
    return _sync_pool


@contextmanager
def get_connection(*, autocommit: bool = False):
    """
    autocommit=False：默认事务；正常提交，异常回滚
    autocommit=True ：只读/不需要事务时可用
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("Failed to create connection pool")

    try:
        with pool.connection() as conn:
            if autocommit:
                conn.autocommit = True
                yield conn
                return

            try:
                yield conn
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            else:
                conn.commit()

    except (OperationalError, PoolTimeout):
        # 保留原始异常信息，便于定位
        raise


def execute_transaction(call: Callable, *args, **kwargs):
    """Executes a callable with a connection from the pool."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            return call(cur, *args, **kwargs)

# ============ 异步 API ============


async def get_async_pool() -> AsyncConnectionPool | None:
    async def _async_check_connection(conn):
        """连接健康检查：验证连接是否可用
        
        添加超时保护，避免健康检查本身卡住导致连接泄漏
        """
        try:
            # 设置健康检查超时（5秒）
            async with asyncio.timeout(5.0):
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
        except (asyncio.TimeoutError, OperationalError) as e:
            # 健康检查失败，记录日志但不抛出异常（让 pool 丢弃连接）
            logger.warning(f"Connection health check failed: {e}")
            raise  # 重新抛出，让 pool 知道连接不可用
        except Exception as e:
            # 其他异常也记录并重新抛出
            logger.warning(f"Unexpected error in connection health check: {e}")
            raise
    
    global _async_pool
    if _async_pool is None:
        try:
            logger.debug(f"Creating async connection pool: {_get_conninfo_masked()}")
            _async_pool = AsyncConnectionPool(
                conninfo=_get_conninfo(),
                min_size=1,  # 预热1个连接，避免冷启动延迟
                max_size=15,  # 增加到15，应对并发需求
                timeout=30,
                check=_async_check_connection,
                max_idle=120,
                max_lifetime=900,
                open=False,
            )
            await _async_pool.open()
            logger.info("Async connection pool created successfully")
        except Exception as e:
            logger.error(f"Error creating async connection pool: {e}", exc_info=True)
            return None
    return _async_pool


def _log_pool_stats(pool: AsyncConnectionPool, context: str = ""):
    """记录连接池状态信息（用于诊断）"""
    try:
        stats = pool.get_stats()
        logger.debug(
            f"Pool stats {context}: size={stats.get('pool_size', 'N/A')}, "
            f"available={stats.get('available', 'N/A')}, "
            f"waiting={stats.get('waiting', 'N/A')}"
        )
    except Exception:
        # 如果获取统计信息失败，忽略（避免影响主流程）
        pass


def _log_sync_pool_stats(pool: ConnectionPool, context: str = ""):
    """记录同步连接池状态信息（用于诊断）"""
    try:
        stats = pool.get_stats()
        logger.debug(
            f"Sync pool stats {context}: size={stats.get('pool_size', 'N/A')}, "
            f"available={stats.get('available', 'N/A')}, "
            f"waiting={stats.get('waiting', 'N/A')}"
        )
    except Exception:
        pass


@asynccontextmanager
async def get_async_connection(*, autocommit: bool = False):
    """
    autocommit=False：默认事务模式；业务正常则提交，异常回滚
    autocommit=True ：只读/不需要事务时可用，避免无意义 commit
    """
    pool = await get_async_pool()
    if pool is None:
        raise RuntimeError("Failed to create async connection pool")

    # 记录获取连接前的池状态
    _log_pool_stats(pool, "before get_connection")

    try:
        async with pool.connection() as conn:
            # 记录获取连接后的池状态
            _log_pool_stats(pool, "after get_connection")

            if autocommit:
                conn.autocommit = True
                yield conn
                return

            try:
                yield conn
            except Exception:
                # 确保异常时回滚
                try:
                    await conn.rollback()
                except Exception as rollback_error:
                    logger.warning(f"Failed to rollback transaction: {rollback_error}")
                    pass
                raise
            else:
                # 正常时提交
                try:
                    await conn.commit()
                except Exception as commit_error:
                    logger.warning(f"Failed to commit transaction: {commit_error}")
                    # 提交失败时尝试回滚
                    try:
                        await conn.rollback()
                    except Exception:
                        pass
                    raise

    except PoolTimeout as e:
        # 连接池超时：记录详细的池状态信息
        _log_pool_stats(pool, "on PoolTimeout")
        logger.error(
            f"PoolTimeout: Could not get connection after 30s. "
            f"This usually indicates connection pool exhaustion or connection leaks. "
            f"Check pool stats above for details."
        )
        raise
    except OperationalError as e:
        # 数据库操作错误：记录但不改变行为
        logger.warning(f"OperationalError in get_async_connection: {e}")
        raise
    except Exception as e:
        # 其他异常：记录详细信息
        logger.error(f"Unexpected error in get_async_connection: {e}", exc_info=True)
        raise


async def execute_async_transaction(call: Callable, *args, **kwargs):
    """Executes an async callable with a connection from the pool."""
    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            return await call(cur, *args, **kwargs)


# ============ 清理 ============


def close_pool():
    global _sync_pool
    if _sync_pool:
        _sync_pool.close()
        _sync_pool = None


async def close_async_pool():
    global _async_pool
    if _async_pool:
        try:
            # 记录关闭前的池状态
            _log_pool_stats(_async_pool, "before close")
            await _async_pool.close()
            logger.info("Async connection pool closed successfully")
        except Exception as e:
            logger.error(f"Error closing async connection pool: {e}", exc_info=True)
        finally:
            _async_pool = None


async def get_async_pool_stats() -> dict | None:
    """获取异步连接池的统计信息（用于监控和诊断）
    
    Returns:
        包含池统计信息的字典，如果池不存在则返回 None
    """
    pool = await get_async_pool()
    if pool is None:
        return None
    try:
        return pool.get_stats()
    except Exception as e:
        logger.warning(f"Failed to get pool stats: {e}")
        return None


def log_pool_stats(context: str = "") -> None:
    """记录当前连接池统计信息（sync + async）"""
    if _sync_pool:
        _log_sync_pool_stats(_sync_pool, context)
    if _async_pool:
        _log_pool_stats(_async_pool, context)


def start_pool_monitoring(interval_seconds: int = 60) -> None:
    """启动连接池监控任务，定期输出连接池统计信息"""
    global _pool_monitor_task
    if _pool_monitor_task is not None and not _pool_monitor_task.done():
        return

    async def _monitor():
        while True:
            log_pool_stats("periodic")
            await asyncio.sleep(interval_seconds)

    _pool_monitor_task = asyncio.create_task(_monitor())


async def stop_pool_monitoring() -> None:
    """停止连接池监控任务"""
    global _pool_monitor_task
    if _pool_monitor_task is None:
        return
    _pool_monitor_task.cancel()
    try:
        await _pool_monitor_task
    except asyncio.CancelledError:
        pass
    _pool_monitor_task = None
