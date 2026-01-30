"""Curation node: triage research items into keep vs discard."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from core.llm_client import LLMClient
from core.models.llm import Message

from ..state import Citation, DiscardedItem, PSAgentState, ResearchItem, log_step
from ..tools import embed_texts, is_embedding_configured
from ..models import FocusBucket, BucketItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _recency_bonus(published_at: str | None, *, now: datetime) -> float:
    dt = _parse_dt(published_at)
    if not dt:
        return 0.0
    now_ref = datetime.now(dt.tzinfo) if dt.tzinfo else now
    delta_hours = (now_ref - dt).total_seconds() / 3600
    if delta_hours <= 24:
        return 0.8
    if delta_hours <= 72:
        return 0.4
    if delta_hours <= 168:
        return 0.1
    return 0.0


def _source_bonus(source: str) -> float:
    if source == "feed":
        return 1.2
    if source == "web":
        return 0.9
    if source == "memory":
        return 0.5
    return 0.6









def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = sum(a * a for a in vec1) ** 0.5
    norm_b = sum(b * b for b in vec2) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)



def _richness_score(item: ResearchItem) -> float:
    summary = str(item.get("summary", "") or "")
    content = str(item.get("content", "") or "")
    summary_part = min(len(summary) / 1200.0, 0.25)
    content_part = min(len(content) / 5000.0, 0.55)
    return summary_part + content_part


def _final_score(
    item: ResearchItem, 
    similarity: float,
    *, 
    now: datetime
) -> float:
    base = float(item.get("score", 0.0) or 0.0)
    source = str(item.get("source", "") or "")
    recency = _recency_bonus(str(item.get("published_at", "") or ""), now=now)
    richness = _richness_score(item)

    # Weighted blend: Base + Similarity(10x) + Recency + Source + Richness
    # Similarity is 0.0-1.0, so 10x puts it on par with max relevance of ~10.0
    score = base + (similarity * 10.0) + recency + _source_bonus(source) + richness
    return round(score, 4)







def _find_best_bucket(
    item_vec: list[float],
    bucket_vecs: list[list[float]],
    buckets: list[dict],
    threshold: float = 0.2
) -> str | None:
    """Find the best matching bucket for an item embedding."""
    best_bid = None
    best_bsim = 0.0
    
    for b_idx, b_vec in enumerate(bucket_vecs):
        bsim = _cosine_similarity(b_vec, item_vec)
        if bsim > best_bsim:
            best_bsim = bsim
            best_bid = buckets[b_idx]["id"]
            
    if best_bsim < threshold:
        return None
    return best_bid


# ---------------------------------------------------------------------------
# Curation node
# ---------------------------------------------------------------------------


@dataclass
class _ScoredItem:
    item: ResearchItem
    score: float
    bucket_id: str | None = None


def _dedup_key(item: ResearchItem) -> str:
    url = str(item.get("url", "") or "").strip().lower()
    if url:
        return f"url::{url}"
    title = str(item.get("title", "") or "").strip().lower()
    if title:
        return f"title::{title}"
    return f"id::{str(item.get('id', '') or '')}"


def _content_len(item: ResearchItem) -> int:
    return len(str(item.get("content", "") or ""))


def _summary_len(item: ResearchItem) -> int:
    return len(str(item.get("summary", "") or ""))


def _choose_better(prev: _ScoredItem, new: _ScoredItem) -> tuple[_ScoredItem, DiscardedItem | None]:
    """Pick the better duplicate; return (kept, discarded)."""
    if new.score > prev.score:
        discarded = DiscardedItem(
            id=str(prev.item.get("id", "") or ""),
            title=str(prev.item.get("title", "") or ""),
            url=str(prev.item.get("url", "") or ""),
            reason="duplicate_lower_score",
            score=prev.score,
        )
        return new, discarded

    # If scores are similar, prefer richer content.
    if abs(new.score - prev.score) <= 0.2:
        new_rich = (_content_len(new.item), _summary_len(new.item))
        prev_rich = (_content_len(prev.item), _summary_len(prev.item))
        if new_rich > prev_rich:
            discarded = DiscardedItem(
                id=str(prev.item.get("id", "") or ""),
                title=str(prev.item.get("title", "") or ""),
                url=str(prev.item.get("url", "") or ""),
                reason="duplicate_less_content",
                score=prev.score,
            )
            return new, discarded

    discarded = DiscardedItem(
        id=str(new.item.get("id", "") or ""),
        title=str(new.item.get("title", "") or ""),
        url=str(new.item.get("url", "") or ""),
        reason="duplicate_not_selected",
        score=new.score,
    )
    return prev, discarded


def _build_citations(items: list[ResearchItem], *, limit: int = 20) -> list[Citation]:
    citations: list[Citation] = []
    for item in items[:limit]:
        url = str(item.get("url", "") or "").strip()
        if not url:
            continue
        citations.append(
            Citation(
                title=str(item.get("title", "") or "").strip(),
                url=url,
                source=str(item.get("source", "") or ""),
                published_at=str(item.get("published_at", "") or ""),
            )
        )
    return citations


class CurationNode:
    """Triage research items and keep only the most useful evidence."""

    def __init__(self, client: LLMClient):
        # We keep the same signature as other nodes; no LLM call is required here.
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        items = list(state.get("research_items", []))
        if not items:
            return {
                **log_step(state, "ℹ️ curation: 暂无可筛选素材，继续研究"),
                "status": "researching",
                "messages": [Message.assistant("暂无可筛选素材，继续研究。")],
            }

        # 0. Check embedding configuration (Fail Fast)
        if not is_embedding_configured():
            raise RuntimeError("Embedding service not configured. Cannot perform relevance scoring.")

        now = datetime.now()
        max_items = int(state.get("max_context_items", 40) or 40)
        
        # 1. Prepare Focus Embedding
        focus_text = state.get("focus", "")
        buckets = state.get("focus_buckets", [])
        
        # Keep the original logic: expand focus with all buckets for the "Main Focus Vector"
        full_focus_text = focus_text
        for b in buckets:
            full_focus_text += f"\n{b.get('name', '')} {b.get('description', '')}"

        # 2. Prepare Bucket Embeddings
        bucket_texts = [
            (str(b.get("name", "")) + " " + str(b.get("description", ""))).strip()
            for b in buckets
        ]

        # 3. Prepare Item Embeddings + Batching
        # Order: [Focus] + [Buckets...] + [Items...]
        texts_to_embed = [full_focus_text]
        texts_to_embed.extend(bucket_texts)

        for item in items:
            # Combine title + summary for partial embedding
            text = (str(item.get("title", "")) + "\n" + str(item.get("summary", ""))).strip()
            texts_to_embed.append(text)
            
        logger.info("[curation] Embedding %d texts...", len(texts_to_embed))
        embeddings = await embed_texts(texts_to_embed)
        
        if not embeddings or len(embeddings) != len(texts_to_embed):
            # Should basically not happen if is_embedding_configured checked out, but safety first
            raise RuntimeError("Embedding generation failed or returned mismatched count.")
            
        focus_vec = embeddings[0]
        num_buckets = len(buckets)
        bucket_vecs = embeddings[1 : 1 + num_buckets]
        item_vecs = embeddings[1 + num_buckets :]
        
        # 3. Score Items
        scored: list[_ScoredItem] = []
        for idx, item in enumerate(items):
            item_v = item_vecs[idx]
            sim = _cosine_similarity(focus_vec, item_v)

            best_bid = _find_best_bucket(item_v, bucket_vecs, buckets)

            scored.append(_ScoredItem(
                item=item,
                score=_final_score(item, sim, now=now),
                bucket_id=best_bid
            ))


        # Deduplicate while keeping the best representative for each key.
        kept_by_key: dict[str, _ScoredItem] = {}
        discarded: list[DiscardedItem] = []
        for entry in scored:
            key = _dedup_key(entry.item)
            prev = kept_by_key.get(key)
            if not prev:
                kept_by_key[key] = entry
                continue
            chosen, dropped = _choose_better(prev, entry)
            kept_by_key[key] = chosen
            if dropped:
                discarded.append(dropped)

        ranked = sorted(kept_by_key.values(), key=lambda x: x.score, reverse=True)

        # Quota System (P2 Feature + Drop Logic)
        buckets = state.get("focus_buckets", [])
        bucket_quota = 2
        bucket_slots: dict[str, int] = {b["id"]: 0 for b in buckets}
        
        # New: Track matched items directly by ID mapping, not tags
        # { item_id: [bucket_id_1, bucket_id_2] }
        item_bucket_map: dict[str, list[str]] = {} 
        
        kept_ranked: list[ResearchItem] = []
        kept_ids: set[str] = set()

        # Drop Logic (User Request): Check blacklist
        blacklist = set(state.get("blacklist_ids", []) or [])
        
        # Pass 1: Fill Buckets (Priority)
        remaining_candidates = []
        
        for entry in ranked:
            eid = str(entry.item.get("id", ""))
            
            # Explicit Drop
            if eid in blacklist:
                 discarded.append(DiscardedItem(
                     id=eid, 
                     title=str(entry.item.get("title", "")), 
                     url="", 
                     reason="blacklisted_by_evaluator", 
                     score=-1.0
                 ))
                 continue

            bid = entry.bucket_id
            
            if bid and bid in bucket_slots and bucket_slots[bid] < bucket_quota:
                bucket_slots[bid] += 1
                new_item = dict(entry.item)
                # Boost score
                new_item["score"] = entry.score + 0.5 
                # NO TAG INJECTION HERE
                
                kept_ranked.append(ResearchItem(**new_item))
                kept_ids.add(eid)
                
                # Record mapping
                if eid not in item_bucket_map:
                    item_bucket_map[eid] = []
                item_bucket_map[eid].append(bid)
            else:
                remaining_candidates.append(entry)
                
        # Pass 2: General Pool
        spots_left = max_items - len(kept_ranked)
        if spots_left > 0:
            for entry in remaining_candidates:
                if len(kept_ranked) >= max_items:
                    break
                eid = str(entry.item.get("id", ""))
                if eid in blacklist:
                     discarded.append(DiscardedItem(
                         id=eid, 
                         title=str(entry.item.get("title", "")), 
                         url="", 
                         reason="blacklisted_by_evaluator", 
                         score=-1.0
                     ))
                     continue

                kept_ranked.append(entry.item)
                kept_ids.add(eid)

        # Pass 3: Discarded (existing logic covers remainder)
        
        # Update Bucket 'matched_items' using our clean map
        # Ensure we are working with FocusBucket objects
        updated_buckets: list[FocusBucket] = [FocusBucket(**b) for b in buckets]
        bucket_matches_items: dict[str, list[BucketItem]] = {b["id"]: [] for b in updated_buckets}

        for item in kept_ranked:
            eid = str(item.get("id", ""))
            bids = item_bucket_map.get(eid, [])
            
            # Create BucketItem
            bucket_item = BucketItem(
                id=eid,
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                summary=str(item.get("summary", ""))
            )
            
            for bid in bids:
                if bid in bucket_matches_items:
                    bucket_matches_items[bid].append(bucket_item)
        
        for b in updated_buckets:
            b["matched_items"] = bucket_matches_items.get(b["id"], [])


        citations = _build_citations(kept_ranked)
        discarded_all = list(state.get("discarded_items", [])) + discarded

        logger.info(
            "[curation] kept=%d discarded=%d",
            len(kept_ranked),
            len(discarded),
        )

        summary = (
            f"素材筛选完成：保留 {len(kept_ranked)} 条，"
            f"丢弃 {len(discarded)} 条（去重/低相关/超预算）。"
        )

        return {
            **log_step(
                state,
                f"🧹 curation: kept={len(kept_ranked)} discarded={len(discarded)}",
            ),
            "research_items": kept_ranked,
            "citations": citations,
            "discarded_items": discarded_all,
            "focus_buckets": updated_buckets,
            "curation_count": state.get("curation_count", 0) + 1,
            "status": "researching",
            "last_error": None,
            "messages": [Message.assistant(summary)],
        }


# LangGraph wiring helpers ---------------------------------------------------

_curation_node: CurationNode | None = None


def set_curation_client(client: LLMClient) -> None:
    global _curation_node
    _curation_node = CurationNode(client)


async def curation_node(state: PSAgentState) -> dict:
    if _curation_node is None:  # pragma: no cover - defensive
        raise RuntimeError("Curation client not initialized. Call set_curation_client first.")
    return await _curation_node(state)


__all__ = ["CurationNode", "curation_node", "set_curation_client"]
