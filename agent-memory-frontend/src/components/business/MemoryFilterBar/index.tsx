import { Button, Card, Flex, Input, Select, Switch, Typography } from 'antd'

import { memoryTypeOptions } from '@/constants/memory'

interface MemoryFilterBarProps {
  keyword: string
  type: string
  rerank: boolean
  loading?: boolean
  onKeywordChange: (value: string) => void
  onTypeChange: (value: string) => void
  onRerankChange: (value: boolean) => void
  onSearch: () => void
}

export function MemoryFilterBar({
  keyword,
  type,
  rerank,
  loading,
  onKeywordChange,
  onTypeChange,
  onRerankChange,
  onSearch,
}: MemoryFilterBarProps) {
  return (
    <Card variant="borderless">
      <Flex wrap gap={12} align="center">
        <Input
          placeholder="按关键字检索记忆"
          value={keyword}
          style={{ flex: '1 1 240px', minWidth: 0 }}
          onChange={(event) => onKeywordChange(event.target.value)}
          onPressEnter={onSearch}
        />
        <Select
          value={type}
          style={{ flex: '0 1 180px', minWidth: 140 }}
          onChange={onTypeChange}
          options={[{ label: '全部类型', value: 'all' }, ...memoryTypeOptions]}
        />
        <Flex align="center" gap={8}>
          <Typography.Text type="secondary">二次排序</Typography.Text>
          <Switch checked={rerank} onChange={onRerankChange} />
        </Flex>
        <Button type="primary" loading={loading} onClick={onSearch}>
          检索
        </Button>
      </Flex>
    </Card>
  )
}
