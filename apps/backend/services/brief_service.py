import asyncio
import datetime
import json
import logging
import re

from core.db.pool import get_connection
from core.models.feed import FeedBrief

logger = logging.getLogger(__name__)


def _extract_h2_headings(content: str) -> str:
    """从内容中提取所有二级标题（## 开头的行）作为概要"""
    headings = []
    lines = content.split("\n")
    for line in lines:
        trimmed = line.strip()
        # 匹配二级标题：## 标题
        match = re.match(r"^##\s+(.+)$", trimmed)
        if match:
            headings.append(match.group(1).strip())
    return "\n".join(headings) if headings else ""


def _extract_base_url(url: str) -> str:
    """提取URL的基础部分（去掉查询参数和fragment）

    例如：
    'https://api3.cls.cn/share/article/2268497?os=web&sv=8.4.6'
    -> 'https://api3.cls.cn/share/article/2268497'
    """
    # 去掉查询参数（?之后）和fragment（#之后）
    base = url.split("?")[0].split("#")[0]
    return base.rstrip("/")


def _is_url_like(text: str) -> bool:
    """判断文本是否看起来像URL"""
    return text.startswith(("http://", "https://"))


def _replace_reference(brief_id: int, content: str) -> str:
    """
    将内容中的引用标记替换为 HTML 角标 <sup>[n]</sup>，并在文末生成参考资料列表。
    支持：rss, ext, memory 三种类型。
    """

    # --- 1. 提取所有引用并分类 ---
    # 匹配格式: [type:id]
    ref_pattern = r"\[(rss|ext|memory):([^\]]+)\]"
    found_refs = re.findall(ref_pattern, content)
    if not found_refs:
        return content

    # 按类型分组以便批量查询数据库
    rss_ids = {id.strip() for type, id in found_refs if type == "rss" and id.strip()}
    ext_keys = {id.strip() for type, id in found_refs if type == "ext" and id.strip()}
    # memory 通常是 ID 直接映射，不需要复杂查询，但为了统一逻辑也放入 map

    # 存储元数据: (type, original_id) -> (title, url)
    metadata_map: dict[tuple[str, str], tuple[str, str]] = {}

    # --- 2. 数据库批量查询 ---
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # A. 处理 RSS 引用
                if rss_ids:
                    # 正常匹配
                    cur.execute(
                        "SELECT id, title, link FROM feed_items WHERE id = ANY(%s)",
                        (list(rss_ids),),
                    )
                    for row in cur.fetchall():
                        metadata_map[("rss", str(row[0]))] = (row[1], row[2])

                    # 兜底：处理模糊 URL 匹配
                    missing_rss = rss_ids - {
                        id for type, id in metadata_map.keys() if type == "rss"
                    }
                    for m_id in missing_rss:
                        if _is_url_like(m_id):
                            base_url = _extract_base_url(m_id)
                            cur.execute(
                                "SELECT title, link FROM feed_items WHERE id LIKE %s || '%%' LIMIT 1",
                                (base_url,),
                            )
                            row = cur.fetchone()
                            if row:
                                metadata_map[("rss", m_id)] = (row[0], row[1])

                # B. 处理外部搜索结果 (Ext Info)
                # 使用你原本的 JSONB 解析逻辑
                SQL_EXT_INFO = """
                    SELECT elem->>'title', elem->>'url'
                    FROM feed_brief fb
                    CROSS JOIN LATERAL jsonb_array_elements(
                        CASE 
                            WHEN jsonb_typeof(fb.ext_info) = 'array' THEN fb.ext_info 
                            ELSE '[]'::jsonb 
                        END
                    ) AS elem
                    WHERE fb.id = %s AND elem ? 'title' AND elem ? 'url'
                """
                cur.execute(SQL_EXT_INFO, (brief_id,))
                for row in cur.fetchall():
                    # 外部信息通常以标题为 Key
                    metadata_map[("ext", row[0])] = (row[0], row[1])

    except Exception as e:
        logger.error(
            f"Error querying metadata for brief {brief_id}: {e}", exc_info=True
        )

    # --- 3. 正文替换与索引分配 ---
    citation_list: list[dict] = []  # 用于存储文末列表的顺序
    ref_to_index: dict[tuple[str, str], int] = {}  # 避免重复分配索引

    def replacer(match: re.Match) -> str:
        ref_type = match.group(1)
        ref_id = match.group(2).strip()
        key = (ref_type, ref_id)

        # 获取或分配索引
        if key not in ref_to_index:
            title, url = (None, None)

            if ref_type == "memory":
                title, url = f"历史记录 {ref_id}", f"/memory/{ref_id}"
            else:
                title, url = metadata_map.get(key, (None, None))

            # 如果没找到元数据，不转化为角标，保持原样（或按需处理）
            if not title:
                return match.group(0)

            new_idx = len(citation_list) + 1
            ref_to_index[key] = new_idx
            citation_list.append({"index": new_idx, "title": title, "url": url})

        idx = ref_to_index[key]
        return f"[^{idx}]"

    # 执行正文替换
    final_content = re.sub(ref_pattern, replacer, content)

    # --- 4. 生成文末参考资料列表和脚注定义 ---
    if citation_list:
        # 生成 markdown 脚注定义（用于前端渲染角标）
        # remark-gfm 会将脚注链接转换为 #user-content-fn-{index} 格式
        footnote_definitions = "\n"
        for item in citation_list:
            # 生成脚注定义：remark-gfm 会自动处理为 #user-content-fn-{index}
            # 我们只需要提供标题，链接会在前端处理
            footnote_definitions += f"[^{item['index']}]: {item['title']}\n"

        # 使用水平分割线区分正文与参考文献
        # 给参考资料列表中的每一项添加锚点 id，使用 user-content-fn-{index} 格式匹配 remark-gfm
        ref_footer = "\n\n---\n\n## 参考资料\n\n"
        for item in citation_list:
            # 使用 HTML 锚点来标记参考资料项，id 格式匹配 remark-gfm 的 user-content-fn-{index}
            # 将 span 和序号链接放在同一行，确保 Markdown 正确解析序号
            ref_footer += f"<span id=\"user-content-fn-{item['index']}\"></span>{item['index']}. [{item['title']}]({item['url']})\n\n"
        final_content += footnote_definitions + ref_footer

    return final_content


