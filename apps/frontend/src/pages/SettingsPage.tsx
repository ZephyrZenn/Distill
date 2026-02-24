import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  Settings,
  Cpu,
  Globe,
  Database,
  Save,
  Check,
  AlertTriangle,
  ChevronRight,
  Zap,
  Layers,
} from 'lucide-react';
import { api } from '@/api/client';
import { queryKeys } from '@/api/queryKeys';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApiMutation } from '@/hooks/useApiMutation';
import { Layout } from '@/components/Layout';
import { useToast } from '@/context/ToastContext';
import { Select } from '@/components/ui/Select';
import type { Setting } from '@/types/api';

const providerOptions = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'Deepseek' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'other', label: 'Other (OpenAI Compatible)' },
];

type ModelFormState = { modelName: string; provider: string; baseUrl: string };

const toFormState = (m: { model: string; provider: string; baseUrl?: string } | null | undefined): ModelFormState =>
  m
    ? { modelName: m.model || '', provider: m.provider || 'openai', baseUrl: m.baseUrl || '' }
    : { modelName: '', provider: 'openai', baseUrl: '' };

const SettingsPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: setting } = useApiQuery<Setting>(queryKeys.settings, api.getSetting);
  const { showToast } = useToast();

  const [modelConfig, setModelConfig] = useState<ModelFormState>(toFormState(null));
  const [lightweightConfig, setLightweightConfig] = useState<ModelFormState>(toFormState(null));
  const [embeddingConfig, setEmbeddingConfig] = useState<ModelFormState>(toFormState(null));
  const [showSaveToast, setShowSaveToast] = useState(false);

  useEffect(() => {
    if (setting) {
      setModelConfig(toFormState(setting.model));
      setLightweightConfig(toFormState(setting.lightweightModel ?? undefined));
      setEmbeddingConfig(
        setting.embedding
          ? { modelName: setting.embedding.model, provider: setting.embedding.provider, baseUrl: setting.embedding.baseUrl || '' }
          : toFormState(null)
      );
    }
  }, [setting]);

  const saveMutation = useApiMutation(async () => {
    await api.updateSetting({
      model: {
        model: modelConfig.modelName,
        provider: modelConfig.provider,
        baseUrl: modelConfig.provider === 'other' ? modelConfig.baseUrl : undefined,
      },
      lightweightModel:
        lightweightConfig.modelName.trim()
          ? {
              model: lightweightConfig.modelName,
              provider: lightweightConfig.provider,
              baseUrl: lightweightConfig.provider === 'other' ? lightweightConfig.baseUrl : undefined,
            }
          : undefined,
      embedding: {
        model: embeddingConfig.modelName.trim() || 'text-embedding-3-small',
        provider: embeddingConfig.provider,
        baseUrl: embeddingConfig.provider === 'other' ? embeddingConfig.baseUrl : undefined,
      },
    });
  }, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings });
      setShowSaveToast(true);
      setTimeout(() => setShowSaveToast(false), 3000);
      showToast('配置保存成功');
    },
    onError: (error) => {
      showToast(error.message || '保存配置失败', { type: 'error' });
    },
  });

  const handleSaveConfig = () => {
    saveMutation.mutate();
  };

  const inputCls =
    'w-full theme-surface theme-text theme-border border rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-[var(--theme-primary)]/20 outline-none transition-all font-medium min-h-[44px]';
  const labelCls = 'text-[10px] font-black theme-text-muted uppercase tracking-widest';
  const sectionCls = 'rounded-xl theme-surface p-4 border theme-border';

  const renderModelSection = (
    title: string,
    icon: React.ReactNode,
    state: ModelFormState,
    setState: React.Dispatch<React.SetStateAction<ModelFormState>>,
    apiKeyHint?: { configured: boolean; envVar: string },
    description?: string
  ) => (
    <div className={sectionCls}>
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h4 className="text-sm font-bold theme-text">{title}</h4>
      </div>
      {description && (
        <p className="text-xs theme-text-muted mb-3 leading-relaxed">{description}</p>
      )}
      <div className="space-y-3">
        <div>
          <label className={`flex items-center gap-2 mb-2 ml-1 ${labelCls}`}>Model 名称</label>
          <input
            type="text"
            value={state.modelName}
            onChange={(e) => setState((s) => ({ ...s, modelName: e.target.value }))}
            className={inputCls}
            placeholder="如 gpt-4o-mini"
          />
        </div>
        <div>
          <label className={`flex items-center gap-2 mb-2 ml-1 ${labelCls}`}>提供商</label>
          <Select
            value={state.provider}
            onChange={(v) => setState((s) => ({ ...s, provider: typeof v === 'string' ? v : v?.[0] || '' }))}
            options={providerOptions}
          />
        </div>
        {state.provider === 'other' && (
          <div>
            <label className={`flex items-center gap-2 mb-2 ml-1 ${labelCls}`}>Base URL</label>
            <input
              type="text"
              value={state.baseUrl}
              onChange={(e) => setState((s) => ({ ...s, baseUrl: e.target.value }))}
              placeholder="https://your-api.com/v1"
              className="w-full theme-surface theme-text theme-border border rounded-xl px-4 py-3 text-sm font-mono min-h-[44px] outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20"
            />
          </div>
        )}
        {apiKeyHint && !apiKeyHint.configured && (
          <p className="text-xs theme-accent-text flex items-center gap-1">
            <AlertTriangle size={12} />
            请配置环境变量 <code className="theme-accent-bg theme-on-accent px-1 rounded font-mono text-[10px]">{apiKeyHint.envVar}</code>
          </p>
        )}
      </div>
    </div>
  );

  return (
    <Layout>
      <div className="h-full flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 md:p-8">
          <div className="w-full max-w-2xl mx-auto pb-6">
            {/* Header */}
            <div className="flex items-center gap-3 md:gap-4 mb-4 md:mb-6 pb-4 border-b theme-border">
              <div className="w-10 h-10 md:w-12 md:h-12 theme-accent-bg theme-on-accent rounded-xl md:rounded-2xl flex items-center justify-center">
                <Settings size={20} className="md:w-6 md:h-6" />
              </div>
              <div>
                <h3 className="text-lg md:text-xl font-black theme-text tracking-tight">
                  模型配置
                </h3>
              </div>
            </div>

            {/* API Key Warning - 主模型 */}
            {setting && !setting.model.apiKeyConfigured && (
              <div className="mb-4 p-3 md:p-4 theme-accent-bg theme-on-accent border theme-border rounded-xl flex items-start gap-2 md:gap-3">
                <AlertTriangle size={18} className="flex-shrink-0 mt-0.5 opacity-90" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs md:text-sm font-semibold opacity-95">主模型 API Key 未配置</p>
                  <p className="text-[10px] md:text-xs mt-1 opacity-90">
                    请设置环境变量 <code className="opacity-90 px-1.5 py-0.5 rounded font-mono text-[9px] md:text-[10px]" style={{ backgroundColor: 'var(--theme-primary-hover)' }}>{setting.model.apiKeyEnvVar}</code> 以启用 AI 功能。
                  </p>
                </div>
              </div>
            )}

            <div className="space-y-4">
              {renderModelSection(
                '主模型 (Model)',
                <Cpu size={14} className="theme-accent-text" />,
                modelConfig,
                setModelConfig,
                setting ? { configured: setting.model.apiKeyConfigured, envVar: setting.model.apiKeyEnvVar } : undefined,
                '用于简报生成、Agent 主推理等核心能力。'
              )}
              {renderModelSection(
                '轻量模型 (Lightweight)（可选）',
                <Zap size={14} className="theme-accent-text" />,
                lightweightConfig,
                setLightweightConfig,
                setting?.lightweightModel
                  ? { configured: setting.lightweightModel.apiKeyConfigured, envVar: setting.lightweightModel.apiKeyEnvVar }
                  : undefined,
                '用于处理一些轻量任务，如果没有配置，会直接使用主模型。'
              )}
              {renderModelSection(
                'Embedding（可选）',
                <Layers size={14} className="theme-accent-text" />,
                embeddingConfig,
                setEmbeddingConfig,
                setting?.embedding
                  ? { configured: setting.embedding.apiKeyConfigured, envVar: setting.embedding.apiKeyEnvVar }
                  : undefined,
                '用于向量检索与语义相关度计算，Agent 模式依赖此项。'
              )}
            </div>

            {/* Tavily 配置状态：已配置 / 未配置 用主题内状态色区分 */}
            {setting && (
              <div
                className={`mt-4 p-3 rounded-xl border text-sm ${
                  setting.tavilyConfigured ? 'theme-status-success' : 'theme-status-warning'
                }`}
              >
                {setting.tavilyConfigured ? (
                  <span>Tavily（网页搜索）：已配置</span>
                ) : (
                  <span>
                    Tavily（网页搜索）：未配置。Agent 模式需设置环境变量 <code className="opacity-90 px-1.5 py-0.5 rounded font-mono text-xs" style={{ backgroundColor: 'var(--theme-surface)', color: 'var(--theme-status-warning-text)' }}>TAVILY_API_KEY</code> 以启用网络搜索。
                  </span>
                )}
              </div>
            )}

            {/* 高级设置入口 */}
            <div className="mt-6 pt-4 border-t theme-border">
              <button
                type="button"
                onClick={() => navigate('/settings/advanced')}
                className="flex items-center justify-between w-full py-3 px-3 rounded-xl theme-text theme-surface-hover theme-accent-text-hover transition-colors text-sm font-medium"
              >
                <span>高级设置</span>
                <ChevronRight size={18} className="theme-text-muted" />
              </button>
              <p className="text-xs theme-text-muted mt-1 ml-3">限流、上下文与 Agent 循环上限等</p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t theme-border theme-surface backdrop-blur p-4 md:p-6">
          <div className="max-w-2xl mx-auto flex items-center justify-between">
            <div
              className={`flex items-center gap-2 theme-accent-text text-[10px] font-bold transition-all duration-500 ${
                showSaveToast ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-4'
              }`}
            >
              <Check size={12} className="md:w-[14px] md:h-[14px]" /> 保存成功
            </div>
            <button
              onClick={handleSaveConfig}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 theme-btn-primary theme-on-primary px-6 md:px-10 py-3 rounded-xl md:rounded-2xl font-black shadow-lg transition-all active:scale-95 text-xs md:text-sm uppercase tracking-wider min-h-[44px] disabled:opacity-60"
            >
              <Save size={16} className="md:w-[18px] md:h-[18px]" /> 保存
            </button>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default SettingsPage;
