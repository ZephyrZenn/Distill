import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { DateFilter } from "@/components/DateFilter";
import { Layout } from "@/components/Layout";
import { useToast } from "@/context/ToastContext";
import { useApiQuery } from "@/hooks/useApiQuery";
import type { FeedBrief } from "@/types/api";
import { formatDate } from "@/utils/date";
import { Check, ChevronRight, Copy, FileText, List, X } from "lucide-react";
import React, { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useNavigate, useParams } from "react-router-dom";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";

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

  return points.length > 0 ? points : ["暂无内容预览"];
};

const getTodayString = () => {
  const today = new Date();
  return today.toISOString().split("T")[0];
};

const SummaryPage = () => {
  const { id: briefIdParam } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
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
              "加载简报详情失败";

            // 显示错误提示
            showToast(errorMessage, { type: "error" });

            // 延迟导航，让用户看到错误提示
            setTimeout(() => {
              navigate("/", { replace: true });
            }, 1500);
          });
      } else {
        // 无效的 ID
        showToast("无效的简报ID", { type: "error" });
        navigate("/", { replace: true });
      }
    } else {
      // 没有路由参数时，清空选中的简报（如果是从详情页返回）
      setSelectedBrief(null);
    }
  }, [briefIdParam, navigate, showToast]);

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
        "加载简报详情失败";
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
      showToast("内容已复制到剪贴板", { type: "success" });
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy content:", error);
      showToast("复制失败，请重试", { type: "error" });
    }
  };

  // 计算要显示的简报列表
  const displayBriefs = useMemo(() => briefs || [], [briefs]);

  // 如果正在从路由加载详情，显示加载状态
  if (briefIdParam && isLoadingDetail) {
    return (
      <Layout>
        <div className="h-full flex items-center justify-center">
          <div className="theme-text-muted text-sm">加载中...</div>
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
        <div className="h-full p-2 md:p-4 flex items-center justify-center theme-bg">
          <div className="w-full max-w-7xl h-full flex flex-col theme-surface shadow-2xl rounded-sm overflow-hidden relative border theme-border">
            <div className="p-4 md:p-12 pb-4 md:pb-6 border-b theme-border mx-2 md:mx-12 shrink-0">
              <div className="flex justify-between items-start">
                {/* Group tags */}
                <div className="flex flex-wrap gap-2">
                  {selectedBrief.groups && selectedBrief.groups.length > 0 ? (
                    selectedBrief.groups.map((group) => (
                      <span
                        key={group.id}
                        className="px-4 py-2 theme-surface theme-border border backdrop-blur-sm theme-text rounded-xl text-sm font-bold shadow-sm opacity-90"
                      >
                        {group.title}
                      </span>
                    ))
                  ) : (
                    <span className="px-4 py-2 theme-surface theme-border border backdrop-blur-sm theme-text-muted rounded-xl text-sm opacity-90">
                      未分组
                    </span>
                  )}
                </div>
                {/* Action buttons */}
                <div className="flex items-center gap-2 shrink-0 ml-4">
                  {/* Copy button */}
                  <button
                    onClick={handleCopyContent}
                    className="p-2 rounded-lg theme-text-muted theme-accent-text-hover theme-surface-hover transition-colors"
                    title="复制内容"
                    aria-label="复制内容"
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
                className="flex-1 overflow-y-auto px-4 md:px-12 py-6 md:py-10 text-sm md:text-md leading-[2.0] theme-text font-medium custom-scrollbar prose prose-slate max-w-none"
                id="brief-content"
              >
                {/* 日报概览（放在正文容器内顶部） */}
                <div className="mb-6 py-3 px-4 md:px-5 rounded-xl border theme-overview-border theme-overview-bg">
                  <div className="text-xs font-bold theme-text-muted uppercase tracking-wider mb-1">
                    日报概览
                  </div>
                  {selectedBrief.overview ? (
                    <p className="text-sm theme-text leading-relaxed">
                      {selectedBrief.overview}
                    </p>
                  ) : (
                    <p className="text-sm theme-text-muted leading-relaxed italic">
                      暂无日报概览
                    </p>
                  )}
                </div>

                <ReactMarkdown
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
                      return <h2 id={id} {...props} />;
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
                                      targetElement.style.backgroundColor = "";
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
              </div>

              {/* 大纲侧边栏 - 只在展开时渲染 */}
              {headings.length > 0 && showOutline && (
                <div className="w-full md:w-64 border-t md:border-t-0 md:border-l theme-border theme-surface shrink-0 max-h-[40vh] md:max-h-none opacity-95 backdrop-blur-sm">
                  <div className="sticky top-0 p-4 md:p-6 max-h-full overflow-y-auto custom-scrollbar">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-xs font-bold theme-text uppercase tracking-wider flex items-center gap-2">
                        <List size={14} />
                        文章大纲
                      </h3>
                      <button
                        onClick={() => setShowOutline(false)}
                        className="theme-text-muted theme-accent-text-hover transition-colors text-xs"
                      >
                        隐藏
                      </button>
                    </div>
                    <nav className="space-y-1">
                      {headings.map((heading, index) => (
                        <a
                          key={index}
                          href={`#${heading.id}`}
                          className={`block py-1.5 px-3 rounded-md text-xs transition-colors theme-surface-hover ${
                            heading.level === 1
                              ? "font-bold theme-text"
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
                title="显示大纲"
                aria-label="显示大纲"
              >
                <List size={18} className="md:w-5 md:h-5" />
                <span className="text-[10px] font-medium hidden md:inline">
                  显示
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
          <div className="theme-text-muted text-sm">加载中...</div>
        </div>
      </Layout>
    );
  }

  // Empty state
  if (!displayBriefs || displayBriefs.length === 0) {
    const emptyMessage =
      startDate || endDate ? "所选时间段内未找到摘要" : "暂无今日摘要";
    const emptyDetail =
      startDate || endDate
        ? "请调整时间范围或返回查看今日摘要。"
        : "系统尚未生成今日的 AI 摘要。您可以前往「AI 实时总结」手动生成，或等待定时任务自动执行。";

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
              <h2 className="text-2xl md:text-3xl font-black theme-text mb-3 px-4">
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
              const groupTitle = brief.groups?.[0]?.title || "分组";

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
                      <span className="truncate font-display tracking-wide uppercase">{groupTitle}</span>
                      <span className="text-[11px] shrink-0 ml-2 font-mono-custom">
                        {formatDate(brief.pubDate)}
                      </span>
                    </div>

                    {/* 要点列表 */}
                    <ul className="space-y-3 flex-1 text-sm leading-relaxed theme-text font-body">
                      {keyPoints.map((point, i) => (
                        <li key={i} className="flex gap-3">
                          <span className="shrink-0 mt-2 w-1.5 h-1.5 rounded-full theme-accent-bg opacity-80" />
                          <span className="line-clamp-2">{point}</span>
                        </li>
                      ))}
                    </ul>

                    {/* 进入箭头 */}
                    <div className="mt-5 pt-4 border-t theme-border-subtle flex justify-end items-center theme-text-muted group-hover:theme-accent-text transition-colors">
                      <span className="text-xs font-medium mr-2 font-body-medium">查看全文</span>
                      <ChevronRight size={16} className="group-hover:translate-x-1 transition-transform" />
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
