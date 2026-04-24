import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { DateFilter } from "@/components/DateFilter";
import { Layout } from "@/components/Layout";
import { useToast } from "@/context/ToastContext";
import { useApiQuery } from "@/hooks/useApiQuery";
import { useQueryClient } from "@tanstack/react-query";
import type { FeedBrief } from "@/types/api";
import { formatDate } from "@/utils/date";
import {
  Check,
  ChevronRight,
  Copy,
  FileText,
  List,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useNavigate, useParams } from "react-router-dom";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import { useTranslation } from "react-i18next";

// 简单 slug 生成，供标题锚点使用
const slugify = (text: string) =>
  text
    .toLowerCase()
    .trim()
    .replace(/[^\w\u4e00-\u9fa5]+/g, "-")
    .replace(/^-+|-+$/g, "");

// 提取大纲（h1-h3）
interface Heading {
  level: number;
  text: string;
  id: string;
}

const extractHeadings = (content: string): Heading[] => {
  const headings: Heading[] = [];
  const lines = content.split("\n");
  lines.forEach((line) => {
    // 更宽松的匹配：允许标题前有空格，标题后可以有空格
    const trimmedLine = line.trim();
    const match = trimmedLine.match(/^(#{1,6})\s+(.+)$/);
    if (match) {
      const level = match[1].length;
      const text = match[2].trim();
      // 使用与 ReactMarkdown 组件一致的 id 格式
      const id = `h${level}-${slugify(text) || Math.random().toString(36).slice(2)}`;
      headings.push({ level, text, id });
    }
  });
  return headings;
};

// Key points: 优先用二级标题，按空间限制数量
const extractKeyPoints = (content: string, maxItems = 4): string[] => {
  const h2Titles = extractHeadings(content)
    .filter((h) => h.level === 2)
    .map((h) => h.text);

  if (h2Titles.length > 0) {
    return h2Titles.slice(0, maxItems);
  }

  // 若无二级标题，退回原有逻辑
  const cleaned = content
    .replace(/^#+\s+.+$/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\[(.+?)\]\(.+?\)/g, "$1")
    .trim();

  const points: string[] = [];
  const paragraphs = cleaned
    .split(/\n\s*\n/)
    .filter((p) => p.trim().length > 0);

  if (paragraphs.length >= 2) {
    for (const para of paragraphs) {
      const firstSentence = para
        .split(/[。.！!？?]/)[0]
        .replace(/\s+/g, " ")
        .trim();
      if (firstSentence.length >= 20 && firstSentence.length <= 180) {
        points.push(firstSentence);
      } else if (firstSentence.length > 180) {
        points.push(firstSentence.slice(0, 177) + "...");
      }
      if (points.length >= maxItems) break;
    }
  }

  if (points.length < maxItems) {
    const sentences = cleaned
      .replace(/\n/g, " ")
      .split(/[。.！!？?]/)
      .map((s) => s.trim())
      .filter((s) => s.length >= 20 && s.length <= 180);
    const needed = maxItems - points.length;
    points.push(...sentences.slice(0, needed));
  }

  return points.length > 0 ? points : [];
};

const getTodayString = () => {
  const today = new Date();
  return today.toISOString().split("T")[0];
};

const SummaryPage = () => {
  const { t } = useTranslation();
  const { id: briefIdParam } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [selectedBrief, setSelectedBrief] = useState<FeedBrief | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [copied, setCopied] = useState(false);
  // 移动端默认隐藏大纲，桌面端默认显示
  const [showOutline, setShowOutline] = useState(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth >= 768; // md breakpoint
    }
    return true;
  });
  const today = getTodayString();
  const [startDate, setStartDate] = useState<string>(today);
  const [endDate, setEndDate] = useState<string>(today);

  // 当进入详情页时，根据屏幕尺寸设置大纲显示状态
  useEffect(() => {
    if (selectedBrief) {
      const isMobile = window.innerWidth < 768; // md breakpoint
      // 桌面端默认显示，移动端默认隐藏（但可以通过按钮显示）
      setShowOutline(!isMobile);
    } else {
      // 返回列表时重置状态
      const isMobile = window.innerWidth < 768;
      setShowOutline(!isMobile);
    }
  }, [selectedBrief]);

  // 处理脚注链接点击事件
  useEffect(() => {
    if (!selectedBrief) return;

    let cleanup: (() => void) | null = null;

    // 等待内容渲染完成
    const timer = setTimeout(() => {
      const handleFootnotClick = (e: Event) => {
        const target = e.target as HTMLElement;
        // 检查是否是脚注链接（在 sup 标签内的 a 标签，或者有 data-footnote-ref 属性）
        const link = target.closest(
          "sup a, [data-footnote-ref]",
        ) as HTMLAnchorElement;
        if (link) {
          const href = link.getAttribute("href") || link.href;
          // remark-gfm 会将脚注链接转换为 #user-content-fn-{index} 格式
          if (
            href &&
            (href.startsWith("#user-content-fn-") ||
              href.startsWith("#ref-") ||
              href.startsWith("#fn"))
          ) {
            e.preventDefault();
            e.stopPropagation();
            let targetId = href.substring(1);
            // 如果是 user-content-fn-{index} 格式，直接使用
            // 如果是其他格式，尝试查找对应的参考资料锚点
            let targetElement = document.getElementById(targetId);
            if (!targetElement && targetId.startsWith("user-content-fn-")) {
              // 已经是对应格式，直接查找
              targetElement = document.getElementById(targetId);
            } else if (targetId.startsWith("ref-")) {
              // 如果是 ref- 格式，转换为 user-content-fn- 格式
              const index = targetId.replace("ref-", "");
              targetId = `user-content-fn-${index}`;
              targetElement = document.getElementById(targetId);
            } else if (targetId.startsWith("fn")) {
              // 如果是 fn 格式，转换为 user-content-fn- 格式
              const index = targetId.replace("fn", "");
              targetId = `user-content-fn-${index}`;
              targetElement = document.getElementById(targetId);
            }

            if (targetElement) {
              targetElement.scrollIntoView({
                behavior: "smooth",
                block: "center",
              });
              // 高亮目标元素
              const originalBg = targetElement.style.backgroundColor;
              targetElement.style.backgroundColor = "rgba(99, 102, 241, 0.1)";
              setTimeout(() => {
                targetElement.style.backgroundColor = originalBg;
              }, 2000);
            } else {
              console.warn("找不到目标元素:", targetId, "原始链接:", href);
            }
          }
        }
      };

      // 使用事件委托，监听整个内容区域的点击
      const contentArea =
        document.querySelector("#brief-content .prose") ||
        document.querySelector("#brief-content");
      if (contentArea) {
        contentArea.addEventListener("click", handleFootnotClick);
        cleanup = () => {
          contentArea.removeEventListener("click", handleFootnotClick);
        };
      }
    }, 100);

    return () => {
      clearTimeout(timer);
      if (cleanup) cleanup();
    };
  }, [selectedBrief]);

  // 使用新的getBriefs API，默认获取当日
  const { data: briefs, isLoading } = useApiQuery<FeedBrief[]>(
    queryKeys.briefs(startDate, endDate),
    () => api.getBriefs(startDate, endDate),
  );

  // 从路由参数加载简报详情
  useEffect(() => {
    if (briefIdParam) {
      const briefId = parseInt(briefIdParam, 10);
      if (!isNaN(briefId)) {
        setIsLoadingDetail(true);
        api
          .getBriefDetail(briefId)
          .then((brief) => {
            setSelectedBrief(brief);
            setIsLoadingDetail(false);
          })
          .catch((error: any) => {
            console.error("Failed to load brief detail:", error);
            setIsLoadingDetail(false);

            // 提取错误信息
            const errorMessage =
              error?.response?.data?.detail ||
              error?.response?.data?.message ||
              error?.message ||
              t("summary.loadFailed");

            // 显示错误提示
            showToast(errorMessage, { type: "error" });

            // 延迟导航，让用户看到错误提示
            setTimeout(() => {
              navigate("/", { replace: true });
            }, 1500);
          });
      } else {
        // 无效的 ID
        showToast(t("summary.invalidId"), { type: "error" });
        navigate("/", { replace: true });
      }
    } else {
      // 没有路由参数时，清空选中的简报（如果是从详情页返回）
      setSelectedBrief(null);
    }
  }, [briefIdParam, navigate, showToast]);

  // 轮询当前正在扩展的主题（仅在有选中简报时启用）
  const { data: expandingTopicIds = [] } = useApiQuery<string[]>(
    ["briefs", "expanding", selectedBrief?.id],
    () => api.getExpandingTopics(selectedBrief!.id),
    { enabled: !!selectedBrief?.id, refetchInterval: 3000 },
  );
  const expandingTopicSet = useMemo(() => new Set(expandingTopicIds), [expandingTopicIds]);
  const prevExpandingTopicIdsRef = useRef<string[]>([]);

  useEffect(() => {
    if (!selectedBrief?.id) {
      prevExpandingTopicIdsRef.current = [];
      return;
    }

    const prevExpandingTopicIds = prevExpandingTopicIdsRef.current;
    const completedTopicIds = prevExpandingTopicIds.filter(
      (topicId) => !expandingTopicIds.includes(topicId),
    );

    // 发现有 topic 从「分析中」变为「已完成」后，自动刷新详情和列表。
    if (completedTopicIds.length > 0) {
      api
        .getBriefDetail(selectedBrief.id)
        .then((brief) => {
          setSelectedBrief(brief);
          queryClient.invalidateQueries({ queryKey: queryKeys.briefs(startDate, endDate) });
        })
        .catch((error: any) => {
          console.error("Failed to refresh brief detail after topic expansion:", error);
        });
    }

    prevExpandingTopicIdsRef.current = expandingTopicIds;
  }, [expandingTopicIds, queryClient, selectedBrief, startDate, endDate]);

  // 处理简报点击，如果简报没有完整内容则加载详情
  const handleBriefClick = async (brief: FeedBrief) => {
    try {
      // 如果简报已经有完整内容，直接导航
      if (brief.content) {
        navigate(`/brief/${brief.id}`);
        return;
      }

      // 否则先加载完整内容，再导航
      const fullBrief = await api.getBriefDetail(brief.id);
      setSelectedBrief(fullBrief);
      navigate(`/brief/${brief.id}`);
    } catch (error: any) {
      console.error("Failed to load brief detail:", error);
      const errorMessage =
        error?.response?.data?.detail ||
        error?.response?.data?.message ||
        error?.message ||
        t("summary.loadFailed");
      showToast(errorMessage, { type: "error" });
    }
  };

  // 处理返回按钮点击
  const handleBackClick = () => {
    navigate("/");
  };

  // 处理复制内容
  const handleCopyContent = async () => {
    if (!selectedBrief?.content) return;

    try {
      await navigator.clipboard.writeText(selectedBrief.content);
      setCopied(true);
      showToast(t("summary.copied"), { type: "success" });
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy content:", error);
      showToast(t("summary.copyFailed"), { type: "error" });
    }
  };

  const handleExpandTopic = async (topicId: string) => {
    if (!selectedBrief?.id) return;
    try {
      await api.expandOptionalTopic(selectedBrief.id, topicId);
      queryClient.invalidateQueries({ queryKey: ["briefs", "expanding", selectedBrief.id] });
      showToast(t("summary.analysisQueued"));
    } catch {
      showToast(t("summary.analysisTriggerFailed"));
    }
  };

  // 计算要显示的简报列表
  const displayBriefs = useMemo(() => briefs || [], [briefs]);

  // 如果正在从路由加载详情，显示加载状态
  if (briefIdParam && isLoadingDetail) {
    return (
      <Layout>
        <div className="h-full flex items-center justify-center">
          <div className="theme-text-muted text-sm">{t("common.loading")}</div>
        </div>
      </Layout>
    );
  }

  // Detail view
  if (selectedBrief) {
    const headings = extractHeadings(selectedBrief.content || "");

    // 调试：检查标题提取
    if (headings.length === 0 && selectedBrief.content) {
      console.log(
        "未提取到标题，内容预览:",
        selectedBrief.content.substring(0, 200),
      );
    }

    return (
      <Layout showBackButton onBackClick={handleBackClick}>
        <div className="h-full p-0 md:p-4 flex items-center justify-center theme-bg">
          <div className="w-full max-w-6xl h-full flex flex-col theme-surface shadow-2xl md:rounded-sm overflow-hidden relative border theme-border">
            <div className="px-5 py-4 md:px-10 md:py-5 border-b theme-border shrink-0">
              <div className="flex justify-between items-start gap-4">
                <div className="min-w-0">
                  {/* Group tags */}
                  <div className="flex flex-wrap gap-2">
                    {selectedBrief.groups && selectedBrief.groups.length > 0 ? (
                      selectedBrief.groups.map((group) => (
                        <span
                          key={group.id}
                          className="px-3 py-1.5 theme-surface theme-border border theme-text rounded-lg text-xs font-semibold opacity-90"
                        >
                          {group.title}
                        </span>
                      ))
                    ) : (
                      <span className="px-3 py-1.5 theme-surface theme-border border theme-text-muted rounded-lg text-xs opacity-90">
                        {t("common.ungrouped")}
                      </span>
                    )}
                  </div>
                  <div className="mt-2 text-xs theme-text-muted type-mono">
                    {formatDate(selectedBrief.pubDate)}
                  </div>
                </div>
                {/* Action buttons */}
                <div className="flex items-center gap-2 shrink-0 ml-4">
                  {/* Copy button */}
                  <button
                    onClick={handleCopyContent}
                    className="p-2 rounded-lg theme-text-muted theme-accent-text-hover theme-surface-hover transition-colors"
                    title={t("summary.copyContent")}
                    aria-label={t("summary.copyContent")}
                  >
                    {copied ? (
                      <Check size={18} className="text-green-600" />
                    ) : (
                      <Copy size={18} />
                    )}
                  </button>
                  {/* Close button */}
                  <X
                    className="cursor-pointer theme-text-muted theme-accent-text-hover transition-colors"
                    onClick={handleBackClick}
                  />
                </div>
              </div>
            </div>

            <div className="flex-1 flex flex-col md:flex-row overflow-hidden relative">
              {/* 主内容区域 */}
              <div
                className="flex-1 overflow-y-auto px-5 py-6 md:px-10 md:py-10 theme-text custom-scrollbar"
                id="brief-content"
              >
                <article className="summary-reader summary-reader-body mx-auto w-full max-w-[72ch]">
                  {/* 日报概览（放在正文容器内顶部） */}
                  <div className="summary-reader-overview mb-8 rounded-lg border theme-overview-border theme-overview-bg">
                    <div className="text-xs font-semibold theme-text-muted uppercase mb-2">
                      {t("summary.dailyOverview")}
                    </div>
                    {selectedBrief.overview ? (
                      <p className="theme-text">{selectedBrief.overview}</p>
                    ) : (
                      <p className="theme-text-muted italic">{t("summary.dailyOverviewEmpty")}</p>
                    )}
                  </div>

                  <ReactMarkdown
                    className="summary-reader-prose prose prose-slate max-w-none"
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeRaw]}
                    components={{
                      h1: ({ node, ...props }) => {
                        const text = String(props.children ?? "");
                        const id = `h1-${slugify(text)}`;
                        return <h1 id={id} {...props} />;
                      },
                      h2: ({ node, ...props }) => {
                        const text = String(props.children ?? "");
                        const id = `h2-${slugify(text)}`;
                        const expandableTopic =
                          selectedBrief.expandableTopics?.find(
                            (topic) =>
                              text.includes(topic.topic) ||
                              text.includes(topic.topicId),
                          );

                        if (!expandableTopic) {
                          return <h2 id={id} {...props} />;
                        }

                        return (
                          <div className="summary-reader-heading-action flex flex-wrap items-baseline gap-x-2 gap-y-1">
                            <h2 id={id} {...props} />
                            <div className="relative group/expand shrink-0">
                              <button
                                type="button"
                                onClick={() =>
                                  handleExpandTopic(expandableTopic.topicId)
                                }
                                disabled={expandingTopicSet.has(expandableTopic.topicId)}
                                aria-label={t("summary.analysisHelp", {
                                  topic: expandableTopic.topic,
                                })}
                                className="summary-reader-expand-pill focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--theme-interactive)] disabled:opacity-60 disabled:cursor-not-allowed"
                              >
                                {expandingTopicSet.has(expandableTopic.topicId) ? (
                                  <Loader2
                                    size={14}
                                    strokeWidth={2}
                                    className="shrink-0 animate-spin"
                                  />
                                ) : (
                                  <Sparkles
                                    size={14}
                                    strokeWidth={2}
                                    className="summary-reader-expand-pill-icon shrink-0"
                                  />
                                )}
                                <span>
                                  {expandingTopicSet.has(expandableTopic.topicId)
                                    ? t("summary.analyzing")
                                    : t("summary.analyze")}
                                </span>
                              </button>
                              <div className="pointer-events-none absolute left-0 top-full mt-1 z-50 w-56 rounded-lg border theme-border theme-surface shadow-lg px-3 py-2 text-xs theme-text leading-relaxed opacity-0 group-hover/expand:opacity-100 transition-opacity duration-150">
                                <p className="font-semibold theme-accent-text mb-1">
                                  {t("summary.analysisAvailable")}
                                </p>
                                <p className="theme-text-muted">
                                  {t("summary.analysisHelp", {
                                    topic: expandableTopic.topic,
                                  })}
                                </p>
                              </div>
                            </div>
                          </div>
                        );
                      },
                      h3: ({ node, ...props }) => {
                        const text = String(props.children ?? "");
                        const id = `h3-${slugify(text)}`;
                        return <h3 id={id} {...props} />;
                      },
                      // 自定义脚注引用渲染
                      sup: ({ node, ...props }: any) => {
                        // 检查是否是脚注引用
                        const children = props.children;
                        if (Array.isArray(children) && children.length > 0) {
                          const firstChild = children[0];
                          // 检查是否是脚注链接（指向 #ref- 或 #fn）
                          if (
                            typeof firstChild === "object" &&
                            firstChild?.props?.href &&
                            (firstChild.props.href.startsWith("#ref-") ||
                              firstChild.props.href.startsWith("#fn"))
                          ) {
                            // 这是脚注引用，渲染为角标样式，并处理点击事件
                            return (
                              <sup className="theme-accent-text font-semibold text-xs ml-0.5">
                                {React.cloneElement(firstChild, {
                                  onClick: (
                                    e: React.MouseEvent<HTMLAnchorElement>,
                                  ) => {
                                    e.preventDefault();
                                    const href = firstChild.props.href;
                                    const targetId = href.substring(1); // 去掉 #
                                    const targetElement =
                                      document.getElementById(targetId);
                                    if (targetElement) {
                                      targetElement.scrollIntoView({
                                        behavior: "smooth",
                                        block: "center",
                                      });
                                      // 高亮目标元素
                                      targetElement.style.backgroundColor =
                                        "rgba(99, 102, 241, 0.1)";
                                      setTimeout(() => {
                                        targetElement.style.backgroundColor =
                                          "";
                                      }, 2000);
                                    }
                                  },
                                })}
                              </sup>
                            );
                          }
                        }
                        return <sup {...props} />;
                      },
                      // 自定义链接处理，确保参考资料链接正常工作
                      a: ({ node, ...props }: any) => {
                        const href = props.href;
                        // 如果是参考资料锚点链接，添加平滑滚动
                        if (href && href.startsWith("#ref-")) {
                          return (
                            <a
                              {...props}
                              onClick={(
                                e: React.MouseEvent<HTMLAnchorElement>,
                              ) => {
                                e.preventDefault();
                                const targetId = href.substring(1);
                                const targetElement =
                                  document.getElementById(targetId);
                                if (targetElement) {
                                  targetElement.scrollIntoView({
                                    behavior: "smooth",
                                    block: "center",
                                  });
                                  // 高亮目标元素
                                  targetElement.style.backgroundColor =
                                    "rgba(99, 102, 241, 0.1)";
                                  setTimeout(() => {
                                    targetElement.style.backgroundColor = "";
                                  }, 2000);
                                }
                              }}
                            />
                          );
                        }
                        return <a {...props} />;
                      },
                    }}
                  >
                    {selectedBrief.content || ""}
                  </ReactMarkdown>
                </article>
              </div>

              {/* 大纲侧边栏 - 只在展开时渲染 */}
              {headings.length > 0 && showOutline && (
                <div className="w-full md:w-72 border-t md:border-t-0 md:border-l theme-border theme-surface shrink-0 max-h-[40vh] md:max-h-none opacity-95 backdrop-blur-sm">
                  <div className="sticky top-0 p-4 md:p-5 max-h-full overflow-y-auto custom-scrollbar">
                    <div className="flex items-center justify-between gap-3 mb-4">
                      <h3 className="text-xs font-semibold theme-text uppercase flex items-center gap-2">
                        <List size={14} />
                        {t("summary.outline")}
                      </h3>
                      <button
                        onClick={() => setShowOutline(false)}
                        className="theme-text-muted theme-accent-text-hover transition-colors text-xs"
                      >
                        {t("summary.hide")}
                      </button>
                    </div>
                    <nav className="space-y-1">
                      {headings.map((heading, index) => (
                        <a
                          key={index}
                          href={`#${heading.id}`}
                          className={`block py-1.5 px-2 rounded-md text-xs leading-relaxed transition-colors theme-surface-hover line-clamp-2 ${
                            heading.level === 1
                              ? "font-semibold theme-text"
                              : heading.level === 2
                                ? "font-semibold theme-text ml-2"
                                : "theme-text-muted ml-4"
                          }`}
                          style={{
                            marginLeft: `${(heading.level - 1) * 0.75}rem`,
                          }}
                          onClick={(e) => {
                            e.preventDefault();
                            const el = document.getElementById(heading.id);
                            if (el) {
                              el.scrollIntoView({
                                behavior: "smooth",
                                block: "start",
                              });
                            }
                          }}
                        >
                          {heading.text}
                        </a>
                      ))}
                    </nav>
                  </div>
                </div>
              )}
            </div>

            {/* 显示按钮 - 移到外层，避免被 overflow-hidden 裁剪 */}
            {headings.length > 0 && !showOutline && (
              <button
                onClick={() => setShowOutline(true)}
                className="fixed md:absolute right-4 md:right-2 bottom-20 md:bottom-auto md:top-1/2 md:-translate-y-1/2 w-12 h-12 md:w-10 md:h-20 theme-surface backdrop-blur-sm border theme-border rounded-lg md:rounded-l-lg shadow-xl flex flex-col items-center justify-center gap-1 theme-text theme-accent-text-hover theme-surface-hover transition-all z-50 min-w-[44px] min-h-[44px]"
                title={t("summary.show")}
                aria-label={t("summary.show")}
              >
                <List size={18} className="md:w-5 md:h-5" />
                <span className="text-[10px] font-medium hidden md:inline">
                  {t("summary.show")}
                </span>
              </button>
            )}
          </div>
        </div>
      </Layout>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <Layout>
        <div className="h-full flex items-center justify-center">
          <div className="theme-text-muted text-sm">{t("common.loading")}</div>
        </div>
      </Layout>
    );
  }

  // Empty state
  if (!displayBriefs || displayBriefs.length === 0) {
    const emptyMessage =
      startDate || endDate
        ? t("summary.emptyRangeTitle")
        : t("summary.emptyTodayTitle");
    const emptyDetail =
      startDate || endDate
        ? t("summary.emptyRangeDetail")
        : t("summary.emptyTodayDetail");

    return (
      <Layout>
        <div className="h-full p-4 md:p-12 custom-scrollbar overflow-y-auto">
          <div className="max-w-7xl mx-auto">
            {/* Date filter */}
            <div className="mb-6 md:mb-8 p-4 md:p-6 theme-surface rounded-[2rem] border theme-border shadow-sm">
              <DateFilter
                startDate={startDate}
                endDate={endDate}
                onStartDateChange={setStartDate}
                onEndDateChange={setEndDate}
              />
            </div>

            {/* Empty state */}
            <div className="flex flex-col items-center justify-center text-center pt-6 md:pt-12">
              <div className="relative mb-6 md:mb-8">
                <div className="absolute inset-0 bg-amber-500/20 blur-[40px] rounded-full" />
                <div className="relative p-6 md:p-8 theme-surface border theme-border rounded-[2.5rem] shadow-xl">
                  <FileText
                    size={40}
                    className="md:w-12 md:h-12 theme-accent-text"
                  />
                </div>
              </div>
              <h2 className="text-2xl md:text-3xl font-semibold theme-text mb-3 px-4">
                {emptyMessage}
              </h2>
              <p className="theme-text-muted max-w-md leading-relaxed px-4 text-sm md:text-base">
                {emptyDetail}
              </p>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  // Grid view - exactly matching t.tsx stream view
  return (
    <Layout>
      <div className="h-full overflow-y-auto p-4 md:p-12 custom-scrollbar">
        <div className="max-w-7xl mx-auto">
          {/* Date filter */}
          <div className="mb-6 md:mb-8 p-4 md:p-6 theme-surface rounded-[2rem] border theme-border shadow-sm">
            <DateFilter
              startDate={startDate}
              endDate={endDate}
              onStartDateChange={setStartDate}
              onEndDateChange={setEndDate}
            />
          </div>

          {/* 近期摘要列表 - 主题一致卡片 */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
            {displayBriefs.map((brief, index) => {
              const keyPoints = brief.summary
                ? brief.summary
                    .split("\n")
                    .filter((line) => line.trim())
                    .slice(0, 4)
                : extractKeyPoints(brief.content || "");
              const groupTitle = brief.groups?.[0]?.title || t("common.ungrouped");
              const pointsToRender =
                keyPoints.length > 0 ? keyPoints : [t("summary.previewFallback")];

              return (
                <button
                  type="button"
                  key={brief.id}
                  onClick={() => handleBriefClick(brief)}
                  className={`group w-full text-left p-6 md:p-7 rounded-2xl theme-surface border theme-border theme-shadow-ambient card-hover theme-transition animate-entrance min-h-[260px] md:min-h-[280px] flex flex-col relative overflow-hidden`}
                  style={{ animationDelay: `${(index % 3) * 100 + 100}ms` }}
                >
                  {/* Subtle gradient overlay */}
                  <div className="absolute inset-0 theme-gradient-subtle opacity-50 pointer-events-none" />

                  {/* Content */}
                  <div className="relative z-10 flex flex-col h-full">
                    {/* 标题行：分组 + 日期 */}
                    <div className="flex justify-between items-center mb-4 text-xs font-semibold theme-text-muted">
                      <span className="truncate type-label uppercase">
                        {groupTitle}
                      </span>
                      <span className="text-[11px] shrink-0 ml-2 type-mono">
                        {formatDate(brief.pubDate)}
                      </span>
                    </div>

                    {/* 要点列表 */}
                    <ul className="space-y-3 flex-1 text-sm leading-relaxed theme-text font-body">
                      {pointsToRender.map((point, i) => (
                        <li key={i} className="flex gap-3">
                          <span className="shrink-0 mt-2 w-1.5 h-1.5 rounded-full theme-accent-bg opacity-80" />
                          <span className="line-clamp-2">{point}</span>
                        </li>
                      ))}
                    </ul>

                    {/* 进入箭头 */}
                    <div className="mt-5 pt-4 border-t theme-border-subtle flex justify-end items-center theme-text-muted group-hover:theme-accent-text transition-colors">
                      <span className="text-xs font-medium mr-2 font-body-medium">
                        {t("summary.viewFull")}
                      </span>
                      <ChevronRight
                        size={16}
                        className="group-hover:translate-x-1 transition-transform"
                      />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default SummaryPage;
