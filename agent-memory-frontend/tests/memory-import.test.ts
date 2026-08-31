import { describe, expect, it } from 'vitest'
import { parseMemoryImportText } from '@/utils/memoryImport'

describe('parseMemoryImportText', () => {
  it('parses a JSON record array and applies the default role', () => {
    expect(
      parseMemoryImportText('memories.json', JSON.stringify([
        { content: '用户偏好 Python', scene_id: 'chat' },
      ])),
    ).toEqual([
      { content: '用户偏好 Python', role: 'user', scene_id: 'chat', task_id: undefined },
    ])
  })

  it('parses CSV values with quoted commas', () => {
    expect(
      parseMemoryImportText(
        'memories.csv',
        'content,role,scene_id,task_id\n"喜欢 Python, FastAPI",user,code,task_1',
      ),
    ).toEqual([
      { content: '喜欢 Python, FastAPI', role: 'user', scene_id: 'code', task_id: 'task_1' },
    ])
  })

  it('rejects invalid roles', () => {
    expect(() =>
      parseMemoryImportText('memories.json', JSON.stringify([{ content: '内容', role: 'admin' }])),
    ).toThrow('role 不合法')
  })

  it('rejects unsupported file types', () => {
    expect(() => parseMemoryImportText('memories.txt', 'hello')).toThrow('仅支持')
  })
})
