import { CopyOutlined, FileTextOutlined, ThunderboltOutlined } from '@ant-design/icons'
import {
  Card,
  Empty,
  Flex,
  Progress,
  Space,
  Tag,
  Typography,
} from 'antd'
import type { MemoryContextResult } from '@/api/types'

const { Text } = Typography

export type ContextResultKind = 'all' | 'json' | 'text' | 'relevance' | 'length'

interface DifferentiatedResultProps {
  kind: ContextResultKind
  result: MemoryContextResult
  isDemo?: boolean
}

function formatJson(json: unknown) {
  try {
    return JSON.stringify(json, null, 2)
  } catch {
    return String(json)
  }
}

/* ---------- 结构化 JSON：可折叠结构树 ---------- */
function JsonTree({ result }: { result: MemoryContextResult }) {
  const fragments = result.fragments ?? []
  return (
    <Space direction="vertical" size={12} style={{ display: 'flex' }}>
      <div className="ctx-json-head">
        <Flex justify="space-between" align="center">
          <Flex gap={8} align="center">
            <FileTextOutlined style={{ color: '#2471cf' }} />
            <Text strong>响应结构</Text>
          </Flex>
          <Flex gap={6}>
            <Tag color="blue">记忆片段 {result.memory_count}</Tag>
            <Tag color="cyan">Token 估算 {result.estimated_tokens ?? '-'}</Tag>
          </Flex>
        </Flex>
      </div>
      {fragments.length ? (
        <Space direction="vertical" size={8} style={{ display: 'flex' }}>
          {fragments.slice(0, 8).map((fragment, index) => (
            <div className="ctx-json-fragment" key={index}>
              <Flex gap={6} align="center" style={{ marginBottom: 4 }}>
                <Tag color="purple">片段 {index + 1}</Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {Object.keys(fragment).join(' / ')}
                </Text>
              </Flex>
              <pre className="ctx-json-pre">{formatJson(fragment)}</pre>
            </div>
          ))}
        </Space>
      ) : null}
      <pre className="ctx-json-pre ctx-json-summary">{formatJson({
        formatted_text: result.formatted_text,
        memory_count: result.memory_count,
        estimated_tokens: result.estimated_tokens,
      })}</pre>
    </Space>
  )
}

