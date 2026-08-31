import type { TaskProgressResult } from '@/api/types'

export const mockTaskProgress: TaskProgressResult = {
  task_id: 'task_demo',
  status: 'in_progress',
  completed_count: 1,
  pending_count: 2,
  related_memory_count: 4,
}
