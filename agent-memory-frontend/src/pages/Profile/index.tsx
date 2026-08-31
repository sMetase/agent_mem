import { Avatar, Button, Card, Descriptions, Form, Input, Tag, Typography } from 'antd'
import { PageContainer } from '@/components/common'
import { useAuthStore } from '@/store'
import { showSuccessMessage } from '@/utils/feedback'

const { Text, Title } = Typography

interface ProfileFormValues {
  displayName: string
  email?: string
  phone?: string
  department?: string
}

export default function ProfilePage() {
  const user = useAuthStore((state) => state.user)
  const [form] = Form.useForm<ProfileFormValues>()

  if (!user) return null

  const roleLabel: Record<string, string> = {
    admin: '管理员',
    operator: '操作员',
    auditor: '审计员',
  }

  const handleSave = async (values: ProfileFormValues) => {
    void values
    showSuccessMessage('个人资料已更新（演示环境，暂不持久化）')
  }

  return (
    <PageContainer
      title="个人中心"
      description="查看并维护当前登录用户的个人资料与账号信息。"
    >
      <Card className="console-card" variant="borderless" style={{ maxWidth: 860 }}>
        <div className="profile-header">
          <Avatar size={64} style={{ background: '#1677ff', fontSize: 26 }}>
            {(user.displayName || user.username).slice(0, 1).toUpperCase()}
          </Avatar>
          <div>
            <Title level={4} style={{ margin: 0 }}>{user.displayName}</Title>
            <Text type="secondary">@{user.username} · {roleLabel[user.role] ?? user.role}</Text>
            <div style={{ marginTop: 6 }}><Tag color="blue">{user.department}</Tag></div>
          </div>
        </div>

        <Descriptions column={{ xs: 1, sm: 2 }} style={{ marginBottom: 24 }}>
          <Descriptions.Item label="用户 ID">{user.id}</Descriptions.Item>
          <Descriptions.Item label="用户名">{user.username}</Descriptions.Item>
          <Descriptions.Item label="角色">{roleLabel[user.role] ?? user.role}</Descriptions.Item>
          <Descriptions.Item label="所属部门">{user.department}</Descriptions.Item>
        </Descriptions>

        <Title level={5}>编辑资料</Title>
        <Form<ProfileFormValues>
          form={form}
          layout="vertical"
          initialValues={{
            displayName: user.displayName,
            email: user.email,
            phone: user.phone,
            department: user.department,
          }}
          onFinish={(values) => void handleSave(values)}
          style={{ maxWidth: 560 }}
        >
          <Form.Item name="displayName" label="姓名" rules={[{ required: true, whitespace: true, message: '请输入姓名' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '请输入有效邮箱' }]}>
            <Input placeholder="name@example.com" />
          </Form.Item>
          <Form.Item name="phone" label="手机号">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="department" label="所属部门">
            <Input />
          </Form.Item>
          <Button type="primary" htmlType="submit">保存资料</Button>
        </Form>
      </Card>
    </PageContainer>
  )
}
