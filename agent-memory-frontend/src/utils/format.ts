export function formatPercent(value?: number) {
  if (typeof value !== 'number') {
    return '--'
  }

  return `${(value * 100).toFixed(1)}%`
}
