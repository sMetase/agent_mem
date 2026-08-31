import { ApiError } from '@/api/errors'

export interface ApiResponse<T> {
  code: number
  message?: string
  data: T
  error_code?: string
  trace_id?: string
}

export interface AppConfig {
  baseUrl: string
  userId: string
  sceneId: string
  agentId: string
  apiKey: string
  /** 活动会话 ID（主链路第 4 步创建，写记忆/关闭会话复用） */
  sessionId: string
}

export interface HealthResult {
  status?: string
  app?: string
  version?: string
  database?: boolean
}

export interface AdminPageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface AdminApiLogItem {
  log_id: string
  agent_id?: string | null
  api_path: string
  method: string
  response_code: number
  error_code?: string | null
  elapsed_ms?: number | null
  created_at: string
  trace_id?: string | null
}

export interface AdminRetrievalLogItem {
  request_id: string
  agent_id?: string | null
  user_id?: string | null
  query_text?: string | null
  top_k?: number | null
  elapsed_ms?: number | null
  result_count?: number | null
  status?: string | null
  created_at: string
  trace_id?: string | null
}

export interface AdminApiLogParams {
  apiPath?: string
  errorCode?: string
  hours?: number
  page?: number
  pageSize?: number
}

export interface AdminRetrievalLogParams {
  agentId?: string
  hours?: number
  page?: number
  pageSize?: number
}

export interface AdminStatsResult {
  total_memories: number
  total_users: number
  total_agents: number
  total_sessions: number
}

export interface AdminDashboardSummary {
  agent_count: number | null
  scene_count: number | null
  memory_count: number | null
  retrieval_count: number | null
  context_success_rate: number | null
}

export interface AdminDashboardComparison {
  agent_count_rate?: number | null
  scene_count_rate?: number | null
  memory_count_rate?: number | null
  retrieval_count_rate?: number | null
  context_success_rate_change?: number | null
}

export interface AdminMemoryTrendItem {
  date: string
  total: number
  added?: number | null
}

export interface AdminMemoryTypeDistributionItem {
  memory_type: string
  count: number
  ratio: number
}

export interface AdminGenerationSummary {
  generated_count?: number | null
  merged_count?: number | null
  updated_count?: number | null
  discarded_count?: number | null
  conflict_count?: number | null
}

export interface AdminRetrievalSignalDistributionItem {
  signal: string
  count: number
  ratio: number
}

export interface AdminRecentAgentItem {
  agent_id: string
  scene_id?: string | null
  scene_name?: string | null
  status?: string | null
  last_write_at?: string | null
  latest_result?: string | null
}

export interface AdminRecentRetrievalItem {
  retrieval_id: string
  memory_type?: string | null
  summary?: string | null
  content?: string | null
  relevance_score?: number | null
  occurred_at?: string | null
  created_at?: string | null
}

export interface AdminAlertItem {
  message: string
  error_code?: string | null
  trace_id?: string | null
  occurred_at?: string | null
  status?: string | null
  resolved_at?: string | null
}

export interface AdminRecentTaskItem {
  task_id: string
  title?: string | null
  status?: string | null
  updated_at?: string | null
}

export type AdminLatestContext = Record<string, unknown> | string

export interface AdminDashboardResult {
  summary: AdminDashboardSummary
  comparison: AdminDashboardComparison
  memory_trend: AdminMemoryTrendItem[]
  memory_type_distribution: AdminMemoryTypeDistributionItem[]
  generation_summary: AdminGenerationSummary
  retrieval_signal_distribution: AdminRetrievalSignalDistributionItem[]
  recent_agents: AdminRecentAgentItem[]
  recent_retrievals: AdminRecentRetrievalItem[]
  recent_alerts: AdminAlertItem[]
  recent_tasks: AdminRecentTaskItem[]
  latest_context?: AdminLatestContext | null
  generated_at?: string | null
}

export interface AdminDashboardParams {
  hours?: number
  trendDays?: number
}

