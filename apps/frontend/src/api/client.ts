import axios from 'axios';
import type {
  AgentCheckResult,
  ApiResponse,
  FeedBrief,
  FeedBriefListResponse,
  FeedBriefResponse,
  FeedGroup,
  FeedGroupDetailResponse,
  FeedGroupListResponse,
  FeedListResponse,
  Feed,
  ImportFeedsPayload,
  ModifyFeedPayload,
  ModifyGroupPayload,
  ModifySettingPayload,
  Setting,
  SettingResponse,
  Schedule,
  ScheduleListResponse,
  ScheduleResponse,
  CreateSchedulePayload,
  UpdateSchedulePayload,
  Memory,
  MemoryResponse,
  OptionalTopicExpansion,
} from '@/types/api';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api';

const client = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const unwrap = async <T>(promise: Promise<{ data: ApiResponse<T> }> | Promise<{ data: ApiResponse<T | null> }>) => {
  const { data } = await promise;
  if (!data.success) {
    throw new Error(data.message || 'Request failed');
  }
  return data.data as T;
};

export const api = {
  // Briefs
  getLatestBrief: () => unwrap<FeedBrief | null>(client.get<FeedBriefResponse>('/')),
  getBriefs: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const query = params.toString();
    return unwrap<FeedBrief[]>(
      client.get<FeedBriefListResponse>(`/briefs/${query ? `?${query}` : ''}`),
    );
  },
  getBriefDetail: (briefId: number) =>
    unwrap<FeedBrief>(
      client.get<FeedBriefResponse>(`/briefs/${briefId}`),
    ),
  getDefaultBriefs: () => unwrap<FeedBrief[]>(
    client.get<FeedBriefListResponse>('/briefs/default'),
  ),
  generateBrief: (groupIds: number[], focus: string = '', agentMode: boolean = false) =>
    unwrap<{ task_id: string }>(
      client.post<ApiResponse<{ task_id: string }>>('/briefs/generate', {
        group_ids: groupIds,
        focus,
        agent_mode: agentMode,
      })
    ),
  getBriefGenerationStatus: (taskId: string) =>
    unwrap<{
      task_id: string;
      status: 'pending' | 'running' | 'completed' | 'failed';
      logs: Array<{ text: string; time: string }>;
      result?: string;
      error?: string;
    }>(client.get<ApiResponse<{
      task_id: string;
      status: 'pending' | 'running' | 'completed' | 'failed';
      logs: Array<{ text: string; time: string }>;
      result?: string;
      error?: string;
    }>>(`/briefs/generate/${taskId}`)),
  expandOptionalTopic: (briefId: number, topicId: string) =>
    unwrap<OptionalTopicExpansion>(
      client.post<ApiResponse<OptionalTopicExpansion>>(`/briefs/${briefId}/expand/${topicId}`)
    ),

  // Groups
  getGroups: () => unwrap<FeedGroup[]>(client.get<FeedGroupListResponse>('/groups/')),
  getGroupDetail: (groupId: number) =>
    unwrap<FeedGroup>(client.get<FeedGroupDetailResponse>(`/groups/${groupId}`)),
  createGroup: (payload: ModifyGroupPayload) =>
    unwrap<number>(client.post<ApiResponse<number>>('/groups/', payload)),
  updateGroup: (groupId: number, payload: ModifyGroupPayload) =>
    unwrap<void>(client.put<ApiResponse<void>>(`/groups/${groupId}`, payload)),
  deleteGroup: (groupId: number) =>
    unwrap<void>(client.delete<ApiResponse<void>>(`/groups/${groupId}`)),

  // Feeds
  getFeeds: () => unwrap<Feed[]>(client.get<FeedListResponse>('/feeds/')),
  createFeed: (payload: ModifyFeedPayload) =>
    unwrap<void>(client.post<ApiResponse<void>>('/feeds/', payload)),
  updateFeed: (feedId: number, payload: ModifyFeedPayload) =>
    unwrap<void>(client.put<ApiResponse<void>>(`/feeds/${feedId}`, payload)),
  deleteFeed: (feedId: number) => unwrap<void>(client.delete<ApiResponse<void>>(`/feeds/${feedId}`)),
  importFeeds: (payload: ImportFeedsPayload) =>
    unwrap<void>(client.post<ApiResponse<void>>('/feeds/import', payload)),

  // Settings
  getSetting: () => unwrap<Setting>(client.get<SettingResponse>('/setting/')),
  getAgentConfigCheck: () =>
    unwrap<AgentCheckResult>(client.get<ApiResponse<AgentCheckResult>>('/setting/agent-check')),
  updateSetting: (payload: ModifySettingPayload) =>
    unwrap<void>(client.post<ApiResponse<void>>('/setting/', payload)),

  // Schedules
  getSchedules: () => unwrap<Schedule[]>(client.get<ScheduleListResponse>('/schedules/')),
  getSchedule: (scheduleId: string) =>
    unwrap<Schedule>(client.get<ScheduleResponse>(`/schedules/${scheduleId}`)),
  createSchedule: (payload: CreateSchedulePayload) =>
    unwrap<Schedule>(client.post<ScheduleResponse>('/schedules/', payload)),
  updateSchedule: (scheduleId: string, payload: UpdateSchedulePayload) =>
    unwrap<Schedule>(client.put<ScheduleResponse>(`/schedules/${scheduleId}`, payload)),
  deleteSchedule: (scheduleId: string) =>
    unwrap<void>(client.delete<ApiResponse<void>>(`/schedules/${scheduleId}`)),

  // Memory
  getMemory: (memoryId: number) =>
    unwrap<Memory>(client.get<MemoryResponse>(`/memory/${memoryId}`)),
};

export type { Feed, FeedGroup, FeedBrief, Setting, Schedule, Memory };
export { baseURL };
