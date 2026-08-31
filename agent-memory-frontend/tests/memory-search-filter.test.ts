import { describe, expect, it } from 'vitest'
import { buildMemorySearchPayload } from '@/pages/Memory/service'
import { buildMemoryTypeFilter, filterMemoriesByType } from '@/utils/memory'

describe('buildMemorySearchPayload', () => {
  it('uses memory search when only a memory type is selected', () => {
    expect(buildMemorySearchPayload({
      keyword: '',
      memoryType: 'task',
      userId: 'user_001',
      rerank: false,
    })).toMatchObject({
      query: '',
      user_id: 'user_001',
      memory_types: ['task_state', 'task'],
      top_k: 50,
    })
  })

  it('keeps different selected types as different backend filters', () => {
    const taskPayload = buildMemorySearchPayload({
      keyword: '',
      memoryType: 'task',
      userId: 'user_001',
      rerank: false,
    })
    const factPayload = buildMemorySearchPayload({
      keyword: '',
      memoryType: 'fact',
      userId: 'user_001',
      rerank: false,
    })

    expect(taskPayload?.memory_types).toEqual(['task_state', 'task'])
    expect(factPayload?.memory_types).toEqual(['fact'])
  })

  it('keeps the backend task_state alias available for the retrieval page', () => {
    expect(buildMemoryTypeFilter('task_state')).toEqual(['task_state', 'task'])
  })

  it('covers every supported type when filtering a complete list locally', () => {
    const memories = [
      { memory_id: 'task-1', content: '', memory_type: 'task_state' },
      { memory_id: 'fact-1', content: '', memory_type: 'fact' },
      { memory_id: 'constraint-1', content: '', memory_type: 'constraint' },
      { memory_id: 'preference-1', content: '', memory_type: 'preference' },
      { memory_id: 'decision-1', content: '', memory_type: 'decision' },
      { memory_id: 'process-1', content: '', memory_type: 'process' },
    ]
    const selectedTypes = ['task', 'fact', 'constraint', 'preference', 'decision', 'process']
    const filteredIds = selectedTypes.flatMap((type) =>
      filterMemoriesByType(memories, buildMemoryTypeFilter(type)).map((memory) => memory.memory_id),
    )

    expect(new Set(filteredIds)).toEqual(new Set(memories.map((memory) => memory.memory_id)))
  })

  it('uses the paginated list when no keyword or type filter is selected', () => {
    expect(buildMemorySearchPayload({
      keyword: ' ',
      memoryType: 'all',
      userId: 'user_001',
      rerank: false,
    })).toBeNull()
  })
})