/** 消息角色：后端合法值为 user/assistant/system/tool/agent。 */
export interface DialogueMessage {
  role: 'user' | 'assistant' | 'system' | 'tool' | 'agent'
  content: string
}

export interface AgentRegisterPayload {
  agent_name: string
  scene_id: string
  permissions: string[]
  llm_model?: string
  llm_api_key?: string
}

export interface AgentRegisterResult {
  agent_id: string
  api_key: string
  api_key_prefix: string
}

export type AgentRotateKeyResult = AgentRegisterResult

export interface AgentInfo {
  agent_id: string
  agent_name?: string
  scene_id?: string
  api_key_prefix?: string
  is_active?: boolean
  permissions?: string[]
  llm_model?: string | null
  created_at?: string
  updated_at?: string | null
}

export type AgentListResult = AdminPageResult<AgentInfo>

export interface AgentUpdatePayload {
  agent_name?: string | null
  is_active?: boolean | null
  permissions?: string[] | null
  llm_model?: string | null
  llm_api_key?: string | null
  extra_meta?: Record<string, unknown>
}

export interface SceneCreatePayload {
  scene_name: string
  description?: string
}

export interface SceneCreateResult {
  scene_id?: string
  scene_name?: string
  description?: string
}

export interface SceneInfo {
  scene_id: string
  scene_name?: string
  description?: string
  is_active?: boolean
  extra_meta?: Record<string, unknown>
  created_at?: string
  updated_at?: string | null
}

export type SceneListResult = AdminPageResult<SceneInfo>

export interface SceneUpdatePayload {
  scene_name?: string | null
  description?: string | null
  is_active?: boolean | null
  extra_meta?: Record<string, unknown>
}

export interface MemoryContextPayload {
  query: string
  user_id: string
  agent_id?: string
  scene_id?: string
  task_id?: string
  session_id?: string
  max_tokens?: number
  group_by_type?: boolean
  top_k?: number
  max_content_length?: number
  memory_types?: string[]
  status?: string[]
  include_preferences?: boolean
  include_facts?: boolean
  include_task_state?: boolean
}

export interface MemoryContextResult {
  formatted_text: string
  memory_count: number
  estimated_tokens?: number
  fragments?: Array<Record<string, unknown>>
}

export interface MemoryWritePayload {
  user_id: string
  scene_id?: string
  task_id?: string
  session_id?: string
  interaction_type?: 'dialogue' | 'session' | 'task_process'
  messages?: DialogueMessage[]
  session_time?: string
  session_source?: string
  session_summary?: string
  task_goal?: string
  task_progress?: string
  task_result?: string
  metadata?: Record<string, unknown>
}

/** 写入响应：只落 L0 异步抽取，不含记忆明细。 */
export interface MemoryWriteResult {
  accepted: boolean
  session_id: string
  l0_count: number
  record_ids: string[]
  /** 仅降级路径返回（Kafka 不可用） */
  degraded?: boolean
}

export interface MemorySearchPayload {
  query: string
  user_id: string
  scene_id?: string
  task_id?: string
  session_id?: string
  agent_id?: string
  memory_types?: string[]
  status?: string[]
  /** 应用层关键词强制后过滤（与 query 的 hybrid 召回是两码事，仅过滤不参与召回） */
  keyword?: string
  top_k?: number
  max_content_length?: number
  rerank?: boolean
  time_start?: string
  time_end?: string
}

export interface MemoryItem {
  memory_id: string
  content: string
  memory_type?: string
  memory_scope?: MemoryLevel
  status?: string
  scene_id?: string
  task_id?: string
  session_id?: string
  summary?: string
  key_points?: string[]
  tags?: string[]
  entities?: string[]
  importance?: number
  confidence?: number
  agent_id?: string
  source_type?: string
  version?: number
  relevance_score?: number
  created_at?: string
  updated_at?: string
}

export interface MemorySearchResult {
  query: string
  results: MemoryItem[]
  total_candidates: number
  elapsed_ms: number
}

export interface MemoryListResult {
  items: MemoryItem[]
  total: number
  page: number
  page_size: number
}

