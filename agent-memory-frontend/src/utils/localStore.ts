/** 轻量 localStorage JSON 存取工具（后端接口就绪后，配置可切换为 API 存储）。 */
export function loadJson<T>(key: string, fallback: T): T {
  const rawValue = localStorage.getItem(key)
  if (!rawValue) return fallback
  try {
    return JSON.parse(rawValue) as T
  } catch {
    return fallback
  }
}

export function saveJson<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value))
}
