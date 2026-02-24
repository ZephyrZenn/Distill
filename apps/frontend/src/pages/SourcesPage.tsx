import { useState, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Trash2,
  Edit3,
  ExternalLink,
  Link as LinkIcon,
} from 'lucide-react';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApiMutation } from '@/hooks/useApiMutation';
import { Layout } from '@/components/Layout';
import { Modal } from '@/components/Modal';
import type { Feed, FeedGroup } from '@/types/api';
import { useToast } from '@/context/ToastContext';
import { useConfirm } from '@/context/ConfirmDialogContext';

const SourcesPage = () => {
  const queryClient = useQueryClient();
  const { data: feeds } = useApiQuery<Feed[]>(queryKeys.feeds, api.getFeeds);
  const { data: groups } = useApiQuery<FeedGroup[]>(queryKeys.groups, api.getGroups);
  const { showToast } = useToast();
  const { confirm } = useConfirm();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<{
    id?: number;
    name: string;
    url: string;
    desc: string;
  } | null>(null);

  const allFeeds = feeds ?? [];
  const allGroups = groups ?? [];

  // Add group info to each source - matching t.tsx allSourcesWithGroupInfo
  const allSourcesWithGroupInfo = useMemo(() => {
    return allFeeds.map((source) => {
      const group = allGroups.find((g) =>
        g.feeds?.some((f) => f.id === source.id)
      );
      return { ...source, groupName: group ? group.title : '未分组' };
    });
  }, [allFeeds, allGroups]);

  const createMutation = useApiMutation(async () => {
    if (!editingSource) return;
    await api.createFeed({
      title: editingSource.name,
      url: editingSource.url,
      desc: editingSource.desc,
    });
  }, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.feeds });
      setIsModalOpen(false);
      showToast('订阅源创建成功');
    },
    onError: (error) => {
      showToast(error.message || '创建订阅源失败', { type: 'error' });
    },
  });

  const updateMutation = useApiMutation(async () => {
    if (!editingSource?.id) return;
    await api.updateFeed(editingSource.id, {
      title: editingSource.name,
      url: editingSource.url,
      desc: editingSource.desc,
    });
  }, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.feeds });
      setIsModalOpen(false);
      showToast('订阅源更新成功');
    },
    onError: (error) => {
      showToast(error.message || '更新订阅源失败', { type: 'error' });
    },
  });

  const deleteMutation = useApiMutation(async (feedId: number) => {
    await api.deleteFeed(feedId);
  }, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.feeds });
      showToast('订阅源删除成功');
    },
    onError: (error) => {
      showToast(error.message || '删除订阅源失败', { type: 'error' });
    },
  });

  const handleOpenModal = (source?: Feed) => {
    if (source) {
      setEditingSource({
        id: source.id,
        name: source.title,
        url: source.url,
        desc: source.desc ?? '',
      });
    } else {
      setEditingSource({ name: '', url: '', desc: '' });
    }
    setIsModalOpen(true);
  };

  const handleDeleteSource = async (feedId: number) => {
    const feed = allFeeds.find((f) => f.id === feedId);
    const confirmed = await confirm({
      title: '删除订阅源',
      description: `确定要删除"${feed?.title ?? '此订阅源'}"吗？此操作无法撤销。`,
      confirmLabel: '删除',
      cancelLabel: '取消',
      tone: 'danger',
    });
    if (confirmed) {
      deleteMutation.mutate(feedId);
    }
  };

  const handleSaveSource = () => {
    if (!editingSource || !editingSource.name || !editingSource.url) return;
    if (editingSource.id) {
      updateMutation.mutate();
    } else {
      createMutation.mutate();
    }
  };

  return (
    <Layout onNewClick={() => handleOpenModal()}>
      {/* Grid layout matching t.tsx sources exactly */}
      <div className="h-full overflow-y-auto p-4 md:p-10 custom-scrollbar grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-x-4 md:gap-y-4 content-start">
        {allSourcesWithGroupInfo.map((source) => (
          <div
            key={source.id}
            className="theme-surface border theme-border rounded-2xl p-4 md:p-5 shadow-sm hover:shadow-md transition-all relative group flex flex-col justify-between min-h-[120px] md:h-[130px] cursor-pointer"
            onClick={() => handleOpenModal(source)}
          >
            {/* Status indicator - top right corner */}
            {source.status && (
              <div
                className="absolute top-3 right-3 z-10"
                title={source.status === 'active' ? '正常' : '不可访问'}
              >
                <div className="relative w-3 h-3">
                  {/* Breathing outer ring */}
                  <div
                    className={`absolute inset-0 rounded-full ${
                      source.status === 'active'
                        ? 'bg-green-400/40'
                        : 'bg-rose-400/40'
                    }`}
                    style={{
                      animation: 'breathing 2s ease-in-out infinite',
                    }}
                  />
                  {/* Inner dot */}
                  <div
                    className={`relative w-3 h-3 rounded-full ${
                      source.status === 'active'
                        ? 'bg-green-500'
                        : 'bg-rose-500'
                    }`}
                  />
                </div>
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h4 className="font-bold theme-text text-xs md:text-sm truncate mb-1">
                {source.title}
              </h4>
              <p className="text-[10px] md:text-xs theme-text-muted line-clamp-2 leading-snug">
                {source.desc || '暂无描述信息'}
              </p>
            </div>
            <div className="mt-2 flex items-center justify-between shrink-0">
              <span className="text-[9px] font-black theme-text-muted uppercase theme-accent-bg theme-on-accent px-1.5 py-0.5 rounded truncate max-w-[80px]">
                {source.groupName}
              </span>
              <div className="flex items-center gap-2">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="theme-text-muted theme-accent-text-hover transition-colors shrink-0"
                  title="打开订阅源链接"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink size={12} />
                </a>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSource(source.id);
                  }}
                  className="text-rose-500 hover:text-rose-600 transition-colors flex-shrink-0"
                  title="删除订阅源"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          </div>
        ))}

        {/* Add new button */}
        <button
          onClick={() => handleOpenModal()}
          className="border-2 border-dashed theme-border rounded-2xl flex flex-col items-center justify-center theme-text-muted theme-accent-text-hover theme-surface-hover min-h-[120px] md:h-[130px] transition-all min-w-[44px] min-h-[44px]"
        >
          <Plus size={24} />
          <span className="text-[10px] font-bold mt-2 uppercase">添加源</span>
        </button>
      </div>

      {/* Modal - matching t.tsx source modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingSource?.id ? '编辑源' : '加入新源'}
        onConfirm={handleSaveSource}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-[10px] font-black theme-text-muted uppercase tracking-widest mb-2 ml-1">
              别名
            </label>
            <input
              type="text"
              value={editingSource?.name || ''}
              onChange={(e) =>
                setEditingSource((prev) =>
                  prev ? { ...prev, name: e.target.value } : null
                )
              }
              className="w-full theme-surface theme-text theme-border border rounded-2xl px-5 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 outline-none"
            />
          </div>
          <div>
            <label className="block text-[10px] font-black theme-text-muted uppercase tracking-widest mb-2 ml-1">
              描述
            </label>
            <textarea
              value={editingSource?.desc || ''}
              onChange={(e) =>
                setEditingSource((prev) =>
                  prev ? { ...prev, desc: e.target.value } : null
                )
              }
              rows={3}
              className="w-full theme-surface theme-text theme-border border rounded-2xl px-5 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 outline-none resize-none"
            />
          </div>
          <div>
            <label className="block text-[10px] font-black theme-text-muted uppercase tracking-widest mb-2 ml-1">
              RSS URL
            </label>
            <div className="relative">
              <LinkIcon
                className="absolute left-4 top-1/2 -translate-y-1/2 theme-text-muted"
                size={16}
              />
              <input
                type="text"
                value={editingSource?.url || ''}
                onChange={(e) =>
                  setEditingSource((prev) =>
                    prev ? { ...prev, url: e.target.value } : null
                  )
                }
                className="w-full theme-surface theme-text theme-border border rounded-2xl pl-11 pr-5 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 outline-none"
              />
            </div>
          </div>
        </div>
      </Modal>
    </Layout>
  );
};

export default SourcesPage;