def get_briefs(
    start_date: datetime.date, end_date: datetime.date, include_content: bool = False
):
    """获取简报列表

    Args:
        start_date: 开始日期
        end_date: 结束日期
        include_content: 是否包含完整内容（content 和 ext_info），默认 False
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            if include_content:
                # 包含完整内容
                cur.execute(
                    """SELECT id, content, created_at, group_ids, summary, ext_info
                       FROM feed_brief
                       WHERE created_at::date BETWEEN %s AND %s
                       ORDER BY id DESC""",
                    (start_date, end_date),
                )
                return [
                    FeedBrief(
                        id=row[0],
                        content=row[1],
                        pub_date=row[2],
                        group_ids=row[3],
                        summary=row[4] or "",
                        ext_info=row[5] if row[5] else [],
                    )
                    for row in cur.fetchall()
                ]
            else:
                # 不包含完整内容，只返回基本信息
                cur.execute(
                    """SELECT id, created_at, group_ids, summary
                       FROM feed_brief
                       WHERE created_at::date BETWEEN %s AND %s
                       ORDER BY id DESC""",
                    (start_date, end_date),
                )
                return [
                    FeedBrief(
                        id=row[0],
                        content="",  # 列表页不返回内容
                        pub_date=row[1],
                        group_ids=row[2],
                        summary=row[3] or "",
                        ext_info=[],  # 列表页不返回外部信息
                    )
                    for row in cur.fetchall()
                ]


def get_brief_by_id(brief_id: int) -> FeedBrief | None:
    """根据ID获取单个简报的完整信息"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, content, created_at, group_ids, ext_info
                   FROM feed_brief
                   WHERE id = %s""",
                (brief_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return FeedBrief(
                id=row[0],
                content=_replace_reference(brief_id, row[1]),
                pub_date=row[2],
                group_ids=row[3],
                ext_info=row[4] if row[4] else [],
            )


def generate_brief_for_groups(group_ids: list[int], focus: str = ""):
    """
    Generate brief for specific groups with optional focus.
    Synchronous version for scheduled tasks.
    """
    if not group_ids:
        raise ValueError("group_ids cannot be empty")

    # 延迟导入避免循环依赖
    from agent import get_agent

    logger.info(f"Generating brief for groups {group_ids} with focus: {focus}")
    try:
        # 若已存在事件循环（例如在异步上下文中调用），禁止同步包装，避免跨 loop 池复用
        asyncio.get_running_loop()
        raise RuntimeError(
            "generate_brief_for_groups cannot run inside an active event loop; "
            "use await generate_brief_for_groups_async instead"
        )
    except RuntimeError:
        # 无运行中的 loop，安全地创建独立 loop 执行
        brief, ext_info = asyncio.run(get_agent().summarize(24, group_ids, focus))
    if not brief:
        logger.warning("No brief generated for groups %s", group_ids)
        return
    _insert_brief(group_ids, brief, ext_info)
    logger.info("Brief generation completed for groups %s", group_ids)


async def generate_brief_for_groups_async(
    group_ids: list[int], focus: str = "", on_step=None
):
    """
    Generate brief for specific groups asynchronously with optional step callback.
    Returns the generated brief content.

    Args:
        group_ids: 分组ID列表
        focus: 用户关注点
        on_step: 步骤回调函数
    """
    if not group_ids:
        raise ValueError("group_ids cannot be empty")

    logger.info(
        f"Generating brief for groups {group_ids} with focus: {focus}"
    )

    from agent import get_agent

    brief, ext_info = await get_agent().summarize(
        24, group_ids, focus, on_step=on_step
    )
    if not brief:
        logger.warning("No brief generated for groups %s", group_ids)
        return ""
    _insert_brief(group_ids, brief, ext_info)
    logger.info("Brief generation completed for groups %s", group_ids)
    return brief



def _insert_brief(group_ids: list[int], brief: str, ext_info: list = None):
    """插入简报到数据库

    Args:
        group_ids: 分组ID列表
        brief: 简报内容
        ext_info: 外部搜索结果列表（SearchResult 对象或字典）
    """
    # 提取二级标题作为概要
    summary = _extract_h2_headings(brief)

    # 处理外部搜索结果：转换为可序列化的字典格式
    ext_info_list = []
    if ext_info:
        for item in ext_info:
            if isinstance(item, dict):
                # 已经是字典（TypedDict 或普通字典）
                ext_info_list.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                        "score": item.get("score", 0.0),
                    }
                )
            elif hasattr(item, "to_dict"):
                # 有 to_dict 方法的对象
                ext_info_list.append(item.to_dict())
            else:
                # 其他类型，尝试转换为字典
                ext_info_list.append(
                    {
                        "title": getattr(item, "title", ""),
                        "url": getattr(item, "url", ""),
                        "content": getattr(item, "content", ""),
                        "score": getattr(item, "score", 0.0),
                    }
                )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO feed_brief (group_ids, content, summary, ext_info) 
                   VALUES (%s::integer[], %s, %s, %s::jsonb)""",
                (group_ids, brief, summary, json.dumps(ext_info_list)),
            )
