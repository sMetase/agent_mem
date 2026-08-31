import { storageKeys } from '@/constants/storage'
import type { ImportMode } from '@/pages/Ingestion/model'

export type IngestionImportStatus = 'completed' | 'partial' | 'failed'

export interface IngestionValidationCounters {
  successCount: number
  failureCount: number
}

export interface IngestionHistoryItem {
  id: string
  userId: string
  agentId?: string
  mode: ImportMode
  source: string
  totalCount: number
  successCount: number
  resultCount: number
  status: IngestionImportStatus
  createdAt: string
}

export interface IngestionActivityState {
  version: 1
  validationByUser: Record<string, IngestionValidationCounters>
  imports: IngestionHistoryItem[]
}

export interface IngestionActivitySummary {
  todaySuccessCount: number
  todayBatchCount: number
  validationSuccessCount: number
  validationAttemptCount: number
  validationPassRate: number | null
}

const maxHistoryItems = 20
const supportedModes = new Set<ImportMode>(['dialogue', 'session', 'task_process'])
const supportedStatuses = new Set<IngestionImportStatus>(['completed', 'partial', 'failed'])

function emptyActivity(): IngestionActivityState {
  return {
    version: 1,
    validationByUser: {},
    imports: [],
  }
}

function getStorage(storage?: Storage) {
  if (storage) return storage
  if (typeof window === 'undefined') return null
  return window.localStorage
}

function asNonNegativeInteger(value: unknown) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : 0
}

function normalizeValidationByUser(value: unknown) {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return {}

  return Object.fromEntries(
    Object.entries(value).flatMap(([userId, counters]) => {
      if (!userId || typeof counters !== 'object' || counters === null) return []
      const record = counters as Record<string, unknown>
      return [[userId, {
        successCount: asNonNegativeInteger(record.successCount),
        failureCount: asNonNegativeInteger(record.failureCount),
      }]]
    }),
  )
}

function normalizeHistoryItem(value: unknown): IngestionHistoryItem | null {
  if (typeof value !== 'object' || value === null) return null
  const item = value as Record<string, unknown>
  if (
    typeof item.id !== 'string'
    || typeof item.userId !== 'string'
    || typeof item.source !== 'string'
    || typeof item.createdAt !== 'string'
    || !supportedModes.has(item.mode as ImportMode)
    || !supportedStatuses.has(item.status as IngestionImportStatus)
    || Number.isNaN(Date.parse(item.createdAt))
  ) {
    return null
  }

  return {
    id: item.id,
    userId: item.userId,
    agentId: typeof item.agentId === 'string' && item.agentId ? item.agentId : undefined,
    mode: item.mode as ImportMode,
    source: item.source,
    totalCount: asNonNegativeInteger(item.totalCount),
    successCount: asNonNegativeInteger(item.successCount),
    resultCount: asNonNegativeInteger(item.resultCount),
    status: item.status as IngestionImportStatus,
    createdAt: item.createdAt,
  }
}

function saveIngestionActivity(state: IngestionActivityState, storage?: Storage) {
  try {
    getStorage(storage)?.setItem(storageKeys.ingestionActivity, JSON.stringify(state))
  } catch {
    // Browser storage can be unavailable or full; the caller still receives
    // the updated in-memory state for the current page session.
  }
  return state
}

export function getIngestionActivity(storage?: Storage): IngestionActivityState {
  try {
    const rawValue = getStorage(storage)?.getItem(storageKeys.ingestionActivity)
    if (!rawValue) return emptyActivity()
    const parsed: unknown = JSON.parse(rawValue)
    if (typeof parsed !== 'object' || parsed === null) return emptyActivity()

    const record = parsed as Record<string, unknown>
    const imports = Array.isArray(record.imports)
      ? record.imports.flatMap((item) => {
          const normalized = normalizeHistoryItem(item)
          return normalized ? [normalized] : []
        }).slice(0, maxHistoryItems)
      : []

    return {
      version: 1,
      validationByUser: normalizeValidationByUser(record.validationByUser),
      imports,
    }
  } catch {
    return emptyActivity()
  }
}

export function recordIngestionValidation(
  state: IngestionActivityState,
  userId: string,
  succeeded: boolean,
  storage?: Storage,
) {
  const current = state.validationByUser[userId] ?? { successCount: 0, failureCount: 0 }
  const next: IngestionActivityState = {
    ...state,
    validationByUser: {
      ...state.validationByUser,
      [userId]: {
        successCount: current.successCount + (succeeded ? 1 : 0),
        failureCount: current.failureCount + (succeeded ? 0 : 1),
      },
    },
  }
  return saveIngestionActivity(next, storage)
}

export function recordIngestionImport(
  state: IngestionActivityState,
  item: IngestionHistoryItem,
  storage?: Storage,
) {
  const next: IngestionActivityState = {
    ...state,
    imports: [item, ...state.imports.filter((historyItem) => historyItem.id !== item.id)]
      .slice(0, maxHistoryItems),
  }
  return saveIngestionActivity(next, storage)
}

function isSameLocalDay(value: string, now: Date) {
  const date = new Date(value)
  return date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate()
}

export function summarizeIngestionActivity(
  state: IngestionActivityState,
  userId: string,
  now = new Date(),
): IngestionActivitySummary {
  const todayImports = state.imports.filter((item) =>
    item.userId === userId && isSameLocalDay(item.createdAt, now))
  const validation = state.validationByUser[userId] ?? { successCount: 0, failureCount: 0 }
  const validationAttemptCount = validation.successCount + validation.failureCount

  return {
    todaySuccessCount: todayImports.reduce((total, item) => total + item.successCount, 0),
    todayBatchCount: todayImports.length,
    validationSuccessCount: validation.successCount,
    validationAttemptCount,
    validationPassRate: validationAttemptCount
      ? (validation.successCount / validationAttemptCount) * 100
      : null,
  }
}
