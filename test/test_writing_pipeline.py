"""测试 Structure -> Writing -> Review -> Refine 流程."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from dotenv import load_dotenv

from agent.ps_agent.models import (
    Dimension,
    ResearchItem,
    SectionUnit,
    StructureChapter,
    StructurePlan,
    WritingContext,
    WritingMaterial,
)
from agent.ps_agent.nodes.evaluator.summary_reviewer import SummaryReviewerNode
from agent.ps_agent.nodes.planner.structure import StructureNode
from agent.ps_agent.nodes.solver.refiner import RefinerNode
from agent.ps_agent.nodes.solver.writer import DeepWriterNode
from agent.ps_agent.state import PSAgentState, create_initial_state
from core.config.loader import load_config


class WritingPipelineTest(unittest.TestCase):
    """测试写作流程的各个节点."""

    def setUp(self):
        """设置测试环境和 mock 数据."""
        self.focus = "测试 AI 行业动态"
        self.current_date = "2025-01-15"

        # Mock LLM client
        self.mock_client = MagicMock()
        self.mock_client.completion = AsyncMock()

        # 创建 mock research items
        self.research_items = [
            {
                "id": "item_001",
                "title": "OpenAI 发布 GPT-5 预览版",
                "url": "https://example.com/gpt5",
                "source": "web",
                "published_at": "2025-01-15",
                "summary": "OpenAI 发布 GPT-5 预览版，性能提升显著",
                "content": "OpenAI 发布 GPT-5 预览版，性能提升显著。新模型在推理能力和多模态处理方面有重大突破。",
                "tags": ["OpenAI", "GPT-5", "LLM"],
                "relevance": 0.95,
                "quality": 0.88,
                "novelty": 0.92,
                "score": 0.92,
            },
            {
                "id": "item_002",
                "title": "DeepSeek 推出新推理模型",
                "url": "https://example.com/deepseek",
                "source": "web",
                "published_at": "2025-01-14",
                "summary": "DeepSeek 推出新推理模型，成本降低50%",
                "content": "DeepSeek 推出新推理模型，在保持性能的同时将推理成本降低50%，引发行业关注。",
                "tags": ["DeepSeek", "推理模型", "成本"],
                "relevance": 0.90,
                "quality": 0.85,
                "novelty": 0.88,
                "score": 0.88,
            },
            {
                "id": "item_003",
                "title": "Gemini 2.0 发布",
                "url": "https://example.com/gemini",
                "source": "web",
                "published_at": "2025-01-13",
                "summary": "Google 发布 Gemini 2.0，支持更长上下文",
                "content": "Google 发布 Gemini 2.0，支持 100 万 token 上下文窗口，在长文档处理方面领先。",
                "tags": ["Google", "Gemini", "长上下文"],
                "relevance": 0.88,
                "quality": 0.82,
                "novelty": 0.85,
                "score": 0.85,
            },
        ]

        # Mock focus dimensions
        self.focus_dimensions = [
            Dimension(
                type="technical_facts",
                name="技术突破",
                intent="了解最近的技术突破和创新",
                keywords=["GPT-5", "Gemini 2.0", "推理模型"],
                priority="high",
                relevance_criteria="与 AI 模型性能提升、新特性相关",
            ),
            Dimension(
                type="market_competition",
                name="市场竞争",
                intent="了解各公司之间的竞争态势",
                keywords=["OpenAI", "DeepSeek", "Google"],
                priority="high",
                relevance_criteria="涉及公司市场份额、竞争策略",
            ),
        ]

        # Mock audit_memo (plan review 输出)
        self.audit_memo = {
            "key_findings": [
                "GPT-5 在推理能力上有重大突破",
                "DeepSeek 将推理成本降低50%",
                "Gemini 2.0 在长上下文处理方面领先",
            ],
            "conflicts": [],
            "gaps": ["缺少关于开源模型竞争的信息"],
            "coverage_score": 0.85,
        }

    def create_base_state(self) -> PSAgentState:
        """创建基础测试状态."""
        state = create_initial_state(
            focus=self.focus,
            max_context_items=15,
        )
        state["current_date"] = self.current_date
        state["focus_dimensions"] = self.focus_dimensions
        state["research_items"] = self.research_items
        state["audit_memo"] = self.audit_memo
        state["execution_mode"] = "READY_TO_WRITE"
        return state

    def test_structure_node(self):
        """测试 StructureNode."""

        async def _run_test():
            # Mock LLM response for structure
            structure_response = """
            {
                "daily_overview": "2025年1月AI行业动态：OpenAI发布GPT-5预览版，DeepSeek推出低成本推理模型，Google发布Gemini 2.0支持更长上下文。",
                "analysis_logic": "本报告从技术突破入手，分析各公司最新模型发布，然后探讨市场竞争格局的变化，最后展望行业发展趋势。",
                "chapters": [
                    {
                        "chapter_id": "ch_001",
                        "title": "技术突破：新一代AI模型",
                        "priority": 1,
                        "chapter_goal": "2025年初，各大AI公司相继发布新一代模型，在推理能力、成本控制和上下文长度方面取得显著突破。",
                        "certainty_level": "high",
                        "writing_guide": {
                            "tone": "客观、专业",
                            "key_points": ["GPT-5的推理能力提升", "DeepSeek的成本优化", "Gemini 2.0的长上下文"],
                            "structure": "引言 -> 技术细节 -> 对比分析"
                        },
                        "referenced_doc_ids": ["item_001", "item_002", "item_003"],
                        "conflict_alert": "",
                        "sub_points": ["推理能力对比", "成本效益分析", "应用场景探讨"]
                    }
                ]
            }
            """
            self.mock_client.completion.return_value = structure_response

            state = self.create_base_state()
            node = StructureNode(client=self.mock_client)

            result = await node(state)

            # 验证返回值
            self.assertIn("plan", result)
            self.assertIn("status", result)
            self.assertEqual(result["status"], "structuring")

            plan: StructurePlan = result["plan"]
            self.assertEqual(len(plan["chapters"]), 1)
            self.assertIn("技术突破", plan["chapters"][0]["title"])
            self.assertEqual(plan["chapters"][0]["priority"], 1)

            print("✅ StructureNode 测试通过")
            print(f"   - 概览: {plan['daily_overview'][:50]}...")
            print(f"   - 章节数: {len(plan['chapters'])}")
            return result

        asyncio.run(_run_test())

    def test_writer_node(self):
        """测试 DeepWriterNode."""

        async def _run_test():
            # 准备 state（包含 structure 的输出）
            state = self.create_base_state()

            # 模拟 structure 的输出
            structure_plan: StructurePlan = {
                "daily_overview": "2025年1月AI行业动态：各大公司发布新一代AI模型。",
                "analysis_logic": "从技术突破到市场竞争的分析",
                "chapters": [
                    {
                        "chapter_id": "ch_001",
                        "title": "技术突破：新一代AI模型",
                        "priority": 1,
                        "chapter_goal": "各大AI公司在推理能力和成本控制方面取得突破",
                        "certainty_level": "high",
                        "writing_guide": {
                            "tone": "客观",
                            "key_points": ["推理能力", "成本优化"],
                        },
                        "referenced_doc_ids": ["item_001", "item_002"],
                        "conflict_alert": "",
                        "sub_points": [],
                    }
                ],
            }
            state["plan"] = structure_plan

            # Mock LLM responses
            self.mock_client.completion.side_effect = [
                # _write 的响应
                """# 技术突破：新一代AI模型

