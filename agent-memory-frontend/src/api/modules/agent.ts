import { request } from '@/api/request'
import type {
  AdminPageResult,
  AgentInfo,
  AgentRegisterPayload,
  AgentRegisterResult,
  AgentRotateKeyResult,
  AgentUpdatePayload,
} from '@/api/types'

export interface ListAgentsParams {
  sceneId?: string
  isActive?: boolean
  page?: number
  pageSize?: number
}

export function registerAgent(payload: AgentRegisterPayload) {
  return request<AgentRegisterResult>({
    url: '/api/v1/agent/register',
    method: 'POST',
    data: payload,
  })
}

export function getAgent(agentId: string) {
  return request<AgentInfo>({
    url: `/api/v1/agent/${encodeURIComponent(agentId)}`,
    method: 'GET',
  })
}

export function listAgents({ sceneId, isActive, page = 1, pageSize = 20 }: ListAgentsParams = {}) {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (sceneId?.trim()) searchParams.set('scene_id', sceneId.trim())
  if (typeof isActive === 'boolean') searchParams.set('is_active', String(isActive))

  return request<AdminPageResult<AgentInfo>>({
    url: `/api/v1/agent?${searchParams.toString()}`,
    method: 'GET',
  })
}

export function updateAgent(agentId: string, payload: AgentUpdatePayload) {
  return request<string>({
    url: `/api/v1/agent/${encodeURIComponent(agentId)}`,
    method: 'PUT',
    data: payload,
  })
}

export function disableAgent(agentId: string) {
  return request<string>({
    url: `/api/v1/agent/${encodeURIComponent(agentId)}`,
    method: 'DELETE',
  })
}

export function rotateAgentKey(agentId: string) {
  return request<AgentRotateKeyResult>({
    url: `/api/v1/agent/${encodeURIComponent(agentId)}/rotate-key`,
    method: 'POST',
  })
}
