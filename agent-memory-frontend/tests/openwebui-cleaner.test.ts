import { describe, expect, it } from 'vitest'
import { parseMemoryImportText } from '@/utils/memoryImport'
import {
  cleanMessages,
  cleanSessionToRecord,
  isSessionObject,
  toIsoTime,
} from '@/utils/openwebuiCleaner'

describe('openwebuiCleaner', () => {
  it('normalizes roles and extracts plain text from string content', () => {
    expect(cleanMessages([
      { role: 'user', content: '  订单需要退货  ' },
      { role: 'assistant', content: '好的，已提交。' },
    ])).toEqual([
      { role: 'user', content: '订单需要退货' },
      { role: 'assistant', content: '好的，已提交。' },
    ])
  })

  it('maps function role to tool and drops unsupported roles', () => {
    expect(cleanMessages([
      { role: 'function', content: '{"query":"x"}' },
      { role: 'internal', content: 'ignored' },
      { role: 'tool', content: 'tool result' },
    ])).toEqual([
      { role: 'tool', content: '{"query":"x"}' },
      { role: 'tool', content: 'tool result' },
    ])
  })

  it('extracts text parts from array content and skips thinking/tool_calls', () => {
    expect(cleanMessages([
      {
        role: 'assistant',
        content: [
          { type: 'thinking', text: '内部推理，不应写入' },
          { type: 'text', text: '这是答复正文' },
          { type: 'tool_calls', tool_calls: [] },
        ],
      },
    ])).toEqual([
      { role: 'assistant', content: '这是答复正文' },
    ])
  })

  it('supports ChatGPT content_type + parts format', () => {
    expect(cleanMessages([
      { role: 'user', content: { content_type: 'text', parts: ['用户说', '第二段'] } },
    ])).toEqual([
      { role: 'user', content: '用户说\n第二段' },
    ])
  })

  it('detects session objects and converts OpenWebUI chat metadata', () => {
    const raw = {
      id: 'chat-1',
      title: '退货流程咨询',
      created_at: 1700000000,
      messages: [
        { role: 'user', content: '你好' },
        { role: 'assistant', content: '你好，请问有什么可以帮忙？' },
      ],
    }
    expect(isSessionObject(raw)).toBe(true)

    const record = cleanSessionToRecord(raw, 0)
    expect(record.messages).toHaveLength(2)
    expect(record.session_summary).toBe('退货流程咨询')
    expect(record.session_source).toBe('openwebui')
    expect(record.session_time).toBe(new Date(1700000000 * 1000).toISOString())
  })

  it('normalizes timestamps for millisecond values', () => {
    expect(toIsoTime(1700000000000)).toBe(new Date(1700000000000).toISOString())
  })

  it('rejects sessions with no usable messages', () => {
    expect(() => cleanSessionToRecord({ title: '空会话', messages: [
      { role: 'assistant', content: [{ type: 'thinking', text: 'x' }] },
    ] }, 0)).toThrow('没有可用消息')
  })
})

describe('parseMemoryImportText JSONL', () => {
  it('parses JSONL session objects into session records', () => {
    const jsonl = [
      JSON.stringify({
        messages: [
          { role: 'user', content: '查询冷链配送时效' },
          { role: 'assistant', content: '北京到上海常温次日达，冷链 48 小时内。' },
        ],
        title: '冷链配送咨询',
        session_time: '2026-08-01T10:00:00+08:00',
      }),
    ].join('\n')

    const records = parseMemoryImportText('sessions.jsonl', jsonl)
    expect(records).toHaveLength(1)
    expect(records[0].messages).toHaveLength(2)
    expect(records[0].session_summary).toBe('冷链配送咨询')
    expect(records[0].session_source).toBe('openwebui')
  })

  it('parses a single session JSON object', () => {
    const records = parseMemoryImportText('session.json', JSON.stringify({
      messages: [{ role: 'user', content: '记忆系统怎么接入' }],
      title: '接入咨询',
    }))
    expect(records).toHaveLength(1)
    expect(records[0].messages?.[0]?.role).toBe('user')
  })

  it('still parses flat JSON record arrays', () => {
    expect(
      parseMemoryImportText('memories.json', JSON.stringify([{ content: '偏好 Python', role: 'user' }])),
    ).toEqual([
      { content: '偏好 Python', role: 'user', scene_id: undefined, agent_id: undefined, task_id: undefined },
    ])
  })

  it('parses the real OpenWebUI export shape (history.messages object + parentId tree)', () => {
    // 结构来自后端真实样例：顶层数组、每项含 title/models/history，
    // 消息在 history.messages（对象，按 id 索引），顺序由 parentId/childrenIds 表达，且可能乱序。
    const openWebUiExport = [{
      title: '智能BOM转换与测试验证-会话1',
      models: ['deepseek-v4-flash'],
      history: {
        currentId: 'm3',
        messages: {
          m2: { id: 'm2', parentId: 'm1', childrenIds: ['m3'], role: 'assistant', content: '好的，TEST-7607。', model: 'deepseek-v4-flash', done: true },
          m1: { id: 'm1', parentId: null, childrenIds: ['m2'], role: 'user', content: '请把 Excel BOM 转为 JSON。' },
          m3: { id: 'm3', parentId: 'm2', childrenIds: [], role: 'user', content: '文件是 MDL-957_BOM_V1.8.xlsx。' },
        },
      },
    }]

    const records = parseMemoryImportText('openwebui-export.json', JSON.stringify(openWebUiExport))
    expect(records).toHaveLength(1)
    // 按 parentId 树序还原线性对话顺序（乱序输入 → 正确顺序输出）
    expect(records[0].messages?.map((message) => [message.role, message.content])).toEqual([
      ['user', '请把 Excel BOM 转为 JSON。'],
      ['assistant', '好的，TEST-7607。'],
      ['user', '文件是 MDL-957_BOM_V1.8.xlsx。'],
    ])
    expect(records[0].session_summary).toBe('智能BOM转换与测试验证-会话1')
    expect(records[0].session_source).toBe('openwebui')
    // 真实样例无时间戳字段，session_time 留空
    expect(records[0].session_time).toBeUndefined()
  })

  it('skips non-conversation metadata files (progress.json / failed.json)', () => {
    // progress.json：测试进度元数据（非数组对象）
    expect(parseMemoryImportText('progress.json', JSON.stringify({
      topic_id: 1,
      topic: '智能BOM转换',
      target_qa: 50,
      completed_qa: 10,
    }))).toEqual([])
    // failed.json：测试失败记录数组（元素无 content/messages）
    expect(parseMemoryImportText('failed.json', JSON.stringify([
      { conversation_id: 'c1', target_rounds: 5, length_type: 'long', error: 'timeout', timestamp: '2026-08-01' },
    ]))).toEqual([])
  })
})
