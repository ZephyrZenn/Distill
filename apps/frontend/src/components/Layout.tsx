import { NavLink, useLocation } from "react-router-dom";
import type { PropsWithChildren } from "react";
import {
  Calendar,
  Zap,
  AlarmClock,
  LayoutGrid,
  List,
  Settings,
  Plus,
  ArrowLeft,
  AlertTriangle,
  X,
  Menu,
  Sun,
  Moon,
} from "lucide-react";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useApiQuery } from "@/hooks/useApiQuery";
import { useTheme } from "@/context/ThemeContext";
import type { Setting } from "@/types/api";

const readViewItems = [
  { to: "/", label: "今日摘要", icon: Calendar },
  { to: "/instant", label: "AI 实时总结", icon: Zap },
];

const systemItems = [
  { to: "/schedules", label: "定时任务", icon: AlarmClock },
  { to: "/groups", label: "分组管理", icon: LayoutGrid },
  { to: "/sources", label: "所有源", icon: List },
];

interface LayoutProps extends PropsWithChildren {
  onNewClick?: () => void;
  showNewButton?: boolean;
  showBackButton?: boolean;
  onBackClick?: () => void;
}

export const Layout = ({
  children,
  onNewClick,
  showNewButton = false,
  showBackButton = false,
  onBackClick,
}: LayoutProps) => {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const activeTab = location.pathname;
  const [dismissedWarning, setDismissedWarning] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

  // Fetch settings to check API key configuration
  const { data: setting } = useApiQuery<Setting>(
    queryKeys.settings,
    api.getSetting,
  );
  const showApiKeyWarning =
    setting && !setting.model.apiKeyConfigured && !dismissedWarning;

  // Close mobile menu when route changes
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  // Prevent body scroll when mobile menu is open
  useEffect(() => {
    if (isMobileMenuOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isMobileMenuOpen]);

  const getPageTitle = () => {
    switch (activeTab) {
      case "/":
        return t("layout.summaryDashboard");
      case "/instant":
        return t("layout.agentSummaryGeneration");
      case "/groups":
        return t("layout.groups");
      case "/sources":
        return t("layout.subscriptionList");
      case "/schedules":
        return t("layout.automationStrategies");
      case "/settings":
        return t("layout.globalSettings");
      default:
        return "Distill";
    }
  };

  const shouldShowNewButton = ["/groups", "/sources", "/schedules"].includes(
    activeTab,
  );

  return (
    <div className="h-screen w-full theme-bg theme-text flex overflow-hidden font-body transition-colors duration-200 bg-noise">
      {/* 移动端遮罩层 */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 backdrop-blur-sm z-40 md:hidden"
          style={{ backgroundColor: "var(--theme-overlay)" }}
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* 侧边栏 - 桌面端固定，移动端抽屉 */}
      <aside
        className={`fixed md:static inset-y-0 left-0 w-64 theme-surface border-r theme-border flex flex-col shrink-0 theme-shadow-elevated z-50 md:z-auto transform transition-transform duration-300 ease-in-out transition-colors duration-200 ${
          isMobileMenuOpen
            ? "translate-x-0"
            : "-translate-x-full md:translate-x-0"
        }`}
      >
        <div className="p-8 flex items-center gap-4 border-b theme-border-subtle">
          <div className="relative">
            <div className="absolute inset-0 theme-accent-subtle rounded-full blur-lg opacity-50" />
            <img
              src="/favicon.svg"
              alt=""
              className="w-12 h-12 shrink-0 relative"
            />
          </div>
          <h1 className="type-page-title theme-text">Distill</h1>
        </div>

        <nav className="flex-1 px-5 py-6 space-y-2 overflow-y-auto custom-scrollbar">
          <div className="px-3 text-[10px] font-semibold theme-text-muted uppercase mb-3 font-body">
            {t("layout.readViews")}
          </div>
          {readViewItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.to;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setIsMobileMenuOpen(false)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl theme-transition min-h-[44px] ${
                  isActive ? "nav-active font-semibold" : "nav-inactive"
                }`}
              >
                <Icon size={18} className="shrink-0" />
                <span className="text-sm font-body-medium">
                  {item.to === "/" ? t("layout.todaySummary") : t("layout.instantSummary")}
                </span>
              </NavLink>
            );
          })}

          <div className="h-6 border-t theme-border-subtle my-4" />
          <div className="px-3 text-[10px] font-semibold theme-text-muted uppercase mb-3 font-body">
            {t("layout.systemManagement")}
          </div>
          {systemItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.to;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setIsMobileMenuOpen(false)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl theme-transition min-h-[44px] ${
                  isActive ? "nav-active font-semibold" : "nav-inactive"
                }`}
              >
                <Icon size={18} className="shrink-0" />
                <span className="text-sm font-body-medium">
                  {item.to === "/schedules"
                    ? t("layout.schedules")
                    : item.to === "/groups"
                      ? t("layout.groups")
                      : t("layout.sources")}
                </span>
              </NavLink>
            );
          })}
        </nav>

        <div className="p-6 border-t theme-border-subtle">
          <NavLink
            to="/settings"
            onClick={() => setIsMobileMenuOpen(false)}
            className={`w-full flex items-center justify-center gap-2 p-3 rounded-2xl theme-transition text-xs font-semibold relative min-h-[44px] ${
              activeTab === "/settings"
                ? "nav-active"
                : showApiKeyWarning
                  ? "nav-active theme-surface-hover"
                  : "nav-inactive theme-accent-text-hover"
            }`}
          >
            {showApiKeyWarning ? (
              <AlertTriangle size={16} className="text-amber-500" />
            ) : (
              <Settings size={16} />
            )}
            <span className="font-body-medium">
              {showApiKeyWarning ? t("layout.settingsRequired") : t("layout.settings")}
            </span>
            {showApiKeyWarning && (
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-amber-500 rounded-full animate-pulse" />
            )}
          </NavLink>
        </div>
      </aside>

      {/* 主内容 */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* API Key Warning Banner */}
        {showApiKeyWarning && (
          <div className="theme-primary-bg theme-on-primary px-3 md:px-4 py-2 md:py-3 flex items-center justify-between shrink-0 z-30">
            <div className="flex items-center gap-2 md:gap-3 min-w-0 flex-1">
              <AlertTriangle
                size={18}
                className="md:w-5 md:h-5 flex-shrink-0"
              />
              <div className="text-xs md:text-sm min-w-0 flex-1">
                <span className="font-semibold">{t("layout.apiKeyMissing")}</span>
                <span className="ml-1 hidden sm:inline">
                  {t("layout.setEnvVar")}{" "}
                  <code
                    className="opacity-90 px-1.5 py-0.5 rounded font-mono text-xs"
                    style={{
                      backgroundColor: "var(--theme-on-primary)",
                      color: "var(--theme-primary)",
                    }}
                  >
                    {setting?.model.apiKeyEnvVar}
                  </code>{" "}
                  {t("layout.enableAiFeature")}
                </span>
                <span className="ml-1 sm:hidden">{t("layout.configureApiKey")}</span>
                <NavLink
                  to="/settings"
                  className="ml-1 md:ml-2 underline underline-offset-2 opacity-90 hover:opacity-100 font-medium whitespace-nowrap"
                >
                  {t("layout.viewSettings")}
                </NavLink>
              </div>
            </div>
            <button
              onClick={() => setDismissedWarning(true)}
              className="p-2 rounded transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0 opacity-90 hover:opacity-100"
              title={t("layout.dismissWarning")}
            >
              <X size={18} />
            </button>
          </div>
        )}

        <header
          className="h-20 backdrop-blur-md border-b theme-border flex items-center justify-between px-4 md:px-8 shrink-0 z-20 theme-transition"
          style={{ backgroundColor: "var(--theme-header-bg)" }}
        >
          <div className="type-page-title theme-text flex items-center gap-2 md:gap-3">
            {/* 移动端汉堡菜单按钮 */}
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="md:hidden p-2 theme-surface-hover rounded-full theme-transition min-w-[44px] min-h-[44px] flex items-center justify-center button-press"
              aria-label={t("layout.openMenu")}
            >
              <Menu size={20} />
            </button>
            {showBackButton && onBackClick && (
              <button
                onClick={onBackClick}
                className="p-2 theme-surface-hover rounded-full theme-transition min-w-[44px] min-h-[44px] flex items-center justify-center button-press"
              >
                <ArrowLeft size={20} />
              </button>
            )}
            <span className="truncate">{getPageTitle()}</span>
          </div>
          <div className="flex items-center gap-2 md:gap-3">
            {shouldShowNewButton && onNewClick && (
              <button
                onClick={onNewClick}
                className="flex items-center gap-1 md:gap-2 theme-btn-primary theme-on-primary px-4 md:px-6 py-2.5 md:py-3 rounded-2xl text-xs md:text-sm font-semibold theme-shadow-ambient theme-transition button-press min-h-[44px]"
              >
                <Plus size={16} className="md:w-[18px] md:h-[18px]" />
                <span className="hidden sm:inline font-body-medium">{t("layout.new")}</span>
              </button>
            )}
            <div className="flex items-center rounded-xl border theme-border overflow-hidden">
              <button
                type="button"
                onClick={() => i18n.changeLanguage("en")}
                className={`px-3 py-2 text-xs font-semibold min-h-[44px] ${
                  i18n.resolvedLanguage === "en"
                    ? "theme-primary-bg theme-on-primary"
                    : "theme-surface-hover theme-text"
                }`}
                title={t("layout.switchToEnglish")}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => i18n.changeLanguage("zh")}
                className={`px-3 py-2 text-xs font-semibold min-h-[44px] ${
                  i18n.resolvedLanguage === "zh"
                    ? "theme-primary-bg theme-on-primary"
                    : "theme-surface-hover theme-text"
                }`}
                title={t("layout.switchToChinese")}
              >
                中文
              </button>
            </div>
            <div className="h-8 w-[1px] mx-1 md:mx-2 hidden sm:block rounded-full theme-border-subtle" />
            <button
              onClick={toggleTheme}
              className="p-2.5 theme-text-muted theme-accent-text-hover theme-surface-hover rounded-xl min-w-[44px] min-h-[44px] flex items-center justify-center theme-transition button-press"
              title={
                theme === "paper"
                  ? t("layout.switchToObsidian")
                  : t("layout.switchToPaper")
              }
              aria-label={t("layout.switchTheme")}
            >
              {theme === "paper" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
          </div>
        </header>

        <div className="flex-1 relative overflow-hidden theme-bg theme-text">
          {children}
        </div>
      </div>
    </div>
  );
};
