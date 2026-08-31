import { Component } from 'react'
import type { ReactNode } from 'react'
import { Button } from 'antd'
import { AppErrorFallback } from '@/components/common/AppErrorFallback'

interface AppErrorBoundaryProps {
  children: ReactNode
}

interface AppErrorBoundaryState {
  error: Error | null
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  override state: AppErrorBoundaryState = {
    error: null,
  }

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error }
  }

  private handleReload = () => {
    window.location.reload()
  }

  override render() {
    if (this.state.error) {
      return (
        <AppErrorFallback
          title="应用渲染出现异常"
          error={this.state.error}
          extra={
            <Button type="primary" onClick={this.handleReload}>
              刷新页面
            </Button>
          }
        />
      )
    }

    return this.props.children
  }
}