/* ---------- 文本片段：可注入文本卡片 ---------- */
function TextCard({ result }: { result: MemoryContextResult }) {
  const segments = (result.formatted_text || '').split(/\n{2,}/).filter(Boolean)
  return (
    <Space direction="vertical" size={12} style={{ display: 'flex' }}>
      <div className="ctx-text-head">
        <Flex justify="space-between" align="center">
          <Flex gap={8} align="center">
            <ThunderboltOutlined style={{ color: '#20a47c' }} />
            <Text strong>可注入 Prompt 文本</Text>
          </Flex>
          <Tag color="green">可直接注入</Tag>
        </Flex>
      </div>
      {segments.length ? (
        <Space direction="vertical" size={8} style={{ display: 'flex' }}>
          {segments.slice(0, 8).map((segment, index) => (
            <div className="ctx-text-segment" key={index}>
              <Flex justify="space-between" align="center" style={{ marginBottom: 4 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>段落 {index + 1}</Text>
                <CopyOutlined style={{ color: '#1677ff', cursor: 'pointer' }} onClick={() => void navigator.clipboard?.writeText(segment)} />
              </Flex>
              <Text style={{ whiteSpace: 'pre-wrap' }}>{segment}</Text>
            </div>
          ))}
        </Space>
      ) : (
        <Empty description="本次没有可返回的上下文文本。" />
      )}
    </Space>
  )
}

/* ---------- 相关性筛选：分级列表 ---------- */
function RelevanceTier({ result }: { result: MemoryContextResult }) {
  // 上下文接口返回单条拼接文本；按行拆分为分级片段用于展示。
  const lines = (result.formatted_text || '').split('\n').map((line) => line.trim()).filter(Boolean)
  if (!lines.length) return <Empty description="本次没有可返回的上下文。" />
  const tiers = lines.slice(0, 9).map((line, index) => {
    if (index < 3) return { level: '高相关', color: 'green', line }
    if (index < 6) return { level: '中相关', color: 'blue', line }
    return { level: '低相关', color: 'default', line }
  })
  return (
    <Space direction="vertical" size={8} style={{ display: 'flex' }}>
      <Flex gap={8}>
        <Text type="secondary">相关度分级</Text>
        <Tag color="green">高</Tag>
        <Tag color="blue">中</Tag>
        <Tag>低</Tag>
      </Flex>
      {tiers.map((tier, index) => (
        <div className={`ctx-tier-item ctx-tier-${tier.color}`} key={index}>
          <Tag color={tier.color}>{tier.level}</Tag>
          <Text ellipsis={{ tooltip: tier.line }} style={{ flex: 1 }}>{tier.line}</Text>
        </div>
      ))}
    </Space>
  )
}

/* ---------- 长度控制：Token 预算 + 压缩对比 ---------- */
function TokenBudget({ result }: { result: MemoryContextResult }) {
  const usedTokens = result.estimated_tokens ?? result.formatted_text.length
  const budget = Math.max(usedTokens, result.formatted_text.length)
  const percent = Math.min(100, Math.round((usedTokens / budget) * 100))
  const textLength = result.formatted_text?.length ?? 0
  return (
    <Space direction="vertical" size={14} style={{ display: 'flex' }}>
      <div className="ctx-budget-bar">
        <Flex justify="space-between" align="center">
          <Text strong>Token 预算使用</Text>
          <Tag color={percent >= 90 ? 'red' : percent >= 70 ? 'orange' : 'green'}>{percent}%</Tag>
        </Flex>
        <Progress percent={percent} strokeColor={percent >= 90 ? '#d04a4a' : percent >= 70 ? '#e49a28' : '#20a47c'} />
        <Flex gap={16} style={{ marginTop: 8 }}>
          <Text type="secondary">已用 {usedTokens} Token</Text>
          <Text type="secondary">预算 {budget} Token</Text>
        </Flex>
      </div>
      <div className="ctx-budget-bar">
        <Flex justify="space-between" align="center">
          <Text strong>长度压缩</Text>
          <Tag color="blue">原始 {textLength} 字符</Tag>
        </Flex>
        <Flex gap={16}>
          <Text type="secondary">返回 {result.memory_count} 条记忆</Text>
          <Text type="secondary">片段已按预算裁剪</Text>
        </Flex>
      </div>
      <pre className="ctx-json-pre ctx-budget-preview">{result.formatted_text}</pre>
    </Space>
  )
}

/* ---------- 全部模式：综合视图 ---------- */
function AllContext({ result }: { result: MemoryContextResult }) {
  return (
    <Space direction="vertical" size={14} style={{ display: 'flex' }}>
      <RowStats result={result} />
      <div className="ctx-all-text">
        <Text strong>上下文内容</Text>
        <Text style={{ whiteSpace: 'pre-wrap', marginTop: 6 }}>{result.formatted_text || '本次没有可返回的上下文。'}</Text>
      </div>
    </Space>
  )
}

function RowStats({ result }: { result: MemoryContextResult }) {
  return (
    <Flex gap={12} wrap>
      <Card className="console-card result-stat" variant="borderless"><Text type="secondary">引用记忆</Text><strong>{result.memory_count}</strong></Card>
      <Card className="console-card result-stat" variant="borderless"><Text type="secondary">预估 Token</Text><strong>{result.estimated_tokens ?? '-'}</strong></Card>
    </Flex>
  )
}

/* ---------- 路由分发 ---------- */
export function DifferentiatedResult({ kind, result, isDemo }: DifferentiatedResultProps) {
  const titles: Record<ContextResultKind, string> = {
    all: '综合上下文',
    json: 'JSON 结构树',
    text: '可注入文本',
    relevance: '相关度分级',
    length: 'Token 预算与压缩',
  }

  const renderBody = () => {
    switch (kind) {
      case 'json':
        return <JsonTree result={result} />
      case 'text':
        return <TextCard result={result} />
      case 'relevance':
        return <RelevanceTier result={result} />
      case 'length':
        return <TokenBudget result={result} />
      case 'all':
        return <AllContext result={result} />
      default:
        return null
    }
  }

  return (
    <Card
      className="console-card"
      title={titles[kind]}
      extra={isDemo ? <Tag color="orange">演示数据</Tag> : <Tag color="green">真实结果</Tag>}
      variant="borderless"
    >
      {renderBody()}
    </Card>
  )
}
