import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Clock, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import { Layout } from "@/components/Layout";
import { useToast } from "@/context/ToastContext";
import type { Memory } from "@/types/api";
import { formatDate } from "@/utils/date";

const MemoryPage = () => {
  const { t } = useTranslation();
  const { id: memoryIdParam } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [memory, setMemory] = useState<Memory | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (memoryIdParam) {
      const memoryId = parseInt(memoryIdParam, 10);
      if (!isNaN(memoryId)) {
        setIsLoading(true);
        api
          .getMemory(memoryId)
          .then((data) => {
            setMemory(data);
            setIsLoading(false);
          })
          .catch((error: any) => {
            console.error("Failed to load memory:", error);
            const errorMessage =
              error?.response?.data?.detail ||
              error?.response?.data?.message ||
              error?.message ||
              t("memory.loadFailed");
            showToast(errorMessage, { type: "error" });
            setIsLoading(false);
            // 延迟导航，让用户看到错误提示
            setTimeout(() => {
              navigate("/", { replace: true });
            }, 1500);
          });
      } else {
        showToast(t("memory.invalidId"), { type: "error" });
        navigate("/", { replace: true });
      }
    }
  }, [memoryIdParam, navigate, showToast]);

  // 处理脚注链接点击事件
  useEffect(() => {
    if (!memory) return;

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
        document.querySelector("#memory-content .prose") ||
        document.querySelector("#memory-content");
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
  }, [memory]);

  const handleBackClick = () => {
    navigate(-1); // 返回上一页
  };

  if (isLoading) {
    return (
      <Layout>
        <div className="h-full flex items-center justify-center">
          <div className="text-slate-400 text-sm">{t("common.loading")}</div>
        </div>
      </Layout>
    );
  }

  if (!memory) {
    return (
      <Layout>
        <div className="h-full flex items-center justify-center">
          <div className="text-slate-400 text-sm">{t("memory.notFound")}</div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout showBackButton onBackClick={handleBackClick}>
      <div className="h-full p-2 md:p-4 flex items-center justify-center bg-slate-100/30">
        <div className="w-full max-w-4xl h-full flex flex-col bg-white shadow-2xl rounded-sm overflow-hidden">
          {/* Header */}
          <div className="p-4 md:p-12 pb-4 md:pb-6 border-b border-black/5 shrink-0">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 md:w-12 md:h-12 bg-amber-600 rounded-xl md:rounded-2xl flex items-center justify-center text-white shadow-lg shadow-amber-100">
                    <FileText size={20} className="md:w-6 md:h-6" />
                  </div>
                  <div>
                    <h1 className="text-xl md:text-2xl font-semibold text-slate-800">
                      {t("memory.title")}
                    </h1>
                    <div className="flex items-center gap-2 text-xs md:text-sm text-slate-400 mt-1">
                      <Clock size={14} />
                      <span>{formatDate(memory.created_at)}</span>
                    </div>
                  </div>
                </div>
                <h2 className="text-lg md:text-xl font-semibold text-slate-700 mb-2">
                  {memory.topic}
                </h2>
                {memory.reasoning && (
                  <p className="text-sm md:text-base text-slate-600 italic">
                    {memory.reasoning}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Content */}
          <div
            className="flex-1 overflow-y-auto px-4 md:px-12 py-6 md:py-10 text-sm md:text-base leading-[2.0] text-slate-700 font-medium custom-scrollbar prose prose-slate max-w-none"
            id="memory-content"
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
              components={{
                // 自定义脚注引用渲染
                sup: ({ node, ...props }: any) => {
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
                      return (
                        <sup className="text-amber-600 font-semibold text-xs ml-0.5">
                          {React.cloneElement(firstChild, {
                            onClick: (
                              e: React.MouseEvent<HTMLAnchorElement>,
                            ) => {
                              e.preventDefault();
                              const href = firstChild.props.href;
                              const targetId = href.substring(1);
                              const targetElement =
                                document.getElementById(targetId);
                              if (targetElement) {
                                targetElement.scrollIntoView({
                                  behavior: "smooth",
                                  block: "center",
                                });
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
                // 自定义链接处理
                a: ({ node, ...props }: any) => {
                  const href = props.href;
                  if (href && href.startsWith("#ref-")) {
                    return (
                      <a
                        {...props}
                        onClick={(e: React.MouseEvent<HTMLAnchorElement>) => {
                          e.preventDefault();
                          const targetId = href.substring(1);
                          const targetElement =
                            document.getElementById(targetId);
                          if (targetElement) {
                            targetElement.scrollIntoView({
                              behavior: "smooth",
                              block: "center",
                            });
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
              {memory.content}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default MemoryPage;
