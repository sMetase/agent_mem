import { Navigate, useParams } from 'react-router-dom'
import { appRoutes } from '@/constants/routes'

/**
 * 旧能力 ID → 新路由 的跳转映射。
 * 记忆生成与去重融合（generate 已废弃）相关旧 ID 统一回到多层记忆管理。
 */
const legacyCapabilityRedirects: Record<string, string> = {
  'agent-level-memory': appRoutes.memory,
  'preference-extraction': appRoutes.memory,
  'fact-extraction': appRoutes.memory,
  'task-state-generation': appRoutes.memory,
  'decision-settlement': appRoutes.memory,
  'conflict-detection': appRoutes.memory,
  'conflict-memory-dedup': appRoutes.memory,
  'similar-memory-dedup': appRoutes.memory,
  'memory-fusion-management': appRoutes.memory,
  'low-value-filter': appRoutes.memory,
}

function getLegacyCapabilityRedirect(id?: string) {
  return (id && legacyCapabilityRedirects[id]) || appRoutes.overview
}

export function LegacyCapabilityRedirect() {
  const { capabilityId } = useParams()
  return <Navigate replace to={getLegacyCapabilityRedirect(capabilityId)} />
}
