import { describe, expect, it } from 'vitest'
import { storageKeys } from '@/constants/storage'
import {
  getIngestionActivity,
  recordIngestionImport,
  recordIngestionValidation,
  summarizeIngestionActivity,
} from '@/utils/ingestionActivity'
import type { IngestionHistoryItem } from '@/utils/ingestionActivity'

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>()

  get length() {
    return this.values.size
  }

  clear() {
    this.values.clear()
  }

  getItem(key: string) {
    return this.values.get(key) ?? null
  }

  key(index: number) {
    return [...this.values.keys()][index] ?? null
  }

  removeItem(key: string) {
    this.values.delete(key)
  }

  setItem(key: string, value: string) {
    this.values.set(key, value)
  }
}

function historyItem(overrides: Partial<IngestionHistoryItem> = {}): IngestionHistoryItem {
  return {
    id: 'import-1',
    userId: 'user-1',
    mode: 'dialogue',
    source: 'fixture.json',
    totalCount: 20,
    successCount: 20,
    resultCount: 20,
    status: 'completed',
    createdAt: '2026-07-17T10:00:00+08:00',
    ...overrides,
  }
}

describe('ingestion activity', () => {
  it('falls back to an empty state when storage data is invalid', () => {
    const storage = new MemoryStorage()
    storage.setItem(storageKeys.ingestionActivity, '{invalid-json')

    expect(getIngestionActivity(storage)).toEqual({
      version: 1,
      validationByUser: {},
      imports: [],
    })
  })

  it('persists validation counters separately for each user', () => {
    const storage = new MemoryStorage()
    let activity = getIngestionActivity(storage)

    activity = recordIngestionValidation(activity, 'user-1', true, storage)
    activity = recordIngestionValidation(activity, 'user-1', false, storage)
    activity = recordIngestionValidation(activity, 'user-2', true, storage)

    expect(getIngestionActivity(storage).validationByUser).toEqual({
      'user-1': { successCount: 1, failureCount: 1 },
      'user-2': { successCount: 1, failureCount: 0 },
    })
  })

  it('derives current-user daily totals and validation pass rate', () => {
    const storage = new MemoryStorage()
    let activity = getIngestionActivity(storage)
    activity = recordIngestionValidation(activity, 'user-1', true, storage)
    activity = recordIngestionValidation(activity, 'user-1', false, storage)
    activity = recordIngestionImport(activity, historyItem(), storage)
    activity = recordIngestionImport(activity, historyItem({
      id: 'import-2',
      successCount: 3,
      totalCount: 5,
      status: 'partial',
      createdAt: '2026-07-17T11:00:00+08:00',
    }), storage)
    activity = recordIngestionImport(activity, historyItem({
      id: 'other-user',
      userId: 'user-2',
      successCount: 99,
    }), storage)
    activity = recordIngestionImport(activity, historyItem({
      id: 'yesterday',
      successCount: 50,
      createdAt: '2026-07-16T10:00:00+08:00',
    }), storage)

    expect(summarizeIngestionActivity(
      activity,
      'user-1',
      new Date('2026-07-17T18:00:00+08:00'),
    )).toEqual({
      todaySuccessCount: 23,
      todayBatchCount: 2,
      validationSuccessCount: 1,
      validationAttemptCount: 2,
      validationPassRate: 50,
    })
  })

  it('keeps only the twenty most recent import records', () => {
    const storage = new MemoryStorage()
    let activity = getIngestionActivity(storage)

    for (let index = 0; index < 25; index += 1) {
      activity = recordIngestionImport(activity, historyItem({ id: `import-${index}` }), storage)
    }

    expect(activity.imports).toHaveLength(20)
    expect(activity.imports[0].id).toBe('import-24')
    expect(activity.imports[19].id).toBe('import-5')
  })
})
