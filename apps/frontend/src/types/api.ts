export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

export interface Feed {
  id: number;
  title: string;
  url: string;
  desc: string;
  status: string;
}

export interface FeedGroup {
  id: number;
  title: string;
  desc: string;
  feeds: Feed[];
}

export interface FeedBrief {
  id: number;
  groupIds: number[];
  content?: string; // 列表接口不返回，详情接口返回
  pubDate: string;
  groups: FeedGroup[];
  summary?: string; // 概要（二级标题列表）
  ext_info?: Array<{ // 外部搜索结果，列表接口不返回，详情接口返回
    title: string;
    url: string;
    content: string;
    score: number;
  }>;
}

export interface ModelSetting {
  model: string;
  provider: string;
  baseUrl?: string; // Only present for 'other' provider
  apiKeyConfigured: boolean; // Whether the API key is configured
  apiKeyEnvVar: string; // Environment variable name for the API key
}

export interface Setting {
  model: ModelSetting;
}

/** Agent 模式配置检查结果 */
export interface AgentCheckResult {
  ready: boolean;
  missing: string[];
}

export type FeedGroupListResponse = ApiResponse<FeedGroup[]>;
export type FeedGroupDetailResponse = ApiResponse<FeedGroup>;
export type FeedListResponse = ApiResponse<Feed[]>;
export type FeedBriefResponse = ApiResponse<FeedBrief | null>;
export type FeedBriefListResponse = ApiResponse<FeedBrief[]>;
export type SettingResponse = ApiResponse<Setting>;

export interface ModifyGroupPayload {
  title: string;
  desc: string;
  feedIds: number[];
}

export interface ModifyFeedPayload {
  title: string;
  desc: string;
  url: string;
}

export interface ImportFeedsPayload {
  url?: string;
  content?: string;
}

export interface ModifySettingPayload {
  model?: {
    model: string;
    provider: string;
    baseUrl?: string; // Only required for 'other' provider
  };
}

export interface Schedule {
  id: string;
  time: string; // HH:MM format
  focus: string;
  groupIds: number[];
  enabled: boolean;
}

export interface CreateSchedulePayload {
  time: string; // HH:MM format
  focus: string;
  groupIds: number[];
}

export interface UpdateSchedulePayload {
  time?: string; // HH:MM format
  focus?: string;
  groupIds?: number[];
  enabled?: boolean;
}

export type ScheduleListResponse = ApiResponse<Schedule[]>;
export type ScheduleResponse = ApiResponse<Schedule>;

export interface Memory {
  id: number;
  topic: string;
  reasoning: string;
  content: string;
  created_at: string;
}

export type MemoryResponse = ApiResponse<Memory>;