2025年初，AI行业迎来新一轮技术突破。OpenAI发布GPT-5预览版，在推理能力上显著提升。与此同时，DeepSeek通过优化架构将推理成本降低50%，为行业提供了新的思路。

## GPT-5的推理能力提升

GPT-5在复杂推理任务中表现出色，特别是在数学和编程领域...
""",
                # _generate_summary 的响应
                "GPT-5在推理能力上有重大突破，DeepSeek通过架构优化显著降低成本。",
            ]

            node = DeepWriterNode(client=self.mock_client)
            result = await node(state)

            # 验证返回值
            self.assertIn("sections", result)
            self.assertIn("status", result)
            self.assertEqual(result["status"], "reviewing")

            sections = result["sections"]
            self.assertEqual(len(sections), 1)

            section: SectionUnit = sections[0]
            self.assertIn("content", section)
            self.assertIn("chapter", section)
            self.assertIn("items", section)
            self.assertIn("context", section)
            self.assertEqual(len(section["items"]), 2)

            print("✅ DeepWriterNode 测试通过")
            print(f"   - 章节数: {len(sections)}")
            print(f"   - 内容长度: {len(section['content'])} 字符")
            return result

        asyncio.run(_run_test())

    def test_reviewer_node(self):
        """测试 SummaryReviewerNode."""

        async def _run_test():
            state = self.create_base_state()

            # 准备 sections（包含 writer 的输出）
            section: SectionUnit = {
                "chapter": {
                    "chapter_id": "ch_001",
                    "title": "技术突破：新一代AI模型",
                    "priority": 1,
                    "chapter_goal": "各大AI公司在推理能力上取得突破",
                    "certainty_level": "high",
                    "writing_guide": {},
                    "referenced_doc_ids": ["item_001", "item_002"],
                    "conflict_alert": "",
                    "sub_points": [],
                },
                "items": self.research_items[:2],
                "content": """# 技术突破：新一代AI模型

