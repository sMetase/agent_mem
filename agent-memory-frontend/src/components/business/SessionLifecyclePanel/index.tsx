import { useState } from 'react'
import { Alert, Button, Card, Descriptions, Space, Tag, Typography } from 'antd'
import { closeSession, createSession } from '@/api/modules/session'
import type { SessionCloseResult } from '@/api/types'
import { useAppStore, useTaskStore } from '@/store'
import { normalizeAppConfig } from '@/utils/config'
import { showErrorMessage, showSuccessMessage, showWarningMessage } from '@/utils/feedback'

/**
 * 会话生命周期面板（主链路第 4 步创建 / 第 10 步关闭）。
 * 写入记忆必须绑定 session_id，本组件负责创建并持久化活动会话。
 */
export function SessionLifecyclePanel() {
  const config = useAppStore((state) => state.config)
  const setConfig = useAppStore((state) => state.setConfig)
  const activeTaskId = useTaskStore((state) => state.activeTaskId)
  const [creating, setCreating] = useState(false)
  const [closing, setClosing] = useState(false)
  const [closeResult, setCloseResult] = useState<SessionCloseResult | null>(null)

  const handleCreate = async () => {
    if (creating || config.sessionId?.trim()) return
    setCreating(true)
    setCloseResult(null)
    try {
      const session = await createSession({
        user_id: config.userId,
        agent_id: config.agentId?.trim() || undefined,
        scene_id: config.sceneId?.trim() || undefined,
        task_id: activeTaskId?.trim() || undefined,
      })
      setConfig(normalizeAppConfig({ ...config, sessionId: session.session_id }))
      showSuccessMessage(`会话已创建：${session.session_id}`)
    } catch (error) {
      showErrorMessage(error, '创建会话失败')
    } finally {
      setCreating(false)
    }
  }

  const handleClose = async () => {
    const sessionId = config.sessionId?.trim()
    if (!sessionId) {
      showWarningMessage('当前没有活动会话')
      return
    }
    if (closing) return
    setClosing(true)
    try {
      const result = await closeSession(sessionId)
      setCloseResult(result)
      setConfig(normalizeAppConfig({ ...config, sessionId: '' }))
      showSuccessMessage('会话已关闭，过程类记忆已完成压缩汇总')
    } catch (error) {
      showErrorMessage(error, '关闭会话失败')
    } finally {
      setClosing(false)
    }
  }

  return (
    <Card variant="borderless" title="会话生命周期（主链路第 4 / 10 步）">
      <Descriptions column={1} size="small" style={{ marginBottom: 12 }}>
        <Descriptions.Item label="当前会话">
          {config.sessionId?.trim() ? (
            <Space>
              <Typography.Text code>{config.sessionId}</Typography.Text>
              <Tag color="processing">进行中</Tag>
            </Space>
          ) : (
            <Tag>无活动会话</Tag>
          )}
        </Descriptions.Item>
        {activeTaskId?.trim() ? (
          <Descriptions.Item label="关联任务">{activeTaskId}</Descriptions.Item>
        ) : null}
      </Descriptions>

      {closeResult ? (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 12 }}
          title={`会话压缩汇总：共 ${closeResult.total_memory_count ?? 0} 条记忆，保留 ${closeResult.kept_count ?? 0} 条，压缩 ${closeResult.compressed_count ?? 0} 条`}
          description={closeResult.summary_text || '本次会话没有可压缩的过程类记忆'}
        />
      ) : null}

      <Space wrap>
        <Button
          type="primary"
          loading={creating}
          disabled={!!config.sessionId?.trim()}
          onClick={() => void handleCreate()}
        >
          创建会话
        </Button>
        <Button
          danger
          loading={closing}
          disabled={!config.sessionId?.trim()}
          onClick={() => void handleClose()}
        >
          关闭会话并压缩
        </Button>
      </Space>
    </Card>
  )
}
