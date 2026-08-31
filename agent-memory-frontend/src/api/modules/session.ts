import { request } from '@/api/request'
import type {
  AdminPageResult,
  SessionCloseResult,
  SessionCreatePayload,
  SessionInfo,
  SessionUpdatePayload,
} from '@/api/types'

export interface ListSessionsParams {
  userId?: string
  agentId?: string
  status?: 'active' | 'closed'
  sceneId?: string
  page?: number
  pageSize?: number
}

export function createSession(payload: SessionCreatePayload) {
  return request<SessionInfo>({
    url: '/api/v1/session',
    method: 'POST',
    data: payload,
  })
}

export function getSession(sessionId: string) {
  return request<SessionInfo>({
    url: `/api/v1/session/${encodeURIComponent(sessionId)}`,
    method: 'GET',
  })
}

export function listSessions({
  userId,
  agentId,
  status,
  sceneId,
  page = 1,
  pageSize = 20,
}: ListSessionsParams = {}) {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (userId?.trim()) searchParams.set('user_id', userId.trim())
  if (agentId?.trim()) searchParams.set('agent_id', agentId.trim())
  if (status) searchParams.set('status', status)
  if (sceneId?.trim()) searchParams.set('scene_id', sceneId.trim())

  return request<AdminPageResult<SessionInfo>>({
    url: `/api/v1/session?${searchParams.toString()}`,
    method: 'GET',
  })
}

export function updateSession(sessionId: string, payload: SessionUpdatePayload) {
  return request<string>({
    url: `/api/v1/session/${encodeURIComponent(sessionId)}`,
    method: 'PUT',
    data: payload,
  })
}

export function closeSession(sessionId: string) {
  return request<SessionCloseResult>({
    url: `/api/v1/session/${encodeURIComponent(sessionId)}/close`,
    method: 'POST',
  })
}
