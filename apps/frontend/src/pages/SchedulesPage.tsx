import { useState, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Edit3, Power, Activity, Sparkles } from "lucide-react";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useApiQuery } from "@/hooks/useApiQuery";
import { useApiMutation } from "@/hooks/useApiMutation";
import { Layout } from "@/components/Layout";
import { Modal } from "@/components/Modal";
import type { Schedule, FeedGroup } from "@/types/api";
import { useToast } from "@/context/ToastContext";
import { useConfirm } from "@/context/ConfirmDialogContext";

const SchedulesPage = () => {
  const queryClient = useQueryClient();
  const { data: schedules } = useApiQuery<Schedule[]>(
    queryKeys.schedules,
    api.getSchedules,
  );
  const { data: groups } = useApiQuery<FeedGroup[]>(
    queryKeys.groups,
    api.getGroups,
  );
  const { showToast } = useToast();
  const { confirm } = useConfirm();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<{
    id?: string;
    time: string;
    groupIds: number[];
    focus: string;
    active: boolean;
    autoExpand: boolean;
  } | null>(null);

  const allSchedules = schedules ?? [];
  const allGroups = groups ?? [];

  // Create a map from group id to group for quick lookup
  const groupMap = useMemo(() => {
    const map = new Map<number, FeedGroup>();
    allGroups.forEach((g) => map.set(g.id, g));
    return map;
  }, [allGroups]);

  const createMutation = useApiMutation(
    async () => {
      if (!editingSchedule) return;
      await api.createSchedule({
        time: editingSchedule.time,
        groupIds: editingSchedule.groupIds,
        focus: editingSchedule.focus,
        autoExpand: editingSchedule.autoExpand,
      });
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.schedules });
        setIsModalOpen(false);
        showToast("定时任务创建成功");
      },
      onError: (error) => {
        showToast(error.message || "创建定时任务失败", { type: "error" });
      },
    },
  );

  const updateMutation = useApiMutation(
    async () => {
      if (!editingSchedule?.id) return;
      await api.updateSchedule(editingSchedule.id, {
        time: editingSchedule.time,
        groupIds: editingSchedule.groupIds,
        focus: editingSchedule.focus,
        enabled: editingSchedule.active,
        autoExpand: editingSchedule.autoExpand,
      });
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.schedules });
        setIsModalOpen(false);
        showToast("定时任务更新成功");
      },
      onError: (error) => {
        showToast(error.message || "更新定时任务失败", { type: "error" });
      },
    },
  );

  const deleteMutation = useApiMutation(
    async (scheduleId: string) => {
      await api.deleteSchedule(scheduleId);
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.schedules });
        showToast("定时任务删除成功");
      },
      onError: (error) => {
        showToast(error.message || "删除定时任务失败", { type: "error" });
      },
    },
  );

  const toggleMutation = useApiMutation(
    async (schedule: Schedule) => {
      await api.updateSchedule(schedule.id, {
        enabled: !schedule.enabled,
      });
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.schedules });
      },
    },
  );

  const handleOpenModal = (schedule?: Schedule) => {
    if (schedule) {
      setEditingSchedule({
        id: schedule.id,
        time: schedule.time,
        groupIds: schedule.groupIds,
        focus: schedule.focus || "",
        active: schedule.enabled,
        autoExpand: schedule.autoExpand ?? false,
      });
    } else {
      setEditingSchedule({
        time: "08:00",
        groupIds: [],
        focus: "",
        active: true,
        autoExpand: false,
      });
    }
    setIsModalOpen(true);
  };

  const handleDeleteSchedule = async (scheduleId: string) => {
    const confirmed = await confirm({
      title: "删除定时任务",
      description: "确定要删除此定时任务吗？此操作无法撤销。",
      confirmLabel: "删除",
      cancelLabel: "取消",
      tone: "danger",
    });
    if (confirmed) {
      deleteMutation.mutate(scheduleId);
    }
  };

  const handleSaveSchedule = () => {
    if (!editingSchedule || !editingSchedule.time) {
      showToast("请输入执行时间", { type: "error" });
      return;
    }
    if (editingSchedule.groupIds.length === 0) {
      showToast("请至少选择一个分组", { type: "error" });
      return;
    }
    if (editingSchedule.id) {
      updateMutation.mutate();
    } else {
      createMutation.mutate();
    }
  };

  const handleToggleSchedule = (schedule: Schedule) => {
    toggleMutation.mutate(schedule);
  };

  const toggleGroupInSchedule = (groupId: number) => {
    if (!editingSchedule) return;
    const current = editingSchedule.groupIds;
    const updated = current.includes(groupId)
      ? current.filter((id) => id !== groupId)
      : [...current, groupId];
    setEditingSchedule({ ...editingSchedule, groupIds: updated });
  };

  return (
    <Layout onNewClick={() => handleOpenModal()}>
      <div className="h-full overflow-y-auto p-4 md:p-12 custom-scrollbar">
        <div className="max-w-5xl mx-auto space-y-4 md:space-y-6">
          {allSchedules.map((task, index) => {
            const isActive = task.enabled;

            return (
              <div
                key={task.id}
                className={`theme-surface rounded-2xl md:rounded-[2.5rem] border theme-transition theme-shadow-ambient card-hover-subtle flex flex-col md:flex-row items-stretch md:items-center p-4 md:p-8 gap-4 md:gap-8 shadow-sm group relative theme-border animate-entrance ${
                  isActive ? "" : "opacity-60 theme-surface-hover"
                }`}
                style={{ animationDelay: `${Math.min(index * 100, 800)}ms` }}
              >
                {/* Time display */}
                <div className="flex flex-row md:flex-col items-center md:items-center shrink-0 w-auto md:w-24 gap-4 md:gap-0">
                  <span
                    className={`text-2xl md:text-3xl font-semibold transition-all theme-text ${
                      isActive ? "" : "theme-text-muted"
                    }`}
                  >
                    {task.time}
                  </span>
                  <div
                    className={`px-3 py-1 rounded-full text-[10px] font-semibold uppercase ${
                      isActive
                        ? "nav-active animate-pulse"
                        : "theme-surface-hover theme-text-muted"
                    }`}
                  >
                    {isActive ? "Next Run" : "Paused"}
                  </div>
                </div>

                <div
                  className="h-[1px] md:h-12 w-full md:w-[1px] rounded-full"
                  style={{ backgroundColor: "var(--theme-border)" }}
                />

                {/* Content */}
                <div className="flex-1 min-w-0 space-y-3">
                  <div className="flex flex-wrap gap-2">
                    {task.groupIds.map((gid) => {
                      const group = groupMap.get(gid);
                      return (
                        <span
                          key={gid}
                          className={`px-3 py-1 border rounded-xl text-[10px] font-semibold transition-all ${
                            isActive
                              ? "theme-surface theme-border theme-accent-text shadow-sm"
                              : "bg-transparent theme-border theme-text-muted"
                          }`}
                        >
                          {group?.title || `分组 ${gid}`}
                        </span>
                      );
                    })}
                  </div>
                  <div className="flex items-start gap-2">
                    <Activity
                      size={14}
                      className={`mt-0.5 ${isActive ? "theme-accent-text" : "theme-text-muted"}`}
                    />
                    <div className="flex flex-wrap items-center gap-2 min-w-0">
                      <p
                        className={`text-sm font-medium leading-relaxed truncate max-w-md ${
                          isActive
                            ? "theme-text-muted"
                            : "theme-text-muted opacity-80"
                        }`}
                      >
                        {task.focus || "默认广度总结模式"}
                      </p>
                      {task.autoExpand && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300">
                          <Sparkles size={11} />
                          自动分析
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Controls */}
                <div className="flex items-center justify-between md:justify-end gap-4 md:gap-6">
                  <div className="flex flex-col items-center gap-2">
                    <button
                      onClick={() => handleToggleSchedule(task)}
                      className={`relative w-16 md:w-20 h-8 md:h-10 rounded-full transition-all duration-300 flex items-center px-1 shadow-inner min-h-[44px] md:min-h-0 ${
                        isActive ? "bg-emerald-500" : "theme-surface-hover"
                      }`}
                      style={
                        !isActive
                          ? { backgroundColor: "var(--theme-border)" }
                          : undefined
                      }
                    >
                      <div
                        className={`absolute transition-all duration-300 h-6 w-6 md:h-8 md:w-8 rounded-full theme-surface shadow-md flex items-center justify-center theme-border border ${
                          isActive
                            ? "translate-x-8 md:translate-x-10"
                            : "translate-x-0"
                        }`}
                      >
                        <Power
                          size={12}
                          className={`md:w-[14px] md:h-[14px] ${
                            isActive ? "text-emerald-500" : "theme-text-muted"
                          }`}
                        />
                      </div>
                    </button>
                  </div>
                  <div
                    className="h-10 w-[1px] hidden md:block rounded-full"
                    style={{ backgroundColor: "var(--theme-border)" }}
                  />
                  <div className="flex flex-row md:flex-col gap-2 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-all duration-300">
                    <button
                      onClick={() => handleOpenModal(task)}
                      className="p-2 md:p-2.5 theme-text-muted theme-accent-text-hover theme-surface-hover rounded-xl transition-all min-w-[44px] min-h-[44px] flex items-center justify-center"
                      aria-label="编辑定时任务"
                    >
                      <Edit3 size={18} />
                    </button>
                    <button
                      onClick={() => handleDeleteSchedule(task.id)}
                      className="p-2 md:p-2.5 theme-text-muted hover:text-rose-500 hover:bg-rose-50 rounded-xl transition-all min-w-[44px] min-h-[44px] flex items-center justify-center"
                      aria-label="删除定时任务"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}

          {/* Add new button */}
          <button
            onClick={() => handleOpenModal()}
            className="w-full py-8 md:py-12 border-2 border-dashed theme-border-subtle rounded-2xl md:rounded-[3rem] flex flex-col items-center justify-center theme-text-muted theme-accent-text-hover theme-surface-hover theme-transition card-hover-subtle animate-entrance gap-2 md:gap-3 min-h-[120px] md:min-h-0"
          >
            <Plus size={32} className="md:w-9 md:h-9" />
            <span className="type-label uppercase">新建自动化方案</span>
          </button>
        </div>
      </div>

      {/* Modal - matching t.tsx schedule modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingSchedule?.id ? "编辑策略" : "新建策略"}
        onConfirm={handleSaveSchedule}
      >
        <div className="space-y-6">
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-[10px] font-semibold theme-text-muted uppercase mb-2 ml-1">
                执行时间
              </label>
              <input
                type="time"
                value={editingSchedule?.time || ""}
                onChange={(e) =>
                  setEditingSchedule((prev) =>
                    prev ? { ...prev, time: e.target.value } : null,
                  )
                }
                className="w-full theme-surface theme-text theme-border border rounded-2xl px-4 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-semibold theme-text-muted uppercase mb-2 ml-1">
              涉及分组 <span className="text-rose-400">*</span>
            </label>
            <div className="flex flex-wrap gap-2">
              {allGroups.map((g) => (
                <button
                  key={g.id}
                  onClick={() => toggleGroupInSchedule(g.id)}
                  className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all border ${
                    editingSchedule?.groupIds.includes(g.id)
                      ? "theme-primary-bg theme-on-primary theme-border"
                      : "theme-surface theme-text-muted theme-border theme-accent-text-hover"
                  }`}
                >
                  {g.title}
                </button>
              ))}
            </div>
            {editingSchedule?.groupIds.length === 0 && (
              <p className="text-xs text-rose-400 mt-2 ml-1">
                请至少选择一个分组
              </p>
            )}
          </div>

          <div>
            <label className="block text-[10px] font-semibold theme-text-muted uppercase mb-2 ml-1">
              关注点
            </label>
            <textarea
              value={editingSchedule?.focus || ""}
              onChange={(e) =>
                setEditingSchedule((prev) =>
                  prev ? { ...prev, focus: e.target.value } : null,
                )
              }
              rows={2}
              className="w-full theme-surface theme-text theme-border border rounded-2xl px-5 py-3 text-sm resize-none outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20"
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="block text-[10px] font-semibold theme-text-muted uppercase ml-1">
                自动展开所有主题
              </label>
              <p className="text-xs theme-text-muted mt-1 ml-1">
                生成后自动展开所有可扩展主题的深度分析
              </p>
            </div>
            <button
              type="button"
              onClick={() =>
                setEditingSchedule((prev) =>
                  prev ? { ...prev, autoExpand: !prev.autoExpand } : null,
                )
              }
              className={`relative w-12 h-7 rounded-full transition-all duration-300 flex items-center px-1 shadow-inner shrink-0 ${
                editingSchedule?.autoExpand
                  ? "bg-emerald-500"
                  : "theme-surface-hover"
              }`}
              style={
                !editingSchedule?.autoExpand
                  ? { backgroundColor: "var(--theme-border)" }
                  : undefined
              }
            >
              <div
                className={`absolute transition-all duration-300 h-5 w-5 rounded-full theme-surface shadow-md theme-border border ${
                  editingSchedule?.autoExpand
                    ? "translate-x-5"
                    : "translate-x-0"
                }`}
              />
            </button>
          </div>
        </div>
      </Modal>
    </Layout>
  );
};

export default SchedulesPage;
