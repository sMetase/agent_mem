import { Modal } from 'antd'

interface ConfirmDialogOptions {
  title: string
  content: string
  onOk: () => void | Promise<void>
}

export function openConfirmDialog({ title, content, onOk }: ConfirmDialogOptions) {
  Modal.confirm({
    title,
    content,
    okText: '确认',
    cancelText: '取消',
    onOk,
  })
}
