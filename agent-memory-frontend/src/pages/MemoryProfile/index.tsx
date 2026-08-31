import { PrinterOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Empty, Segmented, Space, Tag, Typography } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { getMemoryProfile } from '@/api/modules/memory'
import type { MemoryProfileResult } from '@/api/types'
import { FeedbackState, PageContainer } from '@/components/common'
import { storageKeys } from '@/constants/storage'
import { ProfileTemplate } from '@/pages/MemoryProfile/templates'
import { profileTemplateMeta, resolveVisual } from '@/pages/MemoryProfile/visual'
import type { ProfileTemplateKind } from '@/pages/MemoryProfile/visual'
import { useAppStore } from '@/store'
import { getErrorMessage } from '@/utils/error'
import { loadJson, saveJson } from '@/utils/localStore'

export default function MemoryProfilePage() {
  const config = useAppStore((state) => state.config)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [profile, setProfile] = useState<MemoryProfileResult | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [templateKind, setTemplateKind] = useState<ProfileTemplateKind>(() => {
    const saved = loadJson<ProfileTemplateKind>(storageKeys.profileTemplate, 'dashboard')
    return profileTemplateMeta[saved] ? saved : 'dashboard'
  })

  const loadProfile = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getMemoryProfile(config.userId)
      setProfile(result)
      setGeneratedAt(new Date().toISOString())
    } catch (loadError) {
      setProfile(null)
      setError(loadError)
    } finally {
      setLoading(false)
    }
  }, [config.userId])

  useEffect(() => {
    void loadProfile()
  }, [loadProfile])

  const handleTemplateChange = (value: string | number) => {
    const nextKind = String(value) as ProfileTemplateKind
    if (!profileTemplateMeta[nextKind]) return
    setTemplateKind(nextKind)
    saveJson(storageKeys.profileTemplate, nextKind)
  }

  const handleExport = () => {
    // 零依赖导出：浏览器打印对话框，可另存为 PDF（打印样式见 index.css）。
    window.print()
  }

  // 多场景画像（personas）为纯文本展示；单场景走可视化模板（visual 缺省时演示兜底）。
  const hasPersonas = Boolean(profile?.personas?.length)
  const visual = profile && !hasPersonas ? resolveVisual(profile.visual) : null
  const generatedAtText = generatedAt ? new Date(generatedAt).toLocaleString('zh-CN') : undefined

  return (
    <PageContainer
      title="记忆画像"
      description="聚合用户偏好与关键事实记忆，生成画像报告，支持可视化、多模板与导出。"
      extra={(
        <Space wrap className="no-print">
          <Tag color="blue">用户：{config.userId}</Tag>
          {!hasPersonas ? (
            <>
              <Segmented
                value={templateKind}
                options={(Object.keys(profileTemplateMeta) as ProfileTemplateKind[]).map((key) => ({
                  label: profileTemplateMeta[key].label,
                  value: key,
                }))}
                onChange={handleTemplateChange}
              />
              <Button type="primary" icon={<PrinterOutlined />} disabled={!profile} onClick={handleExport}>
                导出报告
              </Button>
            </>
          ) : null}
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadProfile()}>刷新画像</Button>
        </Space>
      )}
    >
      {loading ? <FeedbackState status="loading" description="正在聚合偏好与事实生成画像…" /> : null}

      {!loading && error ? (
        <FeedbackState
          status="error"
          title="画像生成失败"
          error={error}
          description={getErrorMessage(error)?.includes('SCENE_REQUIRED')
            ? '当前智能体未绑定业务场景，无法推导画像。请在「智能体注册接入」页为智能体配置所属场景后重试。'
            : undefined}
          action={<Button icon={<ReloadOutlined />} onClick={() => void loadProfile()}>重新加载</Button>}
        />
      ) : null}

      {!loading && !error && profile ? (
        hasPersonas ? (
          <Space orientation="vertical" size={14} style={{ display: 'flex' }}>
            {profile.personas?.map((item) => (
              <Card className="console-card" variant="borderless" key={item.scene_id}>
                <Typography.Title level={5} style={{ marginBottom: 8 }}>场景画像：{item.scene_name}</Typography.Title>
                {item.content ? (
                  <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{item.content}</Typography.Paragraph>
                ) : (
                  <Empty description="暂无画像内容" />
                )}
              </Card>
            ))}
          </Space>
        ) : visual ? (
          <>
            {visual.isDemo ? (
              <Alert
                className="no-print"
                type="warning"
                showIcon
                style={{ marginBottom: 14 }}
                title="演示数据"
                description="后端暂未返回结构化画像数据（雷达图/类型分布/趋势），以下图表为演示数据，待后端按《后端改造清单0824》填充。"
              />
            ) : null}

            <ProfileTemplate
              kind={templateKind}
              profile={profile}
              visual={visual.data}
              userId={config.userId}
              generatedAt={generatedAtText}
            />

            <Card className="console-card no-print" variant="borderless" style={{ marginTop: 14 }}>
              <Descriptions column={{ xs: 1, sm: 2 }} size="small">
                <Descriptions.Item label="所属场景">{profile.scene_id || '-'}</Descriptions.Item>
                <Descriptions.Item label="变更场景数">{profile.changed_scenes ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="生成时间">{generatedAtText || '-'}</Descriptions.Item>
                <Descriptions.Item label="数据来源">
                  {visual.isDemo ? '演示数据（后端未填充）' : '后端画像接口'}
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </>
        ) : null
      ) : null}
    </PageContainer>
  )
}
