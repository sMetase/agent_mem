import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  buildWritePayload,
  resolveImportMode,
} from '@/pages/Ingestion/model'
import { parseMemoryImportText } from '@/utils/memoryImport'

const dialogueFixtureName = '批量测试数据-物流场景-20条.json'
const dialogueFixture = readFileSync(
  new URL(`./test-data-set/${dialogueFixtureName}`, import.meta.url),
  'utf8',
)

describe('ingestion mode', () => {
  it('resolves supported modes and falls back to dialogue', () => {
    expect(resolveImportMode('dialogue')).toBe('dialogue')
    expect(resolveImportMode('session')).toBe('session')
    expect(resolveImportMode('task_process')).toBe('task_process')
    expect(resolveImportMode('unknown')).toBe('dialogue')
    expect(resolveImportMode(null)).toBe('dialogue')
  })

  it('maps every record in the tests JSON fixture to a valid dialogue payload', () => {
    const records = parseMemoryImportText(dialogueFixtureName, dialogueFixture)
    const payloads = records.map((record) =>
      buildWritePayload('dialogue', record, 'regression-user', 'default-scene'))

    expect(records).toHaveLength(20)
    expect(payloads).toHaveLength(20)
    payloads.forEach((payload, index) => {
      expect(payload).toEqual({
        user_id: 'regression-user',
        scene_id: records[index].scene_id,
        task_id: records[index].task_id,
        interaction_type: 'dialogue',
        messages: [{
          role: records[index].role,
          content: records[index].content,
        }],
      })
    })
  })

  it('injects the active session id when provided and omits agent_id from the body', () => {
    const payload = buildWritePayload(
      'dialogue',
      { content: '需要退货', role: 'user', scene_id: 'scene-a', task_id: 'task-a' },
      'session-user',
      'default-scene',
      'sess_active_001',
    )

    expect(payload).toEqual({
      user_id: 'session-user',
      scene_id: 'scene-a',
      session_id: 'sess_active_001',
      task_id: 'task-a',
      interaction_type: 'dialogue',
      messages: [{ role: 'user', content: '需要退货' }],
    })
    expect(payload).not.toHaveProperty('agent_id')
  })

  it('preserves session payload mapping and content fallback', () => {
    expect(buildWritePayload('session', {
      content: '会话摘要回退内容',
      role: 'user',
      scene_id: 'session-scene',
      task_id: 'session-task',
      session_time: '2026-07-17T10:00:00+08:00',
    }, 'session-user', 'default-scene')).toEqual({
      user_id: 'session-user',
      scene_id: 'session-scene',
      task_id: 'session-task',
      interaction_type: 'session',
      session_time: '2026-07-17T10:00:00+08:00',
      session_source: 'frontend_file_import',
      session_summary: '会话摘要回退内容',
    })
  })

  it('preserves task-process payload mapping and content fallback', () => {
    expect(buildWritePayload('task_process', {
      content: '任务进展回退内容',
      role: 'user',
      task_id: 'task-001',
      task_goal: '完成回归测试',
      task_result: '测试通过',
    }, 'task-user', 'default-scene')).toEqual({
      user_id: 'task-user',
      scene_id: 'default-scene',
      task_id: 'task-001',
      interaction_type: 'task_process',
      task_goal: '完成回归测试',
      task_progress: '任务进展回退内容',
      task_result: '测试通过',
    })
  })
})
