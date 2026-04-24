import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Edit3, FolderPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useApiQuery } from "@/hooks/useApiQuery";
import { useApiMutation } from "@/hooks/useApiMutation";
import { Layout } from "@/components/Layout";
import { Modal } from "@/components/Modal";
import { Select } from "@/components/ui/Select";
import type { Feed, FeedGroup } from "@/types/api";
import { useToast } from "@/context/ToastContext";
import { useConfirm } from "@/context/ConfirmDialogContext";

const GroupsPage = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: groups } = useApiQuery<FeedGroup[]>(
    queryKeys.groups,
    api.getGroups,
  );
  const { data: feeds } = useApiQuery<Feed[]>(queryKeys.feeds, api.getFeeds);
  const { showToast } = useToast();
  const { confirm } = useConfirm();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<{
    id?: number;
    name: string;
    description: string;
    sources: number[];
  } | null>(null);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);

  const allFeeds = feeds ?? [];
  const allGroups = groups ?? [];

  const createMutation = useApiMutation(
    async () => {
      if (!editingGroup) return;
      await api.createGroup({
        title: editingGroup.name,
        desc: editingGroup.description,
        feedIds: editingGroup.sources,
      });
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.groups });
        setIsModalOpen(false);
        showToast(t("groups.createSuccess"));
      },
      onError: (error) => {
        showToast(error.message || t("groups.createFailed"), { type: "error" });
      },
    },
  );

  const updateMutation = useApiMutation(
    async () => {
      if (!editingGroup?.id) return;
      await api.updateGroup(editingGroup.id, {
        title: editingGroup.name,
        desc: editingGroup.description,
        feedIds: editingGroup.sources,
      });
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.groups });
        setIsModalOpen(false);
        showToast(t("groups.updateSuccess"));
      },
      onError: (error) => {
        showToast(error.message || t("groups.updateFailed"), { type: "error" });
      },
    },
  );

  const deleteMutation = useApiMutation(
    async (groupId: number) => {
      await api.deleteGroup(groupId);
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.groups });
        showToast(t("groups.deleteSuccess"));
      },
      onError: (error) => {
        showToast(error.message || t("groups.deleteFailed"), { type: "error" });
      },
    },
  );

  const handleOpenModal = (group?: FeedGroup) => {
    if (group) {
      setEditingGroup({
        id: group.id,
        name: group.title,
        description: group.desc,
        sources: group.feeds.map((f) => f.id),
      });
    } else {
      setEditingGroup({ name: "", description: "", sources: [] });
    }
    setSelectedSourceIds([]);
    setIsModalOpen(true);
  };

  const handleDeleteGroup = async (groupId: number) => {
    const group = allGroups.find((g) => g.id === groupId);
    const confirmed = await confirm({
      title: t("groups.deleteTitle"),
      description: t("groups.deleteDescription", {
        name: group?.title ?? t("groups.deleteFallbackName"),
      }),
      confirmLabel: t("common.delete"),
      cancelLabel: t("common.cancel"),
      tone: "danger",
    });
    if (confirmed) {
      deleteMutation.mutate(groupId);
    }
  };

  const handleSaveGroup = () => {
    if (!editingGroup || !editingGroup.name) return;
    if (editingGroup.id) {
      updateMutation.mutate();
    } else {
      createMutation.mutate();
    }
  };

  const handleRemoveSourceFromGroup = (sourceId: number) => {
    if (!editingGroup) return;
    setEditingGroup({
      ...editingGroup,
      sources: editingGroup.sources.filter((id) => id !== sourceId),
    });
  };

  const handleAddSourceToGroup = () => {
    if (!editingGroup || selectedSourceIds.length === 0) return;
    const sourceIds = selectedSourceIds
      .map((id) => parseInt(id))
      .filter((id) => !Number.isNaN(id));
    const merged = Array.from(new Set([...editingGroup.sources, ...sourceIds]));
    setEditingGroup({
      ...editingGroup,
      sources: merged,
    });
    setSelectedSourceIds([]);
  };

  return (
    <Layout onNewClick={() => handleOpenModal()}>
      <div className="h-full overflow-y-auto p-4 md:p-10 custom-scrollbar grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:gap-6 content-start">
        {allGroups.map((group, index) => (
          <div
            key={group.id}
            className={`theme-surface border theme-border rounded-[2.5rem] p-6 md:p-8 theme-shadow-ambient card-hover theme-transition relative group/card flex flex-col min-h-[210px] md:min-h-[230px] overflow-hidden animate-entrance`}
            style={{ animationDelay: `${Math.min(index * 80, 600)}ms` }}
          >
            {/* Subtle background decoration */}
            <div className="absolute top-0 right-0 w-32 h-32 theme-gradient-subtle opacity-30 rounded-bl-full" />

            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDeleteGroup(group.id);
              }}
              className="absolute top-5 md:top-7 right-5 md:right-7 opacity-100 md:opacity-0 md:group-hover/card:opacity-100 p-2 md:p-2.5 text-rose-400 hover:text-rose-500 transition-all hover:bg-rose-50 rounded-2xl z-10 min-w-[44px] min-h-[44px] flex items-center justify-center theme-transition"
            >
              <Trash2 size={18} />
            </button>
            <div className="flex-1 min-w-0 pr-4 md:pr-6 relative z-10">
              <h3 className="type-card-title theme-text mb-3 truncate leading-tight">
                {group.title}
              </h3>
              <p className="text-xs theme-text-muted leading-relaxed line-clamp-3 mb-4 font-body">
                {group.desc || t("common.noDescription")}
              </p>
            </div>
            <div className="mt-auto pt-5 border-t theme-border-subtle flex items-center justify-between shrink-0 relative z-10">
              <span className="type-caption theme-accent-text italic">
                {t("groups.sourcesCount", { count: group.feeds?.length || 0 })}
              </span>
              <button
                onClick={() => handleOpenModal(group)}
                className="theme-text-muted theme-accent-text-hover p-2 transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center rounded-xl theme-surface-hover"
              >
                <Edit3 size={18} />
              </button>
            </div>
          </div>
        ))}

        {/* Add new button */}
        <button
          onClick={() => handleOpenModal()}
          className="border-2 border-dashed theme-border-subtle rounded-[2.5rem] p-6 flex flex-col items-center justify-center theme-text-muted theme-accent-text-hover theme-surface-hover theme-transition card-hover-subtle min-h-[210px] md:min-h-[230px] animate-entrance"
        >
          <div className="relative">
            <div className="absolute inset-0 theme-accent-subtle rounded-full blur-xl opacity-50" />
            <FolderPlus
              size={32}
              className="md:w-9 md:h-9 mb-3 relative"
              strokeWidth={1.5}
            />
          </div>
          <span className="type-label uppercase">{t("groups.newGroup")}</span>
        </button>
      </div>

      {/* Modal - exactly matching t.tsx */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingGroup?.id ? t("groups.editTitle") : t("groups.createTitle")}
        onConfirm={handleSaveGroup}
      >
        <div className="space-y-6">
          <div className="space-y-4">
            <div>
              <label className="block text-[12px] font-semibold theme-text-muted uppercase mb-2 ml-1">
                {t("groups.groupName")}
              </label>
              <input
                type="text"
                value={editingGroup?.name || ""}
                onChange={(e) =>
                  setEditingGroup((prev) =>
                    prev ? { ...prev, name: e.target.value } : null,
                  )
                }
                className="w-full theme-surface theme-text theme-border border rounded-2xl px-5 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 outline-none"
              />
            </div>
            <div>
              <label className="block text-[12px] font-semibold theme-text-muted uppercase mb-2 ml-1">
                {t("groups.description")}
              </label>
              <textarea
                value={editingGroup?.description || ""}
                onChange={(e) =>
                  setEditingGroup((prev) =>
                    prev ? { ...prev, description: e.target.value } : null,
                  )
                }
                rows={2}
                className="w-full theme-surface theme-text theme-border border rounded-2xl px-5 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 resize-none outline-none"
              />
            </div>
          </div>

          <div className="pt-4 border-t theme-border">
            <label className="text-[12px] font-semibold theme-text-muted uppercase ml-1 mb-4 block">
              {t("groups.sourceManagement")}
            </label>
            <div className="space-y-1.5 mb-4 max-h-64 overflow-y-auto custom-scrollbar">
              {(editingGroup?.sources || []).map((sourceId) => {
                const source = allFeeds.find((f) => f.id === sourceId);
                return (
                  source && (
                    <div
                      key={sourceId}
                      className="flex items-center justify-between px-3 py-2 theme-surface-hover theme-text rounded-lg theme-border border"
                    >
                      <span className="text-xs font-medium truncate">
                        {source.title}
                      </span>
                      <button
                        onClick={() => handleRemoveSourceFromGroup(sourceId)}
                        className="text-rose-400"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )
                );
              })}
            </div>
            <div className="flex gap-2">
              <div className="flex-1">
                <Select
                  value={selectedSourceIds}
                  onChange={(value) =>
                    setSelectedSourceIds(
                      Array.isArray(value) ? value : value ? [value] : [],
                    )
                  }
                  multiple
                  placeholder={t("groups.linkExistingSource")}
                  direction="up"
                  options={[
                    ...allFeeds
                      .filter(
                        (f) => !(editingGroup?.sources || []).includes(f.id),
                      )
                      .map((f) => ({
                        value: f.id.toString(),
                        label: f.title,
                      })),
                  ]}
                  className="text-sm"
                />
              </div>
              <button
                onClick={handleAddSourceToGroup}
                className="theme-btn-primary theme-on-primary px-4 py-2 rounded-xl transition-all shadow-sm hover:shadow-md active:scale-95 min-h-[44px]"
              >
                <Plus size={16} />
              </button>
            </div>
          </div>
        </div>
      </Modal>
    </Layout>
  );
};

export default GroupsPage;
