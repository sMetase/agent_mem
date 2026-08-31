import { App, message as staticMessage } from 'antd'
import { getErrorMessage } from '@/utils/error'

const defaultDuration = 2
type MessageApi = ReturnType<typeof App.useApp>['message']

let contextMessage: MessageApi | undefined

export function setContextMessage(message: MessageApi | undefined) {
  contextMessage = message
}

function getMessageApi() {
  return contextMessage ?? staticMessage
}

export function showSuccessMessage(content: string) {
  void getMessageApi().success({ content, duration: defaultDuration })
}

export function showWarningMessage(content: string) {
  void getMessageApi().warning({ content, duration: defaultDuration })
}

export function showErrorMessage(error: unknown, fallback = '操作失败，请稍后重试。') {
  void getMessageApi().error({
    content: getErrorMessage(error, fallback),
    duration: 3,
  })
}
