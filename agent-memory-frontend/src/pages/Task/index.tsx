import { useState } from 'react'
import { Button, Form, Input, Modal, Select, Space } from 'antd'
import type { TaskCreatePayload, TaskProgressResult, TaskProgressUpdatePayload } from '@/api/types'
import { completeTask, createTask, getTaskProgress, updateTaskProgress } from '@/api/modules/task'
import { TaskProgressPanel } from '@/components/business/TaskProgressPanel'
import { PageContainer, PageSection } from '@/components/common'
import { useAppStore, useTaskStore } from '@/store'
import { showErrorMessage, showSuccessMessage, showWarningMessage } from '@/utils/feedback'

interface TaskUpdateFormValues {
  status: TaskProgressUpdatePayload['status']
  progress?: string
  completedItems?: string
  pendingItems?: string
}

function splitLines(value?: string) {
  return value?.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

export default function TaskPage() {
  const config = useAppStore((state) => state.config)
  const activeTaskId = useTaskStore((state) => state.activeTaskId)
  const setActiveTaskId = useTaskStore((state) => state.setActiveTaskId)
  const [taskIdInput, setTaskIdInput] = useState(activeTaskId)
  const [progress, setProgress] = useState<TaskProgressResult | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [updateOpen, setUpdateOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [createForm] = Form.useForm<TaskCreatePayload>()
  const [updateForm] = Form.useForm<TaskUpdateFormValues>()

  const queryProgress = async (taskId = taskIdInput) => {
    const normalizedTaskId = taskId.trim()
    if (!normalizedTaskId) {
      showWarningMessage('请先输入 Task ID')
      return
    }

    setLoading(true)
    try {
      const result = await getTaskProgress(normalizedTaskId)
      setProgress(result)
      setTaskIdInput(normalizedTaskId)
      setActiveTaskId(normalizedTaskId)
    } catch (error) {
      showErrorMessage(error, '查询任务进度失败')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (values: TaskCreatePayload) => {
    setLoading(true)
    try {
      const task = await createTask({ ...values, user_id: config.userId, scene_id: values.scene_id || config.sceneId })
      setActiveTaskId(task.task_id)
      setTaskIdInput(task.task_id)
      setCreateOpen(false)
      createForm.resetFields()
      showSuccessMessage(`任务已创建：${task.task_id}`)
      await queryProgress(task.task_id)
    } catch (error) {
      showErrorMessage(error, '创建任务失败')
    } finally {
      setLoading(false)
    }
  }

  const handleComplete = async () => {
    const normalizedTaskId = taskIdInput.trim()
    if (!normalizedTaskId) {
      showWarningMessage('请先输入 Task ID')
      return
    }
    setLoading(true)
    try {
      const result = await completeTask(normalizedTaskId)
      showSuccessMessage(result.ended_at
        ? `任务已完成：${result.task_id}（结束于 ${result.ended_at}）`
        : `任务已完成：${result.task_id}`)
      await queryProgress(normalizedTaskId)
    } catch (error) {
      showErrorMessage(error, '完成任务失败')
    } finally {
      setLoading(false)
    }
  }

  const handleUpdate = async (values: TaskUpdateFormValues) => {
    const normalizedTaskId = taskIdInput.trim()
    if (!normalizedTaskId) return
    setLoading(true)
    try {
      await updateTaskProgress(normalizedTaskId, {
        status: values.status,
        progress: values.progress?.trim() || undefined,
        completed_items: splitLines(values.completedItems),
        pending_items: splitLines(values.pendingItems),
      })
      setUpdateOpen(false)
      updateForm.resetFields()
      showSuccessMessage('任务进度已更新')
      await queryProgress(normalizedTaskId)
    } catch (error) {
      showErrorMessage(error, '更新任务进度失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PageContainer
      title="任务管理"
      description="创建长周期任务、维护执行进度，并将目标、进展和结果沉淀为任务过程记忆。"
      extra={
        <Space>
          <Button type="primary" onClick={() => setCreateOpen(true)}>创建任务</Button>
          <Button onClick={() => setUpdateOpen(true)} disabled={!taskIdInput.trim()}>更新进度</Button>
          <Button
            type="primary"
            ghost
            loading={loading}
            disabled={!taskIdInput.trim()}
            onClick={() => void handleComplete()}
          >
            完成任务
          </Button>
        </Space>
      }
    >
      <PageSection>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            aria-label="Task ID"
            placeholder="输入 Task ID 查询进度"
            value={taskIdInput}
            onChange={(event) => setTaskIdInput(event.target.value)}
            onPressEnter={() => void queryProgress()}
          />
          <Button type="primary" loading={loading} onClick={() => void queryProgress()}>查询进度</Button>
        </Space.Compact>
      </PageSection>
      <TaskProgressPanel progress={progress} />

      <Modal
        title="创建任务"
        open={createOpen}
        okText="创建"
        cancelText="取消"
        confirmLoading={loading}
        onOk={() => createForm.submit()}
        onCancel={() => setCreateOpen(false)}
      >
        <Form form={createForm} layout="vertical" onFinish={(values) => void handleCreate(values)}>
          <Form.Item name="title" label="任务标题" rules={[{ required: true, whitespace: true }]}>
            <Input placeholder="例如：Q3 技术方案编写" />
          </Form.Item>
          <Form.Item name="goal" label="任务目标" rules={[{ required: true, whitespace: true }]}>
            <Input.TextArea rows={3} placeholder="描述任务最终要完成什么" />
          </Form.Item>
          <Form.Item name="scene_id" label="场景 ID" initialValue={config.sceneId}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`更新任务 ${taskIdInput || ''}`}
        open={updateOpen}
        okText="保存"
        cancelText="取消"
        confirmLoading={loading}
        onOk={() => updateForm.submit()}
        onCancel={() => setUpdateOpen(false)}
      >
        <Form form={updateForm} layout="vertical" onFinish={(values) => void handleUpdate(values)}>
          <Form.Item name="status" label="任务状态" rules={[{ required: true }]}>
            <Select options={[
              { label: '待处理', value: 'pending' },
              { label: '进行中', value: 'in_progress' },
              { label: '已完成', value: 'completed' },
            ]} />
          </Form.Item>
          <Form.Item name="progress" label="进展说明">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="completedItems" label="已完成项（每行一项）">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="pendingItems" label="待办项（每行一项）">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  )
}
