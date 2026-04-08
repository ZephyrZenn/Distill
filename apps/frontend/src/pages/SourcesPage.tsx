import { useState, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Trash2,
  Edit3,
  ExternalLink,
  Link as LinkIcon,
  FileUp,
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
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [opmlContent, setOpmlContent] = useState('');
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

  const importMutation = useApiMutation(async () => {
    const content = opmlContent.trim();
    if (!content) return;
    await api.importFeeds({ content });
  }, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.feeds });
      setIsImportModalOpen(false);
      setOpmlContent('');
      showToast('OPML 导入成功');
    },
    onError: (error) => {
      showToast(error.message || '导入失败，请检查 OPML 格式', { type: 'error' });
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

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === 'string' ? reader.result : '';
      setOpmlContent(text);
    };
    reader.readAsText(file, 'UTF-8');
    e.target.value = '';
  };

  return (
    <Layout onNewClick={() => handleOpenModal()}>
      <div className="h-full overflow-y-auto p-4 md:p-10 custom-scrollbar flex flex-col">
        {/* 工具栏：导入 OPML */}
        <div className="flex justify-end mb-3 md:mb-4">
          <button
            type="button"
            onClick={() => setIsImportModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold theme-text-muted theme-accent-text-hover theme-surface-hover border theme-border transition-colors min-h-[44px]"
          >
            <FileUp size={18} />
            导入 OPML
          </button>
        </div>
        {/* Grid layout matching t.tsx sources exactly */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 md:gap-x-4 md:gap-y-4 content-start">
        {allSourcesWithGroupInfo.map((source, index) => (
          <div
            key={source.id}
            className={`theme-surface border theme-border rounded-2xl p-5 md:p-6 theme-shadow-ambient card-hover-subtle theme-transition relative group flex flex-col justify-between min-h-[130px] md:h-[140px] cursor-pointer animate-entrance`}
            style={{ animationDelay: `${Math.min(index * 50, 400)}ms` }}
            onClick={() => handleOpenModal(source)}
          >
            {/* Status indicator - top right corner */}
            {source.status && (
              <div
                className="absolute top-4 right-4 z-10"
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
              <h4 className="font-display font-semibold theme-text text-sm md:text-base truncate mb-2">
                {source.title}
              </h4>
              <p className="text-[10px] md:text-xs theme-text-muted line-clamp-2 leading-relaxed font-body">
                {source.desc || '暂无描述信息'}
              </p>
            </div>
            <div className="mt-3 flex items-center justify-between shrink-0">
              <span className="text-[9px] font-black theme-accent-text uppercase tracking-wider theme-accent-subtle px-2 py-1 rounded-md truncate max-w-[90px]">
                {source.groupName}
              </span>
              <div className="flex items-center gap-2">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="theme-text-muted theme-accent-text-hover transition-colors shrink-0 p-1"
                  title="打开订阅源链接"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink size={14} />
                </a>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSource(source.id);
                  }}
                  className="text-rose-400 hover:text-rose-500 transition-colors flex-shrink-0 p-1"
                  title="删除订阅源"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          </div>
        ))}

        {/* Add new button */}
        <button
          onClick={() => handleOpenModal()}
          className="border-2 border-dashed theme-border-subtle rounded-2xl flex flex-col items-center justify-center theme-text-muted theme-accent-text-hover theme-surface-hover min-h-[130px] md:h-[140px] theme-transition card-hover-subtle animate-entrance"
        >
          <Plus size={24} className="mb-2" />
          <span className="text-[10px] font-black uppercase tracking-wider">添加源</span>
        </button>
        </div>
      </div>

      {/* 导入 OPML 弹窗 */}
      <Modal
        isOpen={isImportModalOpen}
        onClose={() => {
          setIsImportModalOpen(false);
          setOpmlContent('');
        }}
        title="导入 OPML"
        onConfirm={() => importMutation.mutate()}
        confirmText="导入"
        confirmDisabled={!opmlContent.trim() || importMutation.isPending}
      >
        <div className="space-y-4">
          <p className="text-sm theme-text-muted">
            上传 OPML 文件或粘贴内容，将批量添加订阅源（与现有源重复的 URL 会跳过）。
          </p>
          <div>
            <label className="block text-[10px] font-black theme-text-muted uppercase tracking-widest mb-2 ml-1">
              选择文件
            </label>
            <label className="flex items-center justify-center gap-2 w-full theme-surface theme-border border border-dashed rounded-2xl px-5 py-4 text-sm theme-text-muted theme-accent-text-hover theme-surface-hover cursor-pointer transition-colors min-h-[52px]">
              <FileUp size={18} />
              <span>点击选择 .opml 文件</span>
              <input
                type="file"
                accept=".opml,application/xml,text/xml"
                className="hidden"
                onChange={handleImportFile}
              />
            </label>
          </div>
          <div>
            <label className="block text-[10px] font-black theme-text-muted uppercase tracking-widest mb-2 ml-1">
              或粘贴 OPML 内容
            </label>
            <textarea
              value={opmlContent}
              onChange={(e) => setOpmlContent(e.target.value)}
              placeholder='<?xml version="1.0"?><opml>...</opml>'
              rows={8}
              className="w-full theme-surface theme-text theme-border border rounded-2xl px-5 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 outline-none resize-y font-mono"
            />
          </div>
        </div>
      </Modal>

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