export type MemoryLevel = 'user' | 'session' | 'task' | 'agent'

export interface MemoryLevelDistributionItem {
  level: MemoryLevel
  count: number
  ratio: number
}

export interface MemoryStatsResult {
  total: number
  level_distribution: MemoryLevelDistributionItem[]
  generated_at: string
  classification_version?: string
}

export interface MemoryListParams {
  userId: string
  sceneId?: string
  taskId?: string
  sessionId?: string
  agentId?: string
  memoryType?: string
  timeStart?: string
  timeEnd?: string
  memoryScope?: MemoryLevel
  page?: number
  pageSize?: number
}

/** 单个场景画像项（全部场景返回时用） */
export interface MemoryProfileItem {
  scene_id: string
  scene_name: string
  content: string
}

/** 用户画像报告（L3，消费 L2 场景块）。传 scene_id 返回单场景；不传返回全部场景列表。visual/stats 为 0824 新增：后端填充，缺省时前端演示兜底。 */
export interface MemoryProfileResult {
  persona?: string
  scene_id?: string
  changed_scenes?: number
  personas?: MemoryProfileItem[]
  total?: number
  stats?: {
    total_memories?: number
    active_memories?: number
  }
  visual?: ProfileVisualData
}

/** 外部数据源类型（0824 新增远程导入通道）。 */
export type DataSourceType = 'openwebui' | 'external_agent'

/** 外部接入源配置（后端接口就绪前存 localStorage；定时拉取需后端 worker）。 */
export interface DataSourceConfig {
  id: string
  name: string
  sourceType: DataSourceType
  baseUrl: string
  apiKey?: string
  isActive: boolean
  lastPullAt?: string
  lastResult?: 'success' | 'failed'
  lastPullCount?: number
  createdAt: string
}

export interface ProfileRadarItem {
  dimension: string
  score: number
}

export interface ProfileTypeDistItem {
  type: string
  count: number
}

export interface ProfileTrendItem {
  date: string
  count: number
}

export interface ProfileVisualData {
  radar?: ProfileRadarItem[]
  memoryTypeDist?: ProfileTypeDistItem[]
  tags?: string[]
  trend?: ProfileTrendItem[]
}

export interface MemoryUpdatePayload {
  memory_id: string
  content?: string
  summary?: string
  status?: string
  importance?: number
  confidence?: number
  tags?: string[]
}

export interface TaskCreatePayload {
  user_id: string
  title: string
  goal: string
  scene_id?: string
}

export interface TaskInfo {
  task_id: string
  title?: string
  goal?: string
  progress?: string
  status: TaskStatus
}

export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

export interface TaskProgressResult {
  task_id: string
  status: TaskStatus
  completed_count: number
  pending_count: number
  related_memory_count: number
  progress?: string
  last_activity?: string
}

export interface MemoryImportRecord {
  content: string
  role?: DialogueMessage['role']
  /** 会话导入：原始消息列表（清洗后，role 已归一化、content 为纯文本）。 */
  messages?: DialogueMessage[]
  scene_id?: string
  agent_id?: string
  task_id?: string
  session_time?: string
  session_source?: string
  session_summary?: string
  task_goal?: string
  task_progress?: string
  task_result?: string
}

export interface TaskProgressUpdatePayload {
  status?: TaskStatus
  progress?: string
  completed_items?: string[]
  pending_items?: string[]
}

export interface TaskCompleteResult {
  task_id: string
  status: TaskStatus
  ended_at?: string
}

/** 会话（Session）——主链路第 4 步创建、第 10 步关闭 */
export interface SessionCreatePayload {
  user_id: string
  agent_id?: string
  scene_id?: string
  task_id?: string
  extra_meta?: Record<string, unknown>
}

export interface SessionInfo {
  session_id: string
  user_id: string
  agent_id?: string
  scene_id?: string
  task_id?: string | null
  title?: string
  status?: 'active' | 'closed'
  message_count?: number
  started_at?: string
  ended_at?: string | null
  created_at?: string
}

