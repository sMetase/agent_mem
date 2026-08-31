import {
  ApiOutlined,
  CloudSyncOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  FilterOutlined,
  FundOutlined,
  HistoryOutlined,
  MessageOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SettingOutlined,
  TagsOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'
import { appRoutes } from '@/constants/routes'
import {
  AgentAccessRoutePage,
  AgentManagementRoutePage,
  ContextRoutePage,
  DataSourcesRoutePage,
  IngestionRoutePage,
  MemoryProfileRoutePage,
  MemoryRoutePage,
  ModernPrototypeRoutePage,
  MonitoringRoutePage,
  OverviewRoutePage,
  RetrievalRoutePage,
  SceneManagementRoutePage,
  SettingsRoutePage,
  TaskRoutePage,
} from '@/router/LazyRoutePages'

export interface AppRouteConfig {
  key: keyof typeof appRoutes
  path: string
  label: string
  title: string
  description: string
  icon: ReactNode
  element: ReactNode
  showInMenu?: boolean
}

export const appRouteConfigs: AppRouteConfig[] = [
  {
    key: 'overview',
    path: appRoutes.overview,
    label: '系统总览',
    title: '系统总览',
    description: '查看智能体接入、记忆处理、检索调用和运行质量。',
    icon: <FundOutlined />,
    element: <OverviewRoutePage />,
  },
  {
    key: 'modernPrototype',
    path: appRoutes.modernPrototype,
    label: '视觉现代化原型',
    title: '视觉现代化原型 (2026设计趋势)',
    description: '温暖色调、精致阴影、流畅动效的现代化设计方案预览',
    icon: <FundOutlined />,
    element: <ModernPrototypeRoutePage />,
    showInMenu: false,
  },
  {
    key: 'agentAccess',
    path: appRoutes.agentAccess,
    label: '智能体注册接入',
    title: '智能体注册接入',
    description: '注册业务智能体并保存后端返回的身份凭据。',
    icon: <RobotOutlined />,
    element: <AgentAccessRoutePage />,
    showInMenu: false,
  },
  {
    key: 'agentManagement',
    path: appRoutes.agentManagement,
    label: '智能体管理',
    title: '智能体管理',
    description: '查看当前用户智能体列表，管理启停状态与 API Key。',
    icon: <RobotOutlined />,
    element: <AgentManagementRoutePage />,
    showInMenu: false,
  },
  {
    key: 'dataSources',
    path: appRoutes.dataSources,
    label: '外部数据源管理',
    title: '外部数据源管理',
    description: '管理远程对话数据源（Open-Web-UI / 外部智能体），供远程 API 导入拉取。',
    icon: <CloudSyncOutlined />,
    element: <DataSourcesRoutePage />,
    showInMenu: false,
  },
  {
    key: 'sceneManagement',
    path: appRoutes.sceneManagement,
    label: '场景标识配置',
    title: '场景标识配置',
    description: '创建用于隔离智能体、任务和记忆数据的业务场景。',
    icon: <TagsOutlined />,
    element: <SceneManagementRoutePage />,
    showInMenu: false,
  },
  {
    key: 'ingestion',
    path: appRoutes.ingestion,
    label: '记忆数据导入',
    title: '智能体接入与数据写入',
    description: '导入对话记录、历史会话摘要和任务过程数据。',
    icon: <CloudUploadOutlined />,
    element: <IngestionRoutePage />,
  },
  {
    key: 'task',
    path: appRoutes.task,
    label: '任务过程管理',
    title: '任务过程管理',
    description: '创建任务、维护执行进度，并关联任务过程记忆。',
    icon: <UnorderedListOutlined />,
    element: <TaskRoutePage />,
  },
  {
    key: 'memory',
    path: appRoutes.memory,
    label: '多层记忆管理',
    title: '多层记忆管理',
    description: '按用户、类型和场景维护多层记忆数据。',
    icon: <DatabaseOutlined />,
    element: <MemoryRoutePage />,
  },
  {
    key: 'userMemory',
    path: appRoutes.userMemory,
    label: '用户级记忆',
    title: '用户级记忆',
    description: '管理用户偏好、稳定事实和长期约束。',
    icon: <UserOutlined />,
    element: <MemoryRoutePage />,
    showInMenu: false,
  },
  {
    key: 'sessionMemory',
    path: appRoutes.sessionMemory,
    label: '会话级记忆',
    title: '会话级记忆',
    description: '按 Session ID 查看历史会话摘要和上下文。',
    icon: <MessageOutlined />,
    element: <MemoryRoutePage />,
    showInMenu: false,
  },
  {
    key: 'taskMemory',
    path: appRoutes.taskMemory,
    label: '任务级记忆',
    title: '任务级记忆',
    description: '按 Task ID 管理任务目标、进展和执行结果。',
    icon: <UnorderedListOutlined />,
    element: <MemoryRoutePage />,
    showInMenu: false,
  },
  {
    key: 'agentMemory',
    path: appRoutes.agentMemory,
    label: '智能体级记忆',
    title: '智能体级记忆',
    description: '按 Agent ID 管理智能体能力、流程与状态经验。',
    icon: <RobotOutlined />,
    element: <MemoryRoutePage />,
    showInMenu: false,
  },
  {
    key: 'memoryProfile',
    path: appRoutes.memoryProfile,
    label: '记忆画像',
    title: '记忆画像',
    description: '聚合用户偏好与事实记忆生成用户画像报告（L3）。',
    icon: <UserOutlined />,
    element: <MemoryProfileRoutePage />,
  },
  {
    key: 'retrieval',
    path: appRoutes.retrieval,
    label: '多信号融合检索',
    title: '多信号融合记忆检索',
    description: 'hybrid 检索（语义 + 关键词 RRF 融合），按类型与状态过滤返回相关记忆。',
    icon: <FilterOutlined />,
    element: <RetrievalRoutePage />,
  },
  {
    key: 'context',
    path: appRoutes.context,
    label: '记忆上下文返回',
    title: '记忆上下文返回',
    description: '预览结构化 JSON 与可注入智能体的文本上下文片段。',
    icon: <FileSearchOutlined />,
    element: <ContextRoutePage />,
  },
  {
    key: 'monitoring',
    path: appRoutes.monitoring,
    label: '接口与监控',
    title: '接口与运行监控',
    description: '检查服务连通性、接口状态和最近告警。',
    icon: <FundOutlined />,
    element: <MonitoringRoutePage />,
  },
  {
    key: 'healthMonitoring',
    path: appRoutes.healthMonitoring,
    label: '接口健康检查',
    title: '接口健康检查',
    description: '检查后端服务连通性和版本状态。',
    icon: <SafetyCertificateOutlined />,
    element: <MonitoringRoutePage />,
    showInMenu: false,
  },
  {
    key: 'callsMonitoring',
    path: appRoutes.callsMonitoring,
    label: '调用状态监控',
    title: '调用状态监控',
    description: '查看核心接口最近状态和响应耗时。',
    icon: <FundOutlined />,
    element: <MonitoringRoutePage />,
    showInMenu: false,
  },
  {
    key: 'recordsMonitoring',
    path: appRoutes.recordsMonitoring,
    label: '联调记录',
    title: '联调记录',
    description: '集中记录接口问题、修复状态和运行保障项。',
    icon: <HistoryOutlined />,
    element: <MonitoringRoutePage />,
    showInMenu: false,
  },
  {
    key: 'settings',
    path: appRoutes.settings,
    label: '系统设置',
    title: '系统设置',
    description: '管理后端连接地址。',
    icon: <SettingOutlined />,
    element: <SettingsRoutePage />,
  },
  {
    key: 'connectionSettings',
    path: appRoutes.connectionSettings,
    label: '基础连接设置',
    title: '基础连接设置',
    description: '配置当前浏览器连接的后端服务地址。',
    icon: <ApiOutlined />,
    element: <SettingsRoutePage />,
    showInMenu: false,
  },
]

export interface MenuEntryConfig {
  key: string
  path: string
  label: string
  icon: ReactNode
}

export interface MenuSectionConfig {
  key: string
  label: string
  icon: ReactNode
  items: MenuEntryConfig[]
}

function routeItem(key: string, path: string, label: string, icon: ReactNode): MenuEntryConfig {
  return { key, path, label, icon }
}

export const menuSectionConfigs: MenuSectionConfig[] = [
  {
    key: 'section:access',
    label: '1. 智能体接入与记忆数据写入',
    icon: <CloudUploadOutlined />,
    items: [
      routeItem('access:agent', appRoutes.agentAccess, '智能体注册接入', <RobotOutlined />),
      routeItem('access:agentManagement', appRoutes.agentManagement, '智能体管理', <RobotOutlined />),
      routeItem('access:dataSources', appRoutes.dataSources, '外部数据源管理', <CloudSyncOutlined />),
      routeItem('access:scene', appRoutes.sceneManagement, '场景标识配置', <TagsOutlined />),
      routeItem('access:ingestion', appRoutes.ingestion, '记忆数据导入', <CloudUploadOutlined />),
    ],
  },
  {
    key: 'section:memory',
    label: '2. 多层记忆管理',
    icon: <DatabaseOutlined />,
    items: [
      routeItem('memory:user', appRoutes.userMemory, '用户级记忆', <UserOutlined />),
      routeItem('memory:session', appRoutes.sessionMemory, '会话级记忆', <MessageOutlined />),
      routeItem('memory:task', appRoutes.taskMemory, '任务级记忆', <UnorderedListOutlined />),
      routeItem('memory:agent', appRoutes.agentMemory, '智能体级记忆', <RobotOutlined />),
      routeItem('memory:profile', appRoutes.memoryProfile, '记忆画像', <UserOutlined />),
    ],
  },
  {
    key: 'section:retrieval',
    label: '3. 记忆检索',
    icon: <SearchOutlined />,
    items: [
      routeItem('retrieval:main', appRoutes.retrieval, '多信号融合检索', <SearchOutlined />),
    ],
  },
  {
    key: 'section:context',
    label: '4. 记忆上下文返回',
    icon: <FileSearchOutlined />,
    items: [
      routeItem('context:main', appRoutes.context, '记忆上下文返回', <FileSearchOutlined />),
    ],
  },
  {
    key: 'section:monitoring',
    label: '5. 接口与监控',
    icon: <ApiOutlined />,
    items: [
      routeItem('monitoring:health', appRoutes.healthMonitoring, '接口健康检查', <SafetyCertificateOutlined />),
      routeItem('monitoring:calls', appRoutes.callsMonitoring, '调用状态监控', <FundOutlined />),
      routeItem('monitoring:records', appRoutes.recordsMonitoring, '联调记录', <HistoryOutlined />),
    ],
  },
  {
    key: 'section:settings',
    label: '6. 系统设置',
    icon: <SettingOutlined />,
    items: [
      routeItem('settings:connection', appRoutes.connectionSettings, '基础连接设置', <ApiOutlined />),
    ],
  },
]

export function findRouteConfig(pathname: string) {
  return appRouteConfigs.find((route) => route.path === pathname)
}
