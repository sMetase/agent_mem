import { apiClient } from '@/api/client'
import { request } from '@/api/request'
import type {
  AdminApiLogItem,
  AdminApiLogParams,
  AdminPageResult,
  AdminRetrievalLogItem,
  AdminRetrievalLogParams,
  HealthResult,
} from '@/api/types'

function addPaginationParams(
  searchParams: URLSearchParams,
  params: { hours?: number; page?: number; pageSize?: number },
) {
  searchParams.set('hours', String(params.hours ?? 24))
  searchParams.set('page', String(params.page ?? 1))
  searchParams.set('page_size', String(params.pageSize ?? 20))
}

export function buildAdminApiLogsUrl(params: AdminApiLogParams = {}) {
  const searchParams = new URLSearchParams()
  addPaginationParams(searchParams, params)
  if (params.apiPath?.trim()) searchParams.set('api_path', params.apiPath.trim())
  if (params.errorCode?.trim()) searchParams.set('error_code', params.errorCode.trim())
  return `/api/v1/admin/api-logs?${searchParams.toString()}`
}

export function buildAdminRetrievalLogsUrl(params: AdminRetrievalLogParams = {}) {
  const searchParams = new URLSearchParams()
  addPaginationParams(searchParams, params)
  if (params.agentId?.trim()) searchParams.set('agent_id', params.agentId.trim())
  return `/api/v1/admin/retrieval-logs?${searchParams.toString()}`
}

export async function getHealth() {
  const response = await apiClient.get<HealthResult>('/api/v1/health')
  return response.data
}

export function getAdminApiLogs(params: AdminApiLogParams = {}) {
  return request<AdminPageResult<AdminApiLogItem>>({
    url: buildAdminApiLogsUrl(params),
    method: 'GET',
  })
}

export function getAdminRetrievalLogs(params: AdminRetrievalLogParams = {}) {
  return request<AdminPageResult<AdminRetrievalLogItem>>({
    url: buildAdminRetrievalLogsUrl(params),
    method: 'GET',
  })
}