2025年初，AI行业迎来新一轮技术突破。OpenAI发布GPT-5预览版...
""",
                "context": WritingContext(
                    global_outline="概览:2025年1月AI行业动态\n分析逻辑:技术突破分析",
                    previous_summary="",
                    section_number=1,
                ),
            }

            state["sections"] = [section]

            # Mock LLM response - 第一次审核未通过
            review_response = """
            {
                "status": "REJECTED",
                "score": 65,
                "summary": "文章结构合理，但内容深度不足",
                "strengths": ["结构清晰", "关键信息覆盖"],
                "findings": [
                    {
                        "type": "SHALLOW_ANALYSIS",
                        "severity": "medium",
                        "description": "对技术细节的描述过于简略",
                        "suggestion": "增加具体的性能对比数据"
                    },
                    {
                        "type": "MISSING_INFO",
                        "severity": "high",
                        "description": "缺少实际应用案例",
                        "suggestion": "补充具体的应用场景和案例"
                    }
                ]
            }
            """
            self.mock_client.completion.return_value = review_response

            node = SummaryReviewerNode(client=self.mock_client)
            result = await node(state)

            # 验证返回值
            self.assertIn("status", result)
            self.assertEqual(result["status"], "refining")

            sections = result["sections"]
            self.assertEqual(len(sections), 1)

            review = sections[0]["review_result"]
            self.assertEqual(review["status"], "REJECTED")
            self.assertEqual(review["score"], 65)
            self.assertEqual(len(review["findings"]), 2)

            print("✅ SummaryReviewerNode 测试通过")
            print(f"   - 审核状态: {review['status']}")
            print(f"   - 审核得分: {review['score']}")
            print(f"   - 问题数: {len(review['findings'])}")
            return result

        asyncio.run(_run_test())

    def test_refiner_node(self):
        """测试 RefinerNode."""

        async def _run_test():
            state = self.create_base_state()

            # 准备 sections（包含 review 的输出）
            section: SectionUnit = {
                "chapter": {
                    "chapter_id": "ch_001",
                    "title": "技术突破：新一代AI模型",
                    "priority": 1,
                    "chapter_goal": "各大AI公司在推理能力上取得突破",
                    "certainty_level": "high",
                    "writing_guide": {},
                    "referenced_doc_ids": ["item_001", "item_002"],
                    "conflict_alert": "",
                    "sub_points": [],
                },
                "items": self.research_items[:2],
                "content": """# 技术突破：新一代AI模型

2025年初，AI行业迎来新一轮技术突破...
""",
                "context": WritingContext(
                    global_outline="概览:2025年1月AI行业动态\n分析逻辑:技术突破分析",
                    previous_summary="",
                    section_number=1,
                ),
                "review_result": {
                    "status": "REJECTED",
                    "score": 65,
                    "summary": "文章结构合理，但内容深度不足",
                    "strengths": ["结构清晰"],
                    "findings": [
                        {
                            "type": "SHALLOW_ANALYSIS",
                            "severity": "medium",
                            "description": "对技术细节的描述过于简略",
                            "suggestion": "增加具体的性能对比数据",
                        },
                    ],
                },
            }

            state["sections"] = [section]

            # Mock LLM response - 修订后的内容
            refined_content = """# 技术突破：新一代AI模型

2025年初，AI行业迎来新一轮技术突破。OpenAI发布GPT-5预览版，在推理能力上显著提升。根据官方测试数据，GPT-5在MATH基准测试中的准确率提升了35%，在编程任务中的Pass@1指标达到78.5%。

## 性能对比分析

