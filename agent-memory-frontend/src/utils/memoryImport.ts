import type { DialogueMessage, MemoryImportRecord } from '@/api/types'
import { cleanSessionToRecord, isSessionObject } from '@/utils/openwebuiCleaner'

const supportedRoles = new Set<DialogueMessage['role']>(['user', 'assistant', 'system', 'tool', 'agent'])

function normalizeRecord(value: unknown, index: number): MemoryImportRecord {
  if (typeof value !== 'object' || value === null) {
    throw new Error(`第 ${index + 1} 条记录不是对象`)
  }

  const record = value as Record<string, unknown>
  const optionalString = (key: string) =>
    typeof record[key] === 'string' ? record[key].trim() || undefined : undefined
  const content = optionalString('content')
    ?? optionalString('session_summary')
    ?? optionalString('task_progress')
    ?? optionalString('task_goal')
    ?? optionalString('task_result')
    ?? ''
  if (!content) {
    throw new Error(`第 ${index + 1} 条记录缺少 content`)
  }

  const role = typeof record.role === 'string' ? record.role.trim() : ''
  if (role && !supportedRoles.has(role as DialogueMessage['role'])) {
    throw new Error(`第 ${index + 1} 条记录的 role 不合法`)
  }

  const normalized: MemoryImportRecord = {
    content,
    role: (role as DialogueMessage['role']) || 'user',
    scene_id: optionalString('scene_id'),
    agent_id: optionalString('agent_id'),
    task_id: optionalString('task_id'),
  }

  const extraFields = [
    'session_time',
    'session_source',
    'session_summary',
    'task_goal',
    'task_progress',
    'task_result',
  ] as const
  extraFields.forEach((field) => {
    const value = optionalString(field)
    if (value) normalized[field] = value
  })

  return normalized
}

/** 单个输入元素：会话对象走清洗器，扁平记录走通用归一化。 */
function toRecord(value: unknown, index: number): MemoryImportRecord {
  return isSessionObject(value) ? cleanSessionToRecord(value, index) : normalizeRecord(value, index)
}

function parseCsvRow(line: string) {
  const cells: string[] = []
  let current = ''
  let quoted = false

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index]
    if (character === '"' && quoted && line[index + 1] === '"') {
      current += '"'
      index += 1
    } else if (character === '"') {
      quoted = !quoted
    } else if (character === ',' && !quoted) {
      cells.push(current.trim())
      current = ''
    } else {
      current += character
    }
  }

  cells.push(current.trim())
  return cells
}

function parseCsv(text: string) {
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/).filter((line) => line.trim())
  if (lines.length < 2) {
    throw new Error('CSV 至少需要表头和一条数据')
  }

  const headers = parseCsvRow(lines[0]).map((header) => header.toLowerCase())
  if (!headers.includes('content')) {
    throw new Error('CSV 表头必须包含 content')
  }

  return lines.slice(1).map((line, index) => {
    const cells = parseCsvRow(line)
    const record = Object.fromEntries(headers.map((header, cellIndex) => [header, cells[cellIndex] ?? '']))
    return normalizeRecord(record, index)
  })
}

/** 解析 JSONL（每行一个会话对象或扁平记录）。 */
function parseJsonl(text: string) {
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (!lines.length) {
    throw new Error('JSONL 文件为空')
  }

  return lines.map((line, index) => {
    let value: unknown
    try {
      value = JSON.parse(line)
    } catch {
      throw new Error(`第 ${index + 1} 行不是合法的 JSON`)
    }
    return toRecord(value, index)
  })
}

/** 解析 JSON：会话对象数组 / 扁平记录数组 / 含 records 字段的对象 / 单个会话对象。 */
function parseJson(text: string) {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('JSON 文件格式不正确')
  }

  if (Array.isArray(parsed)) {
    if (!parsed.length) return []
    const first = parsed[0]
    // 首元素既非会话对象也非含 content 的记录（如 failed.json 测试失败记录）→ 视为非对话元数据跳过。
    if (!isSessionObject(first)
      && (typeof first !== 'object' || first === null || !('content' in first))) {
      return []
    }
    return parsed.map(toRecord)
  }

  if (typeof parsed === 'object' && parsed !== null) {
    const obj = parsed as { records?: unknown }
    if (Array.isArray(obj.records)) {
      return obj.records.map(toRecord)
    }
    if (isSessionObject(parsed)) {
      return [toRecord(parsed, 0)]
    }
    // 非会话结构的对象（如 progress.json 测试进度元数据）→ 空记录，由调用方按「跳过」处理。
    return []
  }

  throw new Error('JSON 需要是非空数组，或包含非空 records 数组')
}

export function parseMemoryImportText(fileName: string, text: string) {
  const normalizedName = fileName.toLowerCase()

  if (normalizedName.endsWith('.csv')) {
    return parseCsv(text)
  }

  if (normalizedName.endsWith('.jsonl')) {
    return parseJsonl(text)
  }

  if (!normalizedName.endsWith('.json')) {
    throw new Error('仅支持 .json、.jsonl 或 .csv 文件')
  }

  return parseJson(text)
}
