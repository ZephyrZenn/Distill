import { useState, useRef, useEffect, useCallback } from "react";
import {
  Zap,
  PlayCircle,
  RotateCcw,
  History,
  X,
  Clock,
  CheckCircle,
  XCircle,
  Loader,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useApiQuery } from "@/hooks/useApiQuery";
import { Layout } from "@/components/Layout";
import { useToast } from "@/context/ToastContext";
import { useTaskPolling } from "@/hooks/useTaskPolling";
import type { FeedGroup } from "@/types/api";

interface LogEntry {
  text: string;
  time: string;
}

interface HistoryTask {
  taskId: string;
  createdAt: string;
  status?: "pending" | "running" | "completed" | "failed" | "deleted";
  focus?: string;
  agentMode?: boolean;
}

const TASK_STORAGE_KEY = "instant_lab_active_task";
const HISTORY_STORAGE_KEY = "instant_lab_history_tasks";
const MAX_HISTORY_COUNT = 50; // 最多保存50条历史记录

const InstantLabPage = () => {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { data: groups } = useApiQuery<FeedGroup[]>(
    queryKeys.groups,
    api.getGroups,
  );
  const { showToast } = useToast();

  const [taskId, setTaskId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [agentLogs, setAgentLogs] = useState<LogEntry[]>([]);
  const [generationFocus, setGenerationFocus] = useState("");
  const [selectedGroupsForGen, setSelectedGroupsForGen] = useState<number[]>(
    [],
  );
  const [agentMode, setAgentMode] = useState(false);
  const [isRecovering, setIsRecovering] = useState(true); // 标记是否正在恢复状态
  const [historyTasks, setHistoryTasks] = useState<HistoryTask[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [selectedHistoryTask, setSelectedHistoryTask] =
    useState<HistoryTask | null>(null);
  const [loadingHistoryTask, setLoadingHistoryTask] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const focusInputRef = useRef<HTMLTextAreaElement>(null);

  const allGroups = groups ?? [];

  // Auto-resize focus textarea by content (wrap, no horizontal scroll)
  useEffect(() => {
    const el = focusInputRef.current;
    if (!el) return;
    el.style.height = "auto";
    const min = 40; // ~2.5rem
    const max = 112; // max-h-28
    const h = Math.min(max, Math.max(min, el.scrollHeight));
    el.style.height = `${h}px`;
  }, [generationFocus]);

  // 从 localStorage 加载历史记录
  useEffect(() => {
    const loadHistory = () => {
      try {
        const stored = localStorage.getItem(HISTORY_STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored) as HistoryTask[];
          setHistoryTasks(parsed);
        }
      } catch (error) {
        console.error("Failed to load history:", error);
      }
    };
    loadHistory();
  }, []);

  // 保存历史记录到 localStorage
  const saveHistoryTask = useCallback((task: HistoryTask) => {
    try {
      setHistoryTasks((existing) => {
        const updated = [...existing];
        // 检查是否已存在，如果存在则更新，否则添加到开头
        const index = updated.findIndex((t) => t.taskId === task.taskId);
        if (index >= 0) {
          updated[index] = task;
        } else {
          updated.unshift(task);
        }
        // 限制数量
        const limited = updated.slice(0, MAX_HISTORY_COUNT);
        localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(limited));
        return limited;
      });
    } catch (error) {
      console.error("Failed to save history:", error);
    }
  }, []);

  // 加载历史任务详情
  const loadHistoryTaskDetail = useCallback(
    async (task: HistoryTask) => {
      setLoadingHistoryTask(true);
      try {
        const status = await api.getBriefGenerationStatus(task.taskId);
        const updatedTask: HistoryTask = {
          ...task,
          status: status.status,
        };
        saveHistoryTask(updatedTask);
        setSelectedHistoryTask(updatedTask);
        // 显示日志
        if (status.logs.length > 0) {
          setAgentLogs(
            status.logs.map((log) => ({
              text: log.text,
              time: new Date(log.time).toLocaleTimeString(),
            })),
          );
          // 关闭侧边栏，显示日志视图
          setIsHistoryOpen(false);
        } else {
          showToast(t("instantLab.noLogs"));
        }
      } catch (error: any) {
        // 如果是 404，标记为已删除
        if (error?.response?.status === 404) {
          const deletedTask: HistoryTask = {
            ...task,
            status: "deleted",
          };
          saveHistoryTask(deletedTask);
          setSelectedHistoryTask(deletedTask);
          showToast(t("instantLab.recordDeleted"), { type: "error" });
        } else {
          showToast(t("instantLab.loadTaskFailed"), { type: "error" });
        }
      } finally {
        setLoadingHistoryTask(false);
      }
    },
    [saveHistoryTask, showToast],
  );

  // 组件挂载时检查是否有正在运行的任务
  useEffect(() => {
    const recoverTask = async () => {
      const savedTaskId = localStorage.getItem(TASK_STORAGE_KEY);
      if (savedTaskId) {
        try {
          // 从后端获取任务状态
          const status = await api.getBriefGenerationStatus(savedTaskId);
          if (status.status === "pending" || status.status === "running") {
            // 任务仍在运行，恢复状态
            setTaskId(savedTaskId);
            setIsGenerating(true);
            // 恢复已有的日志
            if (status.logs.length > 0) {
              setAgentLogs(
                status.logs.map((log) => ({
                  text: log.text,
                  time: new Date(log.time).toLocaleTimeString(),
                })),
              );
            }
            // 更新历史记录中的任务状态
            setHistoryTasks((existing) => {
              const existingTask = existing.find(
                (t) => t.taskId === savedTaskId,
              );
              if (existingTask) {
                const updated = [...existing];
                const index = updated.findIndex(
                  (t) => t.taskId === savedTaskId,
                );
                updated[index] = {
                  ...existingTask,
                  status: status.status,
                };
                return updated;
              }
              return existing;
            });
          } else {
            // 任务已完成或失败，清除存储
            localStorage.removeItem(TASK_STORAGE_KEY);
            // 更新历史记录中的任务状态
            setHistoryTasks((existing) => {
              const existingTask = existing.find(
                (t) => t.taskId === savedTaskId,
              );
              if (existingTask) {
                const updated = [...existing];
                const index = updated.findIndex(
                  (t) => t.taskId === savedTaskId,
                );
                updated[index] = {
                  ...existingTask,
                  status: status.status,
                };
                return updated;
              }
              return existing;
            });
          }
        } catch {
          // 任务不存在或出错，清除存储
          localStorage.removeItem(TASK_STORAGE_KEY);
        }
      }
      setIsRecovering(false);
    };

    recoverTask();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // 只在组件挂载时执行一次

  // 自动滚动到底部
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [agentLogs]);

  // 任务完成时的处理
  const handleTaskComplete = useCallback(() => {
    setIsGenerating(false);
    const completedTask: HistoryTask = {
      taskId: taskId!,
      createdAt: new Date().toISOString(),
      status: "completed",
      focus: generationFocus,
      agentMode: agentMode,
    };
    saveHistoryTask(completedTask);
    setTaskId(null);
    localStorage.removeItem(TASK_STORAGE_KEY);
    showToast(t("instantLab.generationSuccess"));
    queryClient.invalidateQueries({ queryKey: queryKeys.briefs() });
    queryClient.invalidateQueries({ queryKey: queryKeys.defaultBriefs });
  }, [
    showToast,
    queryClient,
    taskId,
    generationFocus,
    agentMode,
    saveHistoryTask,
  ]);

  // 任务失败时的处理
  const handleTaskError = useCallback(
    (error: string) => {
      setIsGenerating(false);
      const failedTask: HistoryTask = {
        taskId: taskId!,
        createdAt: new Date().toISOString(),
        status: "failed",
        focus: generationFocus,
        agentMode: agentMode,
      };
      saveHistoryTask(failedTask);
      setTaskId(null);
      localStorage.removeItem(TASK_STORAGE_KEY);
      showToast(t("instantLab.generationFailed", { error }), { type: "error" });
    },
    [showToast, taskId, generationFocus, agentMode, saveHistoryTask],
  );

  // 日志更新处理
  const handleLogUpdate = useCallback(
    (logs: Array<{ text: string; time: string }>) => {
      setAgentLogs(
        logs.map((log) => ({
          text: log.text,
          time: new Date(log.time).toLocaleTimeString(),
        })),
      );
      // 更新历史记录中的任务状态为 running
      if (taskId) {
        setHistoryTasks((existing) => {
          const existingTask = existing.find((t) => t.taskId === taskId);
          if (existingTask && existingTask.status === "pending") {
            const updated = [...existing];
            const index = updated.findIndex((t) => t.taskId === taskId);
            updated[index] = {
              ...existingTask,
              status: "running",
            };
            localStorage.setItem(
              HISTORY_STORAGE_KEY,
              JSON.stringify(updated.slice(0, MAX_HISTORY_COUNT)),
            );
            return updated.slice(0, MAX_HISTORY_COUNT);
          }
          return existing;
        });
      }
    },
    [taskId],
  );

  // 使用轮询 hook 获取任务状态
  useTaskPolling({
    taskId,
    enabled: !!taskId && isGenerating && !isRecovering,
    interval: 3000, // 每3秒轮询一次
    onLogUpdate: handleLogUpdate,
    onComplete: handleTaskComplete,
    onError: handleTaskError,
  });

  const startGeneration = async () => {
    // Agent Mode 需要填写 focus，Workflow Mode 需要至少选择一个分组
    if (agentMode && !generationFocus.trim()) {
      showToast(t("instantLab.agentFocusRequired"), { type: "error" });
      return;
    }
    if (!agentMode && selectedGroupsForGen.length === 0) return;

    try {
      setIsGenerating(true);
      setAgentLogs([]);

      // 创建brief生成任务并获取任务ID
      // AgentMode 时传递空数组，后端会忽略 group_ids
      const { task_id } = await api.generateBrief(
        agentMode ? [] : selectedGroupsForGen,
        generationFocus.trim(),
        agentMode,
      );

      // 保存到 localStorage，以便页面切换后恢复
      localStorage.setItem(TASK_STORAGE_KEY, task_id);
      setTaskId(task_id);

      // 保存到历史记录
      const newTask: HistoryTask = {
        taskId: task_id,
        createdAt: new Date().toISOString(),
        status: "pending",
        focus: generationFocus.trim(),
        agentMode: agentMode,
      };
      saveHistoryTask(newTask);
    } catch (error: any) {
      setIsGenerating(false);
      // FastAPI 返回的错误格式是 { detail: "error message" }
      const errorMessage =
        error?.response?.data?.detail || error?.message || t("instantLab.startTaskFailed");
      showToast(errorMessage, { type: "error" });
    }
  };

  const resetGeneration = () => {
    setIsGenerating(false);
    setAgentLogs([]);
    setTaskId(null);
    setGenerationFocus("");
    setSelectedGroupsForGen([]);
    setAgentMode(false);
    localStorage.removeItem(TASK_STORAGE_KEY);
  };

  const toggleGroupForGen = (groupId: number) => {
    setSelectedGroupsForGen((prev) =>
      prev.includes(groupId)
        ? prev.filter((id) => id !== groupId)
        : [...prev, groupId],
    );
  };

  // 恢复状态时显示加载
  if (isRecovering) {
    return (
      <Layout>
        <div className="h-full overflow-hidden p-4 md:p-12 flex flex-col items-center justify-center">
          <div className="theme-text-muted text-sm">{t("instantLab.checkStatus")}</div>
        </div>
      </Layout>
    );
  }

  // 历史记录侧边栏组件
  const HistorySidebar = () => (
    <div
      className={`fixed right-0 top-0 h-full w-80 theme-surface border-l theme-border theme-shadow-modal z-50 transform transition-transform duration-300 ease-in-out ${
        isHistoryOpen ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="p-4 border-b theme-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={20} className="theme-accent-text" />
            <h3 className="font-semibold theme-text">{t("instantLab.generationHistory")}</h3>
          </div>
          <button
            onClick={() => setIsHistoryOpen(false)}
            className="p-2 theme-surface-hover rounded-lg transition-colors theme-text"
          >
            <X size={18} />
          </button>
        </div>

        {/* History List */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {historyTasks.length === 0 ? (
            <div className="p-8 text-center theme-text-muted text-sm">
              {t("instantLab.noHistory")}
            </div>
          ) : (
            <div className="p-2">
              {historyTasks.map((task, index) => {
                const date = new Date(task.createdAt);
                const StatusIcon =
                  task.status === "completed"
                    ? CheckCircle
                    : task.status === "failed"
                      ? XCircle
                      : task.status === "deleted"
                        ? X
                        : task.status === "running"
                          ? Loader
                          : Clock;
                const statusColor =
                  task.status === "completed"
                    ? "text-emerald-500"
                    : task.status === "failed"
                      ? "text-rose-500"
                      : task.status === "deleted"
                        ? "text-slate-400"
                        : task.status === "running"
                          ? "text-amber-500"
                          : "text-slate-400";

                return (
                  <button
                    key={task.taskId}
                    onClick={() => loadHistoryTaskDetail(task)}
                    disabled={loadingHistoryTask}
                    className={`w-full p-3 mb-2 rounded-lg border theme-transition text-left theme-text card-hover-subtle ${
                      selectedHistoryTask?.taskId === task.taskId
                        ? "nav-active theme-border"
                        : "theme-surface theme-border theme-surface-hover theme-accent-text-hover"
                    } ${loadingHistoryTask ? "opacity-50 cursor-wait" : "cursor-pointer"} animate-entrance`}
                    style={{ animationDelay: `${Math.min(index * 50, 500)}ms` }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <StatusIcon
                            size={14}
                            className={`${statusColor} shrink-0`}
                          />
                          <span
                            className={`text-xs font-medium ${statusColor}`}
                          >
                            {task.status === "completed"
                              ? t("instantLab.completed")
                              : task.status === "failed"
                                ? t("instantLab.failed")
                                : task.status === "deleted"
                                  ? t("instantLab.deleted")
                                  : task.status === "running"
                                    ? t("instantLab.running")
                                    : t("instantLab.pending")}
                          </span>
                          {task.agentMode && (
                            <span className="text-[10px] theme-accent-bg theme-on-accent px-1.5 py-0.5 rounded font-semibold">
                              AGENT
                            </span>
                          )}
                        </div>
                        {task.focus && (
                          <p className="text-xs theme-text truncate mb-1">
                            {task.focus}
                          </p>
                        )}
                        <p className="text-[10px] theme-text-muted">
                          {date.toLocaleString(
                            i18n.resolvedLanguage === "zh" ? "zh-CN" : "en-US",
                            {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                            },
                          )}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  // Console view - when generating or has logs
  if (isGenerating || agentLogs.length > 0) {
    return (
      <Layout>
        <div className="h-full overflow-hidden p-4 md:p-12 flex flex-col items-center relative">
          {/* History button */}
          <button
            onClick={() => setIsHistoryOpen(true)}
            className="fixed right-4 top-24 md:right-8 md:top-28 z-40 p-3 theme-surface border theme-border rounded-xl theme-shadow-ambient theme-surface-hover theme-transition flex items-center gap-2 theme-text theme-accent-text-hover animate-entrance"
            style={{ animationDelay: "100ms" }}
          >
            <History size={18} className="theme-accent-text" />
            <span className="text-xs font-semibold hidden sm:inline font-body-medium">
              {t("instantLab.history")}
            </span>
          </button>

          {/* History Sidebar */}
          <HistorySidebar />

          {/* Overlay when sidebar is open */}
          {isHistoryOpen && (
            <div
              className="fixed inset-0 backdrop-blur-sm z-40 animate-in fade-in duration-300"
              style={{ backgroundColor: "var(--theme-overlay)" }}
              onClick={() => setIsHistoryOpen(false)}
            />
          )}

          <div
            className="w-full max-w-4xl flex flex-col h-full animate-entrance"
            style={{ animationDelay: "200ms" }}
          >
            {/* Console header */}
            <div className="bg-slate-900 rounded-t-2xl md:rounded-t-[3rem] p-4 md:p-8 text-white flex items-center justify-between shadow-2xl border-b border-white/5">
              <div className="flex items-center gap-4">
                <div
                  className={`w-3 h-3 rounded-full ${
                    isGenerating
                      ? "bg-amber-400 animate-pulse"
                      : "bg-emerald-400 shadow-[0_0_15px_rgba(52,211,153,0.5)]"
                  }`}
                />
                <div className="font-mono text-xs md:text-sm font-semibold uppercase">
                  Agent Logic Console
                </div>
              </div>
              {!isGenerating && (
                <button
                  onClick={resetGeneration}
                  className="flex items-center gap-1 md:gap-2 bg-white/10 hover:bg-white/20 px-3 md:px-4 py-2 rounded-xl text-[10px] md:text-xs font-semibold border border-white/10 transition-all min-h-[44px]"
                >
                  <RotateCcw size={14} />{" "}
                    <span className="hidden sm:inline">{t("instantLab.newSummary")}</span>
                </button>
              )}
            </div>

            {/* Console body */}
            <div className="flex-1 bg-slate-900 rounded-b-2xl md:rounded-b-[3rem] p-4 md:p-8 font-mono text-xs md:text-sm overflow-hidden flex flex-col shadow-2xl">
              <div className="flex-1 overflow-y-auto custom-scrollbar-terminal pr-2 md:pr-4 space-y-3 md:space-y-4">
                {agentLogs.map((log, i) => (
                  <div
                    key={i}
                    className="flex gap-4 animate-entrance"
                    style={{ animationDelay: `${Math.min(i * 30, 300)}ms` }}
                  >
                    <span className="text-amber-500/60 shrink-0">
                      [{log.time}]
                    </span>
                    <span
                      className={
                        i === agentLogs.length - 1
                          ? "text-amber-300 font-semibold border-l-2 border-amber-500 pl-3 ml-2"
                          : "text-slate-400 ml-3 pl-3 border-l border-white/5"
                      }
                    >
                      {log.text}
                    </span>
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  // Input form view - GPT chat-like layout
  return (
    <Layout>
      <div className="h-full overflow-hidden flex flex-col relative">
        {/* History button */}
        <button
          onClick={() => setIsHistoryOpen(true)}
          className="fixed right-4 top-24 md:right-8 md:top-28 z-40 p-3 theme-surface border theme-border rounded-xl theme-shadow-ambient theme-surface-hover theme-transition flex items-center gap-2 theme-text theme-accent-text-hover animate-entrance"
          style={{ animationDelay: "100ms" }}
        >
          <History size={18} className="theme-accent-text" />
          <span className="text-xs font-semibold hidden sm:inline font-body-medium">
            {t("instantLab.history")}
          </span>
        </button>

        {/* History Sidebar */}
        <HistorySidebar />

        {/* Overlay when sidebar is open */}
        {isHistoryOpen && (
          <div
            className="fixed inset-0 backdrop-blur-sm z-40 animate-in fade-in duration-300"
            style={{ backgroundColor: "var(--theme-overlay)" }}
            onClick={() => setIsHistoryOpen(false)}
          />
        )}

        <div className="flex-1 flex flex-col items-center justify-center p-4 md:p-8">
          <div className="w-full max-w-3xl flex flex-col h-full max-h-[800px]">
            {/* Header */}
            <div className="mb-6 md:mb-8 flex items-center gap-3 md:gap-4 animate-entrance">
              <div className="relative">
                <div className="absolute inset-0 theme-accent-subtle rounded-xl blur-lg opacity-50" />
                <div className="relative w-10 h-10 md:w-12 md:h-12 theme-primary-bg theme-on-primary rounded-xl md:rounded-2xl flex items-center justify-center shadow-lg">
                  <Zap size={20} className="md:w-6 md:h-6" />
                </div>
              </div>
              <div>
                <h3 className="type-section-title theme-text">
                  {t("instantLab.title")}
                </h3>
                <p className="theme-text-muted text-xs md:text-sm font-body-medium">
                  {t("instantLab.subtitle")}
                </p>
              </div>
            </div>

            {/* Mode container: both modes shown, click to select */}
            <div
              className="mb-3 md:mb-4 rounded-xl theme-surface p-3 md:p-4 theme-border border theme-shadow-ambient animate-entrance"
              style={{ animationDelay: "200ms" }}
            >
              <div className="flex flex-col sm:flex-row items-stretch gap-2 md:gap-3">
                {/* Workflow 模式 - card */}
                <button
                  type="button"
                  onClick={() => {
                    if (agentMode) {
                      setAgentMode(false);
                      setSelectedGroupsForGen([]);
                    }
                  }}
                  className={`flex-1 flex flex-col items-center p-3 md:p-4 rounded-lg border-2 transition-all text-left min-w-0 theme-text ${
                    !agentMode
                      ? "nav-active theme-border"
                      : "theme-border theme-surface theme-surface-hover"
                  }`}
                >
                  <div className="flex items-center justify-center w-14 h-14 md:w-16 md:h-16 overflow-hidden shrink-0">
                    <img
                      src="/workflow.svg"
                      alt=""
                      className="w-full h-full max-w-[56px] max-h-[56px] md:max-w-[64px] md:max-h-[64px] object-contain"
                    />
                  </div>
                  <p className="mt-1.5 text-xs font-semibold theme-text">
                    Workflow
                  </p>
                  <p className="mt-0.5 text-[11px] theme-text-muted">
                    {t("instantLab.workflowDescription")}
                  </p>
                </button>

                {/* PS Agent 模式 - card */}
                <button
                  type="button"
                  onClick={async () => {
                    if (agentMode) return;
                    try {
                      const check = await api.getAgentConfigCheck();
                      if (!check.ready) {
                        showToast(
                          `Agent 模式配置不完整：${check.missing.join("；")}`,
                          { type: "error" },
                        );
                        return;
                      }
                      setAgentMode(true);
                    } catch (e) {
                      showToast("检查 Agent 配置失败，请稍后重试", {
                        type: "error",
                      });
                    }
                  }}
                  className={`flex-1 flex flex-col items-center p-3 md:p-4 rounded-lg border-2 transition-all text-left min-w-0 theme-text ${
                    agentMode
                      ? "nav-active theme-border"
                      : "theme-border theme-surface theme-surface-hover"
                  }`}
                >
                  <div className="flex items-center justify-center w-14 h-14 md:w-16 md:h-16 overflow-hidden shrink-0">
                    <img
                      src="/bot.svg"
                      alt=""
                      className="w-full h-full max-w-[56px] max-h-[56px] md:max-w-[64px] md:max-h-[64px] object-contain"
                    />
                  </div>
                  <p className="mt-1.5 text-xs font-semibold theme-text">
                    Agent
                  </p>
                  <p className="mt-0.5 text-[11px] theme-text-muted">
                    {t("instantLab.agentDescription")}
                  </p>
                </button>
              </div>
            </div>

            {/* Main content area - height follows content */}
            <div
              className="flex flex-col theme-surface rounded-2xl md:rounded-3xl border theme-border theme-shadow-ambient overflow-hidden w-full animate-entrance"
              style={{ animationDelay: "300ms" }}
            >
              {/* Top section - Group selection (standard mode only) */}
              {!agentMode && (
                <div className="border-b theme-border theme-surface-hover p-3 md:p-4">
                  <div className="flex items-start gap-3">
                    <div className="pt-1 text-xs font-semibold theme-text whitespace-nowrap">
                      {t("instantLab.workflowGroups")} <span className="text-rose-400">*</span>
                    </div>
                    <div className="flex-1">
                      <div className="flex flex-wrap gap-2">
                        {allGroups.map((group) => (
                          <button
                            key={group.id}
                            onClick={() => toggleGroupForGen(group.id)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border whitespace-nowrap ${
                              selectedGroupsForGen.includes(group.id)
                                ? "theme-primary-bg theme-on-primary theme-border"
                                : "theme-surface theme-text theme-border theme-accent-text-hover"
                            }`}
                          >
                            {group.title}
                          </button>
                        ))}
                      </div>
                      {selectedGroupsForGen.length === 0 && (
                        <div className="mt-2 text-xs text-rose-400">
                          {t("schedules.groupRequired")}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Chat-like input row: input + send icon in one bar */}
              <div className="px-3 md:px-4 py-3 theme-text">
                <div className="flex items-center gap-2 mb-1.5">
                  <label className="text-xs font-semibold theme-text shrink-0">
                    {t("instantLab.focusLabel")}
                  </label>
                  {agentMode && (
                    <span className="text-rose-400 text-xs">*</span>
                  )}
                  {!agentMode && (
                    <span className="theme-text-muted text-xs">{t("instantLab.optional")}</span>
                  )}
                </div>
                <div
                  className={`flex items-start rounded-lg md:rounded-xl theme-surface border overflow-hidden theme-border ${
                    agentMode && !generationFocus.trim()
                      ? "ring-2 ring-rose-300 border-rose-200"
                      : "focus-within:ring-2 focus-within:ring-[var(--theme-primary)]/30 focus-within:border-[var(--theme-primary)]"
                  }`}
                >
                  <textarea
                    ref={focusInputRef}
                    value={generationFocus}
                    onChange={(e) => setGenerationFocus(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (
                          !(agentMode && !generationFocus.trim()) &&
                          (agentMode || selectedGroupsForGen.length > 0)
                        ) {
                          startGeneration();
                        }
                      }
                    }}
                    placeholder={
                      agentMode
                        ? t("instantLab.focusPlaceholderAgent")
                        : t("instantLab.focusPlaceholderWorkflow")
                    }
                    rows={1}
                    className="flex-1 min-w-0 min-h-[2.25rem] md:min-h-10 max-h-28 py-2.5 px-3 md:px-4 bg-transparent border-none text-sm outline-none resize-none overflow-x-hidden overflow-y-auto break-words"
                  />
                  <button
                    onClick={startGeneration}
                    disabled={
                      (agentMode && !generationFocus.trim()) ||
                      (!agentMode && selectedGroupsForGen.length === 0)
                    }
                    className="h-9 md:h-10 w-9 md:w-10 shrink-0 flex items-center justify-center theme-text-muted theme-accent-text-hover theme-surface-hover disabled:opacity-35 disabled:cursor-not-allowed disabled:hover:bg-transparent transition-colors mt-0.5"
                  >
                    <PlayCircle size={20} />
                  </button>
                </div>
                {agentMode && !generationFocus.trim() && (
                  <p className="text-xs text-rose-400 mt-1 ml-1">
                    {t("instantLab.agentFocusRequired")}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default InstantLabPage;
