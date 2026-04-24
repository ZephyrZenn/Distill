import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Gauge, LayoutList, Bot, Save, Check, ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useApiQuery } from "@/hooks/useApiQuery";
import { useApiMutation } from "@/hooks/useApiMutation";
import { Layout } from "@/components/Layout";
import { Checkbox } from "@/components/ui/Checkbox";
import { useToast } from "@/context/ToastContext";
import type {
  AgentLimitsSetting,
  ContextSetting,
  RateLimitSetting,
  Setting,
} from "@/types/api";

const DEFAULT_RATE_LIMIT: RateLimitSetting = {
  requestsPerMinute: 60,
  burstSize: 10,
  enableRateLimit: true,
  maxRetries: 3,
  baseDelay: 1,
  maxDelay: 60,
  enableRetry: true,
};

const DEFAULT_CONTEXT: ContextSetting = {
  maxTokens: 128000,
  compressThreshold: 0.8,
};

const DEFAULT_AGENT_LIMITS: AgentLimitsSetting = {
  maxIterations: 10,
  maxToolCalls: 50,
  maxCurations: 8,
  maxPlanReviews: 3,
  maxRefines: 3,
  enableHardLimits: true,
};

const SettingsAdvancedPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: setting } = useApiQuery<Setting>(
    queryKeys.settings,
    api.getSetting,
  );
  const { showToast } = useToast();

  const [advancedConfig, setAdvancedConfig] = useState({
    rateLimit: DEFAULT_RATE_LIMIT,
    context: DEFAULT_CONTEXT,
    agentLimits: DEFAULT_AGENT_LIMITS,
  });
  const [showSaveToast, setShowSaveToast] = useState(false);

  useEffect(() => {
    if (setting) {
      setAdvancedConfig({
        rateLimit: { ...DEFAULT_RATE_LIMIT, ...setting.rateLimit },
        context: { ...DEFAULT_CONTEXT, ...setting.context },
        agentLimits: { ...DEFAULT_AGENT_LIMITS, ...setting.agentLimits },
      });
    }
  }, [setting]);

  const saveMutation = useApiMutation(
    async () => {
      await api.updateSetting({
        rateLimit: advancedConfig.rateLimit,
        context: advancedConfig.context,
        agentLimits: advancedConfig.agentLimits,
      });
    },
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.settings });
        setShowSaveToast(true);
        setTimeout(() => setShowSaveToast(false), 3000);
        showToast(t("settingsAdvanced.saveSuccess"));
      },
      onError: (error) => {
        showToast(error.message || t("settingsAdvanced.saveFailed"), { type: "error" });
      },
    },
  );

  const inputCls =
    "theme-surface theme-text theme-border border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20 text-sm w-full min-w-0";
  const labelCls = "text-xs theme-text-muted mb-1 block";

  return (
    <Layout>
      <div className="h-full flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 md:p-8">
          <div className="w-full max-w-2xl mx-auto">
            {/* Header */}
            <div className="flex items-center gap-3 mb-6">
              <button
                type="button"
                onClick={() => navigate("/settings")}
                className="p-2 rounded-lg theme-text-muted theme-surface-hover theme-accent-text-hover transition-colors"
                aria-label={t("settingsAdvanced.back")}
              >
                <ArrowLeft size={20} />
              </button>
              <div>
                <h1 className="text-lg md:text-xl font-semibold theme-text">
                  {t("settingsAdvanced.title")}
                </h1>
                <p className="theme-text-muted text-xs font-medium">
                  {t("settingsAdvanced.subtitle")}
                </p>
              </div>
            </div>

            <div className="space-y-6 pb-8">
              {/* 限流与重试 */}
              <section className="rounded-xl theme-surface p-4 md:p-5 border theme-border">
                <div className="flex items-center gap-2 mb-4">
                  <Gauge size={16} className="theme-accent-text" />
                  <h2 className="text-sm font-semibold theme-text">
                    {t("settingsAdvanced.rateLimitSection")}
                  </h2>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.requestsPerMinute")}</span>
                    <input
                      type="number"
                      min={1}
                      step={1}
                      value={advancedConfig.rateLimit.requestsPerMinute}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          rateLimit: {
                            ...advancedConfig.rateLimit,
                            requestsPerMinute: Number(e.target.value) || 60,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.burstSize")}</span>
                    <input
                      type="number"
                      min={1}
                      value={advancedConfig.rateLimit.burstSize}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          rateLimit: {
                            ...advancedConfig.rateLimit,
                            burstSize: Number(e.target.value) || 10,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.maxRetries")}</span>
                    <input
                      type="number"
                      min={0}
                      value={advancedConfig.rateLimit.maxRetries}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          rateLimit: {
                            ...advancedConfig.rateLimit,
                            maxRetries: Number(e.target.value) ?? 3,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.baseDelay")}</span>
                    <input
                      type="number"
                      min={0}
                      step={0.1}
                      value={advancedConfig.rateLimit.baseDelay}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          rateLimit: {
                            ...advancedConfig.rateLimit,
                            baseDelay: Number(e.target.value) ?? 1,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.maxDelay")}</span>
                    <input
                      type="number"
                      min={0}
                      value={advancedConfig.rateLimit.maxDelay}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          rateLimit: {
                            ...advancedConfig.rateLimit,
                            maxDelay: Number(e.target.value) ?? 60,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <div className="flex flex-wrap items-end gap-4 sm:col-span-2">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <Checkbox
                        checked={advancedConfig.rateLimit.enableRateLimit}
                        onCheckedChange={(v) =>
                          setAdvancedConfig({
                            ...advancedConfig,
                            rateLimit: {
                              ...advancedConfig.rateLimit,
                              enableRateLimit: v,
                            },
                          })
                        }
                      />
                      <span className="text-sm theme-text">{t("settingsAdvanced.enableRateLimit")}</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <Checkbox
                        checked={advancedConfig.rateLimit.enableRetry}
                        onCheckedChange={(v) =>
                          setAdvancedConfig({
                            ...advancedConfig,
                            rateLimit: {
                              ...advancedConfig.rateLimit,
                              enableRetry: v,
                            },
                          })
                        }
                      />
                      <span className="text-sm theme-text">{t("settingsAdvanced.enableRetry")}</span>
                    </label>
                  </div>
                </div>
              </section>

              {/* 上下文 */}
              <section className="rounded-xl theme-surface p-4 md:p-5 border theme-border">
                <div className="flex items-center gap-2 mb-4">
                  <LayoutList size={16} className="theme-accent-text" />
                  <h2 className="text-sm font-semibold theme-text">{t("settingsAdvanced.contextSection")}</h2>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.maxTokens")}</span>
                    <input
                      type="number"
                      min={1000}
                      value={advancedConfig.context.maxTokens}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          context: {
                            ...advancedConfig.context,
                            maxTokens: Number(e.target.value) || 128000,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.compressThreshold")}</span>
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.1}
                      value={advancedConfig.context.compressThreshold}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          context: {
                            ...advancedConfig.context,
                            compressThreshold: Number(e.target.value) ?? 0.8,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                </div>
              </section>

              {/* Agent 循环上限 */}
              <section className="rounded-xl theme-surface p-4 md:p-5 border theme-border">
                <div className="flex items-center gap-2 mb-4">
                  <Bot size={16} className="theme-accent-text" />
                  <h2 className="text-sm font-semibold theme-text">
                    {t("settingsAdvanced.agentSection")}
                  </h2>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.maxIterations")}</span>
                    <input
                      type="number"
                      min={1}
                      value={advancedConfig.agentLimits.maxIterations}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          agentLimits: {
                            ...advancedConfig.agentLimits,
                            maxIterations: Number(e.target.value) || 10,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.maxToolCalls")}</span>
                    <input
                      type="number"
                      min={1}
                      value={advancedConfig.agentLimits.maxToolCalls}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          agentLimits: {
                            ...advancedConfig.agentLimits,
                            maxToolCalls: Number(e.target.value) || 50,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.maxCurations")}</span>
                    <input
                      type="number"
                      min={1}
                      value={advancedConfig.agentLimits.maxCurations}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          agentLimits: {
                            ...advancedConfig.agentLimits,
                            maxCurations: Number(e.target.value) || 8,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.maxPlanReviews")}</span>
                    <input
                      type="number"
                      min={1}
                      value={advancedConfig.agentLimits.maxPlanReviews}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          agentLimits: {
                            ...advancedConfig.agentLimits,
                            maxPlanReviews: Number(e.target.value) || 3,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className={labelCls}>{t("settingsAdvanced.maxRefines")}</span>
                    <input
                      type="number"
                      min={1}
                      value={advancedConfig.agentLimits.maxRefines}
                      onChange={(e) =>
                        setAdvancedConfig({
                          ...advancedConfig,
                          agentLimits: {
                            ...advancedConfig.agentLimits,
                            maxRefines: Number(e.target.value) || 3,
                          },
                        })
                      }
                      className={inputCls}
                    />
                  </label>
                  <div className="flex items-center sm:col-span-2">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <Checkbox
                        checked={advancedConfig.agentLimits.enableHardLimits}
                        onCheckedChange={(v) =>
                          setAdvancedConfig({
                            ...advancedConfig,
                            agentLimits: {
                              ...advancedConfig.agentLimits,
                              enableHardLimits: v,
                            },
                          })
                        }
                      />
                      <span className="text-sm theme-text">{t("settingsAdvanced.enableHardLimits")}</span>
                    </label>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </div>

        {/* Sticky footer */}
        <div className="shrink-0 border-t theme-border theme-surface backdrop-blur p-4 md:p-6">
          <div className="max-w-2xl mx-auto flex items-center justify-between">
            <div
              className={`flex items-center gap-2 text-emerald-500 text-xs font-semibold transition-all duration-500 ${
                showSaveToast
                  ? "opacity-100 translate-x-0"
                  : "opacity-0 -translate-x-4"
              }`}
            >
              <Check size={14} /> {t("settingsAdvanced.saveSuccess")}
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => navigate("/settings")}
                className="px-4 py-2.5 rounded-xl theme-text theme-surface-hover theme-accent-text-hover font-medium text-sm transition-colors"
              >
                {t("settingsAdvanced.back")}
              </button>
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="flex items-center gap-2 theme-btn-primary theme-on-primary px-6 py-2.5 rounded-xl font-semibold shadow-lg transition-all active:scale-95 text-sm disabled:opacity-60"
              >
                <Save size={16} /> {t("settingsAdvanced.saveButton")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default SettingsAdvancedPage;
