import type { DialogueMessage, MemoryImportRecord } from '@/api/types'

/**
 * OpenWebUI（及其他含 messages 的对话导出）清洗器：
 * 把原始导出消息转成后端 `POST /memory/write` 契约的消息结构。
 * 纯前端确定性转换，不依赖 LLM / 后端 / 离线脚本。
 *
 * 清洗规则：
 * - role 归一化：user/assistant/system/tool 保留；function 视为 tool；其余丢弃。
 * - content 纯文本提取：字符串直接用；数组 `[{type:"text",text:"..."}]` 提取 text，
 *   thinking/工具调用片段跳过；兼容 ChatGPT content_type + parts 格式。
 * - 过滤空消息、纯工具调用/推理消息。
 * - 会话元数据：title → session_summary、created_at → session_time（ISO 8601）、来源 openwebui。
 */

const roleMap: Record<string, DialogueMessage['role'] | undefined> = {
  user: 'user',
  assistant: 'assistant',
  system: 'system',
  tool: 'tool',
  agent: 'agent',
}

function normalizeRole(role: unknown): DialogueMessage['role'] | undefined {
  if (typeof role !== 'string') return undefined
  const normalized = role.trim().toLowerCase()
  if (normalized === 'function') return 'tool'
  return roleMap[normalized]
}

/** 从消息 content 中提取纯文本；跳过推理/工具调用等无记忆价值片段。 */
function extractText(content: unknown): string {
  if (typeof content === 'string') return content.trim()
  if (typeof content === 'number' || typeof content === 'boolean') return String(content)

  if (Array.isArray(content)) {
    const parts = content.map((part) => {
      if (typeof part === 'string') return part
      if (typeof part !== 'object' || part === null) return ''
      const item = part as Record<string, unknown>
      if (item.type === 'text') return typeof item.text === 'string' ? item.text : ''
      // 推理内容、工具调用参数不作为记忆内容写入
      if (item.type === 'thinking' || item.type === 'tool_calls' || item.type === 'function_call') return ''
      if (item.type === 'input_text' || item.type === 'output_text') return typeof item.text === 'string' ? item.text : ''
      if (Array.isArray(item.parts)) return item.parts.filter((p): p is string => typeof p === 'string').join('\n')
      if (typeof item.text === 'string') return item.text
      return ''
    })
    return parts.join('\n').trim()
  }

  if (typeof content === 'object' && content !== null) {
    const item = content as Record<string, unknown>
    // ChatGPT 导出格式：{content_type: "text", parts: ["..."]}
    if (typeof item.content_type === 'string' && Array.isArray(item.parts)) {
      return item.parts.filter((part): part is string => typeof part === 'string').join('\n').trim()
    }
    if (typeof item.text === 'string') return item.text.trim()
  }

  return ''
}

/** 清洗消息数组：role 归一化 + content 纯文本，过滤空消息与无价值消息。 */
export function cleanMessages(raw: unknown): DialogueMessage[] {
  if (!Array.isArray(raw)) return []
  const result: DialogueMessage[] = []
  for (const item of raw) {
    if (typeof item !== 'object' || item === null) continue
    const record = item as Record<string, unknown>
    const role = normalizeRole(record.role)
    if (!role) continue
    const content = extractText(record.content)
    if (!content) continue
    result.push({ role, content })
  }
  return result
}

/** 时间戳 → ISO 8601：支持秒级/毫秒级数字、ISO 字符串、日期字符串。 */
export function toIsoTime(value: unknown): string | undefined {
  if (value == null || value === '') return undefined
  if (typeof value === 'number' && Number.isFinite(value)) {
    const milliseconds = value > 1e12 ? value : value * 1000
    const date = new Date(milliseconds)
    return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
  }
  if (typeof value === 'string') {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toISOString()
  }
  return undefined
}

/** 提取会话中的原始消息数组（支持 OpenWebUI `history.messages` 对象 / `messages` 对象或数组）。 */
function extractRawMessages(session: Record<string, unknown>): unknown[] {
  const history = session.history
  const historyMessages = (typeof history === 'object' && history !== null)
    ? (history as Record<string, unknown>).messages
    : undefined
  const candidates = [historyMessages, session.messages]
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate
    if (candidate && typeof candidate === 'object') return Object.values(candidate)
  }
  return []
}

/** 按 parentId / childrenIds 树从根开始排序为对话线性顺序（保留分支顺序）。 */
function orderMessages(raw: unknown[]): Array<Record<string, unknown>> {
  const items = raw.filter((item): item is Record<string, unknown> =>
    typeof item === 'object' && item !== null)
  if (!items.length) return []

  const byId = new Map<string, Record<string, unknown>>()
  for (const item of items) {
    if (typeof item.id === 'string' && item.id) byId.set(item.id, item)
  }

  const roots = items.filter((item) => {
    const parent = item.parentId
    return parent == null || parent === '' || !byId.has(String(parent))
  })

  const ordered: Array<Record<string, unknown>> = []
  const visited = new Set<string>()
  const visit = (item: Record<string, unknown>) => {
    const id = typeof item.id === 'string' ? item.id : ''
    if (id && visited.has(id)) return
    visited.add(id)
    ordered.push(item)
    const children = Array.isArray(item.childrenIds) ? item.childrenIds : []
    for (const childId of children) {
      const child = byId.get(String(childId))
      if (child) visit(child)
    }
  }

  for (const root of roots) visit(root)
  // 兜底：未被树遍历覆盖的孤儿消息按原始顺序追加。
  for (const item of items) {
    const id = typeof item.id === 'string' ? item.id : ''
    if (!visited.has(id)) ordered.push(item)
  }
  return ordered
}

/** 判断一个对象是否是「会话对象」（含 messages / history.messages，对象或数组）。 */
export function isSessionObject(value: unknown): boolean {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  const history = record.history
  const historyMessages = (typeof history === 'object' && history !== null)
    ? (history as Record<string, unknown>).messages
    : undefined
  const hasMessages = (candidate: unknown) =>
    Array.isArray(candidate) || (!!candidate && typeof candidate === 'object')
  return hasMessages(record.messages) || hasMessages(historyMessages)
}

/** 把会话对象清洗成导入记录：messages + 会话元数据。 */
export function cleanSessionToRecord(raw: unknown, index: number): MemoryImportRecord {
  const session = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>
  const ordered = orderMessages(extractRawMessages(session))
  const messages = cleanMessages(ordered)
  if (!messages.length) {
    throw new Error(`第 ${index + 1} 个会话没有可用消息（已过滤空消息与工具调用）`)
  }

  const title = typeof session.title === 'string' ? session.title.trim() : ''
  const summary = typeof session.session_summary === 'string' && session.session_summary.trim()
    ? session.session_summary.trim()
    : title || undefined

  const source = typeof session.session_source === 'string' && session.session_source.trim()
    ? session.session_source.trim()
    : 'openwebui'

  return {
    content: messages.map((message) => message.content).join('\n'),
    messages,
    session_summary: summary,
    session_time: toIsoTime(session.session_time ?? session.created_at),
    session_source: source,
  }
}