export type SessionListResult = AdminPageResult<SessionInfo>

export interface SessionUpdatePayload {
  status?: 'active' | 'closed'
  task_id?: string | null
  extra_meta?: Record<string, unknown>
}

export interface SessionCloseResult {
  session_id: string
  status?: string
  total_memory_count?: number
  kept_count?: number
  compressed_count?: number
  summary_text?: string
  ended_at?: string
}

/** 智能体接入采集配置（外部平台对话拉取） */
export interface AgentCollectionConfig {
  platform?: string
  collectionMode?: 'manual' | 'scheduled'
  scheduleFrequency?: 'hourly' | 'daily' | 'custom'
  customIntervalMinutes?: number
  apiKey?: string
  apiBaseUrl?: string
  conversationId?: string
  agentId?: string
  accessKeyId?: string
  accessKeySecret?: string
  token?: string
  user?: string
  userId?: string
  deviceId?: string
}

export interface AdminStatsResult {
  total_memories: number
  total_users: number
  total_agents: number
  total_sessions: number
}

export interface DashboardSummary {
  agent_count?: number | null
  scene_count?: number | null
  memory_count?: number | null
  retrieval_count?: number | null
  context_success_rate?: number | null
}

export interface DashboardComparison {
  agent_count_rate?: number | null
  scene_count_rate?: number | null
  memory_count_rate?: number | null
  retrieval_count_rate?: number | null
  context_success_rate_change?: number | null
}

export interface DashboardGenerationSummary {
  generated_count?: number | null
  merged_count?: number | null
  updated_count?: number | null
  discarded_count?: number | null
  conflict_count?: number | null
}

export interface DashboardMemoryTrendItem {
  date: string
  total: number
  added?: number | null
}

export interface DashboardMemoryTypeItem {
  memory_type: string
  count: number
  ratio: number
}

export interface DashboardRetrievalSignalItem {
  signal: string
  count: number
  ratio: number
}

export interface DashboardRecentAgent {
  agent_id?: string
  scene_id?: string
  scene_name?: string
  status?: string
  last_write_at?: string
  latest_result?: string
}

export interface DashboardRecentRetrieval {
  retrieval_id?: string
  memory_type?: string
  content?: string
  summary?: string
  relevance_score?: number | null
  created_at?: string
  occurred_at?: string
}

export interface DashboardRecentAlert {
  message?: string
  error_code?: string
  trace_id?: string
  occurred_at?: string
}

export interface DashboardRecentTask {
  task_id?: string
  title?: string
  status?: string
  created_at?: string
  updated_at?: string
}

export interface DashboardResult {
  summary?: DashboardSummary
  comparison?: DashboardComparison
  generation_summary?: DashboardGenerationSummary
  memory_trend?: DashboardMemoryTrendItem[]
  memory_type_distribution?: DashboardMemoryTypeItem[]
  retrieval_signal_distribution?: DashboardRetrievalSignalItem[]
  recent_agents?: DashboardRecentAgent[]
  recent_retrievals?: DashboardRecentRetrieval[]
  recent_alerts?: DashboardRecentAlert[]
  recent_tasks?: DashboardRecentTask[]
  latest_context?: Record<string, unknown> | null
  generated_at?: string
}

export function unwrapApiResponse<T>(payload: unknown) {
  if (typeof payload !== 'object' || payload === null || !('code' in payload)) {
    throw new ApiError('接口响应格式不正确', { errorCode: 'INVALID_RESPONSE' })
  }

  const response = payload as Partial<ApiResponse<T>>

  if (typeof response.code !== 'number') {
    throw new ApiError('接口响应格式不正确', { errorCode: 'INVALID_RESPONSE' })
  }

  if (response.code !== 0) {
    throw new ApiError(response.message || '接口请求失败', {
      code: response.code,
      errorCode: response.error_code,
      traceId: response.trace_id,
    })
  }

  if (!('data' in response)) {
    throw new ApiError('接口响应缺少 data 字段', { errorCode: 'INVALID_RESPONSE' })
  }

  return response.data as T
}
