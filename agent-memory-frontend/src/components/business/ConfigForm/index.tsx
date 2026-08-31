import { useEffect } from 'react'
import { Button, Card, Form, Input } from 'antd'
import type { AppConfig } from '@/api/types'

interface ConfigFormProps {
  initialValues: AppConfig
  onSubmit: (values: AppConfig) => void
  fields?: Array<keyof AppConfig>
  title?: string
}

const allFields: Array<keyof AppConfig> = ['baseUrl', 'userId', 'sceneId', 'agentId', 'apiKey']

export function ConfigForm({
  initialValues,
  onSubmit,
  fields = allFields,
  title = '系统配置',
}: ConfigFormProps) {
  const [form] = Form.useForm<AppConfig>()
  const includes = (field: keyof AppConfig) => fields.includes(field)

  useEffect(() => {
    form.setFieldsValue(initialValues)
  }, [form, initialValues])

  return (
    <Card variant="borderless" title={title}>
      <Form form={form} layout="vertical" initialValues={initialValues} onFinish={onSubmit}>
        {includes('baseUrl') ? (
          <Form.Item
            label="Base URL"
            name="baseUrl"
            rules={[{ required: true, whitespace: true, message: '请输入后端 Base URL' }]}
          >
            <Input placeholder="http://localhost:8000" />
          </Form.Item>
        ) : null}
        {includes('userId') ? (
          <Form.Item
            label="User ID"
            name="userId"
            rules={[{ required: true, whitespace: true, message: '请输入 User ID' }]}
          >
            <Input placeholder="user_001" />
          </Form.Item>
        ) : null}
        {includes('sceneId') ? (
          <Form.Item
            label="Scene ID"
            name="sceneId"
            rules={[{ required: true, whitespace: true, message: '请输入 Scene ID' }]}
          >
            <Input placeholder="memory-console" />
          </Form.Item>
        ) : null}
        {includes('agentId') ? (
          <Form.Item label="Agent ID" name="agentId">
            <Input placeholder="agent_abc" />
          </Form.Item>
        ) : null}
        {includes('apiKey') ? (
          <Form.Item label="API Key" name="apiKey">
            <Input.Password placeholder="mem_xxxx" />
          </Form.Item>
        ) : null}
        <Button type="primary" htmlType="submit">保存配置</Button>
      </Form>
    </Card>
  )
}
