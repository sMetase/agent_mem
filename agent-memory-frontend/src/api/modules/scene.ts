import { request } from '@/api/request'
import type {
  AdminPageResult,
  SceneCreatePayload,
  SceneInfo,
  SceneUpdatePayload,
} from '@/api/types'

export interface ListScenesParams {
  isActive?: boolean
  page?: number
  pageSize?: number
}

export function createScene(payload: SceneCreatePayload) {
  return request<SceneInfo>({
    url: '/api/v1/scene',
    method: 'POST',
    data: payload,
  })
}

export function getScene(sceneId: string) {
  return request<SceneInfo>({
    url: `/api/v1/scene/${encodeURIComponent(sceneId)}`,
    method: 'GET',
  })
}

export function listScenes({ isActive, page = 1, pageSize = 20 }: ListScenesParams = {}) {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (typeof isActive === 'boolean') searchParams.set('is_active', String(isActive))

  return request<AdminPageResult<SceneInfo>>({
    url: `/api/v1/scene?${searchParams.toString()}`,
    method: 'GET',
  })
}

export function updateScene(sceneId: string, payload: SceneUpdatePayload) {
  return request<string>({
    url: `/api/v1/scene/${encodeURIComponent(sceneId)}`,
    method: 'PUT',
    data: payload,
  })
}

export function disableScene(sceneId: string) {
  return request<string>({
    url: `/api/v1/scene/${encodeURIComponent(sceneId)}`,
    method: 'DELETE',
  })
}
