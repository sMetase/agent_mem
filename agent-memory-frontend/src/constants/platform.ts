/** 智能体接入平台配置：字段定义依据《智能体接入接口.pdf》（梁闯提供）。 */

export type AgentPlatform =
  | 'dify'
  | 'openwebui'
  | 'aliyun_ims'
  | 'zhipu'

export type CollectionMode = 'manual' | 'scheduled'

export type ScheduleFrequency = 'hourly' | 'daily' | 'custom'

export interface PlatformField {
  /** 字段名（表单 key） */
  name: string
  /** 展示标签 */
  label: string
  /** 占位提示 */
  placeholder?: string
  /** 是否必填 */
  required?: boolean
  /** 是否是密码/密钥类型 */
  secret?: boolean
}

export interface PlatformMeta {
  value: AgentPlatform
  label: string
  description: string
  /** 该平台专属字段，选中平台后表单动态切换 */
  fields: PlatformField[]
  /** 拉取对话的接口说明 */
  apiNote: string
}

export const agentPlatformOptions: PlatformMeta[] = [
  {
    value: 'dify',
    label: 'Dify',
    description: '通过 Dify HTTP API 拉取会话消息列表。',
    fields: [
      { name: 'apiKey', label: 'API Key', placeholder: 'Dify 应用的 API 密钥', required: true, secret: true },
      { name: 'apiBaseUrl', label: '接口地址', placeholder: 'https://api.dify.ai/v1', required: true },
      { name: 'conversationId', label: '会话 ID', placeholder: '会话唯一标识', required: true },
    ],
    apiNote: 'GET /conversations/{conversation_id}/messages（Dify API）',
  },
  {
    value: 'openwebui',
    label: 'Open WebUI',
    description: '通过 Open WebUI HTTP API 拉取聊天消息。',
    fields: [
      { name: 'apiKey', label: 'API Key', placeholder: 'Bearer Token', required: true, secret: true },
      { name: 'apiBaseUrl', label: '接口地址', placeholder: 'https://your-domain.com', required: true },
      { name: 'conversationId', label: '会话 ID', placeholder: '会话唯一标识', required: true },
      { name: 'user', label: '用户标识', placeholder: '可选，按用户过滤' },
    ],
    apiNote: 'GET /api/v1/chats/{id} 或 /api/chats/{id}（Open WebUI API）',
  },
  {
    value: 'aliyun_ims',
    label: '阿里云 IMS',
    description: '通过阿里云智能媒体服务 SDK 拉取历史对话记录。',
    fields: [
      { name: 'accessKeyId', label: 'AccessKey ID', placeholder: '阿里云访问密钥 ID', required: true, secret: true },
      { name: 'accessKeySecret', label: 'AccessKey Secret', placeholder: '阿里云访问密钥 Secret', required: true, secret: true },
      { name: 'userId', label: '用户 ID', placeholder: 'AIChatUserInfo.userId', required: true },
      { name: 'deviceId', label: '设备 ID', placeholder: '可选' },
      { name: 'agentId', label: '智能体 ID', placeholder: 'AIChatAgentInfo.agentId', required: true },
    ],
    apiNote: 'AIChatEngine.queryMessageList(startTime, endTime, pageNumber, pageSize)',
  },
  {
    value: 'zhipu',
    label: '智谱 BigModel',
    description: '通过智谱开放平台 Agent API 拉取会话。',
    fields: [
      { name: 'token', label: '访问令牌', placeholder: 'Authorization: Bearer <token>', required: true, secret: true },
      { name: 'agentId', label: 'Agent ID', placeholder: 'agent_id', required: true },
      { name: 'conversationId', label: '会话 ID', placeholder: 'conversation_id', required: true },
    ],
    apiNote: 'POST /api/v1/agents/conversation（智谱 Agent API）',
  },
]

export const collectionModeOptions: Array<{ label: string; value: CollectionMode }> = [
  { label: '手动采集', value: 'manual' },
  { label: '定时采集', value: 'scheduled' },
]

export const scheduleFrequencyOptions: Array<{ label: string; value: ScheduleFrequency }> = [
  { label: '每小时', value: 'hourly' },
  { label: '每天', value: 'daily' },
  { label: '自定义间隔', value: 'custom' },
]

export function getPlatformMeta(platform?: AgentPlatform) {
  return agentPlatformOptions.find((option) => option.value === platform)
}
