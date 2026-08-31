import { request } from '@/api/request'
import type {
  AdminPageResult,
  TaskCompleteResult,
  TaskCreatePayload,
  TaskInfo,
  TaskProgressResult,
  TaskProgressUpdatePayload,
} from '@/api/types'

export interface ListTasksParams {
  userId?: string
  status?: TaskInfo['status']
  sessionId?: string
  page?: number
  pageSize?: number
}

export function createTask(payload: TaskCreatePayload) {
  return request<TaskInfo>({
    url: '/api/v1/task',
    method: 'POST',
    data: payload,
  })
}

export function getTask(taskId: string) {
  return request<TaskInfo>({
    url: `/api/v1/task/${encodeURIComponent(taskId)}`,
    method: 'GET',
  })
}

export function listTasks({
  userId,
  status,
  sessionId,
  page = 1,
  pageSize = 20,
}: ListTasksParams = {}) {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (userId?.trim()) searchParams.set('user_id', userId.trim())
  if (status) searchParams.set('status', status)
  if (sessionId?.trim()) searchParams.set('session_id', sessionId.trim())

  return request<AdminPageResult<TaskInfo>>({
    url: `/api/v1/task?${searchParams.toString()}`,
    method: 'GET',
  })
}

export function updateTaskProgress(taskId: string, payload: TaskProgressUpdatePayload) {
  return request<{ task_id: string; updated: boolean; status?: TaskInfo['status'] }>({
    url: `/api/v1/task/${encodeURIComponent(taskId)}`,
    method: 'PUT',
    data: payload,
  })
}

export function getTaskProgress(taskId: string) {
  return request<TaskProgressResult>({
    url: `/api/v1/task/${taskId}/progress`,
    method: 'GET',
  })
}

export function completeTask(taskId: string) {
  return request<TaskCompleteResult>({
    url: `/api/v1/task/${encodeURIComponent(taskId)}/complete`,
    method: 'POST',
  })
}