与上一代相比，GPT-5在处理复杂推理任务时的速度提升2倍...
"""
            self.mock_client.completion.return_value = refined_content

            node = RefinerNode(client=self.mock_client)
            result = await node(state)

            # 验证返回值
            self.assertIn("status", result)
            self.assertEqual(result["status"], "writing")

            sections = result["sections"]
            refined_section = sections[0]
            self.assertIn("content", refined_section)
            self.assertIn("性能对比分析", refined_section["content"])

            print("✅ RefinerNode 测试通过")
            print(f"   - 修订后内容长度: {len(refined_section['content'])} 字符")
            return result

        asyncio.run(_run_test())

    def test_full_pipeline(self):
        """测试完整的写作流程：Structure -> Writing -> Review -> Refine."""

        async def _run_test():
            state = self.create_base_state()

            # ============ Step 1: Structure ============
            structure_response = """
            {
                "daily_overview": "2025年1月AI行业动态：各大公司发布新一代AI模型。",
                "analysis_logic": "从技术突破到市场竞争的分析",
                "chapters": [
                    {
                        "chapter_id": "ch_001",
                        "title": "技术突破：新一代AI模型",
                        "priority": 1,
                        "chapter_goal": "各大AI公司在推理能力上取得突破",
                        "certainty_level": "high",
                        "writing_guide": {"tone": "客观"},
                        "referenced_doc_ids": ["item_001", "item_002"],
                        "conflict_alert": "",
                        "sub_points": []
                    }
                ]
            }
            """

            # ============ Step 2: Writing ============
            written_content = """# 技术突破：新一代AI模型

2025年初，AI行业迎来新一轮技术突破。OpenAI发布GPT-5预览版...
"""
            summary = "GPT-5在推理能力上有重大突破。"

            # ============ Step 3: Review (第一次未通过) ============
            review_response = """
            {
                "status": "REJECTED",
                "score": 65,
                "summary": "内容深度不足",
                "strengths": ["结构清晰"],
                "findings": [
                    {
                        "type": "SHALLOW_ANALYSIS",
                        "severity": "medium",
                        "description": "缺少具体数据",
                        "suggestion": "补充性能对比数据"
                    }
                ]
            }
            """

            # ============ Step 4: Refine ============
            refined_content = """# 技术突破：新一代AI模型

2025年初，AI行业迎来新一轮技术突破。OpenAI发布GPT-5预览版，在MATH基准测试中的准确率提升了35%...
"""

            # ============ Step 5: Review (第二次通过) ============
            review_approved_response = """
            {
                "status": "APPROVED",
                "score": 85,
                "summary": "文章质量良好，内容详实",
                "strengths": ["数据详实", "分析深入"],
                "findings": []
            }
            """

            # 设置 mock 返回顺序
            self.mock_client.completion.side_effect = [
                structure_response,  # Structure
                written_content,  # Writer._write
                summary,  # Writer._generate_summary
                review_response,  # Reviewer (第一次)
                refined_content,  # Refiner
                review_approved_response,  # Reviewer (第二次)
            ]

            # 执行流程
            structure_node = StructureNode(client=self.mock_client)
            writer_node = DeepWriterNode(client=self.mock_client)
            reviewer_node = SummaryReviewerNode(client=self.mock_client)
            refiner_node = RefinerNode(client=self.mock_client)

            print("\n" + "=" * 60)
            print("🚀 开始测试完整写作流程")
            print("=" * 60)

            # Step 1: Structure
            print("\n📐 Step 1: Structure 生成写作计划...")
            result = await structure_node(state)
            state.update(result)
            print(f"   ✅ 状态: {result['status']}")
            print(f"   📄 章节数: {len(result['plan']['chapters'])}")

            # Step 2: Writing
            print("\n✍️  Step 2: Writing 生成初稿...")
            result = await writer_node(state)
            state.update(result)
            print(f"   ✅ 状态: {result['status']}")
            print(f"   📄 生成章节数: {len(result['sections'])}")

            # Step 3: Review (第一次)
            print("\n🧪 Step 3: Review 审核初稿...")
            result = await reviewer_node(state)
            state.update(result)
            print(f"   ✅ 状态: {result['status']}")
            review_status = result['sections'][0]['review_result']['status']
            print(f"   📄 审核结果: {review_status}")

            # Step 4: Refine
            if result['status'] == 'refining':
                print("\n🔧 Step 4: Refine 修订初稿...")
                result = await refiner_node(state)
                state.update(result)
                print(f"   ✅ 状态: {result['status']}")
                print(f"   📄 修订完成")

            # Step 5: Review (第二次)
            print("\n🧪 Step 5: Review 再次审核...")
            result = await reviewer_node(state)
            state.update(result)
            print(f"   ✅ 状态: {result['status']}")
            if result['status'] == 'completed':
                print(f"   📄 最终报告长度: {len(result['final_report'])} 字符")

            print("\n" + "=" * 60)
            print("✅ 完整流程测试完成！")
            print("=" * 60)

            # 最终验证
            self.assertEqual(state["status"], "completed")
            self.assertIn("final_report", state)
        load_dotenv()
        load_config()
        asyncio.run(_run_test())


if __name__ == "__main__":
    unittest.main(verbosity=2)
