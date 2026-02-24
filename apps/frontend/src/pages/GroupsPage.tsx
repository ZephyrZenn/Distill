import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Trash2,
  Edit3,
  FolderPlus,
} from 'lucide-react';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApiMutation } from '@/hooks/useApiMutation';
import { Layout } from '@/components/Layout';
import { Modal } from '@/components/Modal';
import { Select } from '@/components/ui/Select';
import type { Feed, FeedGroup } from '@/types/api';
import { useToast } from '@/context/ToastContext';
import { useConfirm } from '@/context/ConfirmDialogContext';

const GroupsPage = () => {
  const queryClient = useQueryClient();
  const { data: groups } = useApiQuery<FeedGroup[]>(queryKeys.groups, api.getGroups);
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

  const createMutation = useApiMutation(async () => {
    if (!editingGroup) return;
    await api.createGroup({
      title: editingGroup.name,
      desc: editingGroup.description,
      feedIds: editingGroup.sources,
    });
  }, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.groups });
      setIsModalOpen(false);
      showToast('分组创建成功');
    },
    onError: (error) => {
      showToast(error.message || '创建分组失败', { type: 'error' });
    },
  });

  const updateMutation = useApiMutation(async () => {
    if (!editingGroup?.id) return;
    await api.updateGroup(editingGroup.id, {
      title: editingGroup.name,
      desc: editingGroup.description,
      feedIds: editingGroup.sources,
    });
  }, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.groups });
      setIsModalOpen(false);
      showToast('分组更新成功');
    },
    onError: (error) => {
      showToast(error.message || '更新分组失败', { type: 'error' });
    },
  });

  const deleteMutation = useApiMutation(async (groupId: number) => {
    await api.deleteGroup(groupId);
  }, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.groups });
      showToast('分组删除成功');
    },
    onError: (error) => {
      showToast(error.message || '删除分组失败', { type: 'error' });
    },
  });

  const handleOpenModal = (group?: FeedGroup) => {
    if (group) {
      setEditingGroup({
        id: group.id,
        name: group.title,
        description: group.desc,
        sources: group.feeds.map((f) => f.id),
      });
    } else {
      setEditingGroup({ name: '', description: '', sources: [] });
    }
    setSelectedSourceIds([]);
    setIsModalOpen(true);
  };

  const handleDeleteGroup = async (groupId: number) => {
    const group = allGroups.find((g) => g.id === groupId);
    const confirmed = await confirm({
      title: '删除分组',
      description: `确定要删除"${group?.title ?? '此分组'}"吗？此操作无法撤销。`,
      confirmLabel: '删除',
      cancelLabel: '取消',
      tone: 'danger',
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
    const merged = Array.from(
      new Set([...editingGroup.sources, ...sourceIds])
    );
    setEditingGroup({
      ...editingGroup,
      sources: merged,
    });
    setSelectedSourceIds([]);
  };

  return (
    <Layout onNewClick={() => handleOpenModal()}>
      <div className="h-full overflow-y-auto p-4 md:p-10 custom-scrollbar grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:gap-6 content-start">
        {allGroups.map((group) => (
          <div
            key={group.id}
            className="theme-surface border theme-border rounded-[2.5rem] p-6 md:p-8 shadow-sm hover:shadow-md transition-all relative group/card flex flex-col min-h-[200px] md:min-h-[220px]"
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDeleteGroup(group.id);
              }}
              className="absolute top-4 md:top-6 right-4 md:right-6 opacity-100 md:opacity-0 md:group-hover/card:opacity-100 p-2 md:p-2.5 text-rose-300 hover:text-rose-500 transition-all hover:bg-rose-50 rounded-2xl z-10 min-w-[44px] min-h-[44px] flex items-center justify-center"
            >
              <Trash2 size={18} />
            </button>
            <div className="flex-1 min-w-0 pr-4 md:pr-6">
              <h3 className="text-lg md:text-xl font-black theme-text mb-2 truncate">
                {group.title}
              </h3>
              <p className="text-xs theme-text-muted leading-relaxed line-clamp-3 mb-4">
                {group.desc || '暂无描述信息'}
              </p>
            </div>
            <div className="mt-auto pt-4 border-t theme-border flex items-center justify-between shrink-0">
              <span className="text-[10px] font-black theme-accent-text uppercase tracking-widest italic">
                {group.feeds?.length || 0} 个订阅源
              </span>
              <button
                onClick={() => handleOpenModal(group)}
                className="theme-text-muted theme-accent-text-hover p-2 transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
              >
                <Edit3 size={18} />
              </button>
            </div>
          </div>
        ))}

        {/* Add new button */}
        <button
          onClick={() => handleOpenModal()}
          className="border-2 border-dashed theme-border rounded-[2.5rem] p-6 flex flex-col items-center justify-center theme-text-muted theme-accent-text-hover theme-surface-hover transition-all min-h-[200px] md:min-h-[220px]"
        >
          <FolderPlus size={32} className="md:w-9 md:h-9 mb-2" strokeWidth={1.5} />
          <span className="text-xs md:text-sm font-black uppercase">新建分组</span>
        </button>
      </div>

      {/* Modal - exactly matching t.tsx */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingGroup?.id ? '编辑分组' : '新建订阅分组'}
        onConfirm={handleSaveGroup}
      >
        <div className="space-y-6">
          <div className="space-y-4">
            <div>
              <label className="block text-[12px] font-black theme-text-muted uppercase tracking-widest mb-2 ml-1">
                分组名称
              </label>
              <input
                type="text"
                value={editingGroup?.name || ''}
                onChange={(e) =>
                  setEditingGroup((prev) =>
                    prev ? { ...prev, name: e.target.value } : null
                  )
                }
                className="w-full theme-surface theme-text theme-border border rounded-2xl px-5 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 outline-none"
              />
            </div>
            <div>
              <label className="block text-[12px] font-black theme-text-muted uppercase tracking-widest mb-2 ml-1">
                描述
              </label>
              <textarea
                value={editingGroup?.description || ''}
                onChange={(e) =>
                  setEditingGroup((prev) =>
                    prev ? { ...prev, description: e.target.value } : null
                  )
                }
                rows={2}
                className="w-full theme-surface theme-text theme-border border rounded-2xl px-5 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 resize-none outline-none"
              />
            </div>
          </div>

          <div className="pt-4 border-t theme-border">
            <label className="text-[12px] font-black theme-text-muted uppercase tracking-widest ml-1 mb-4 block">
              下属源管理
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
                      Array.isArray(value) ? value : value ? [value] : []
                    )
                  }
                  multiple
                  placeholder="关联已有源..."
                  direction="up"
                  options={[
                    ...allFeeds
                      .filter((f) => !(editingGroup?.sources || []).includes(f.id))
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
