import { describe, expect, it } from 'vitest'
import { demoProfileVisual, needsVisualFallback, resolveVisual } from '@/pages/MemoryProfile/visual'
import type { ProfileVisualData } from '@/api/types'

const partialVisual: ProfileVisualData = {
  memoryTypeDist: [{ type: 'fact', count: 3 }],
  tags: ['BOM'],
}

describe('profile visual fallback', () => {
  it('uses demo data when backend returns no structured visual', () => {
    const resolved = resolveVisual(undefined)
    expect(resolved.isDemo).toBe(true)
    expect(resolved.data.radar?.length).toBeGreaterThan(0)
    expect(resolved.data.tags?.length).toBeGreaterThan(0)
  })

  it('uses demo data when visual fields are all empty', () => {
    expect(needsVisualFallback({ radar: [], memoryTypeDist: [], tags: [], trend: [] })).toBe(true)
    expect(resolveVisual({ radar: [], memoryTypeDist: [] }).isDemo).toBe(true)
  })

  it('keeps backend visual when any field is populated', () => {
    expect(needsVisualFallback(partialVisual)).toBe(false)
    const resolved = resolveVisual(partialVisual)
    expect(resolved.isDemo).toBe(false)
    expect(resolved.data.memoryTypeDist?.[0]?.count).toBe(3)
    expect(resolved.data).toBe(partialVisual)
  })

  it('demo data contains radar, distribution, tags and trend', () => {
    expect(demoProfileVisual.radar?.length).toBeGreaterThan(0)
    expect(demoProfileVisual.memoryTypeDist?.length).toBeGreaterThan(0)
    expect(demoProfileVisual.tags?.length).toBeGreaterThan(0)
    expect(demoProfileVisual.trend?.length).toBeGreaterThan(0)
  })
})
