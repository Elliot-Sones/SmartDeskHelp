import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'
import { createSettingsApi } from './api/settings/handlers'
import { createChatApi } from './api/chat/handlers'
import { createMessageApi } from './api/message/handlers'
import { createFoldersApi } from './api/folders/handlers'

const settingsApi = createSettingsApi(ipcRenderer)
const foldersApi = createFoldersApi(ipcRenderer)
const chatApi = createChatApi(ipcRenderer)
const messageApi = createMessageApi(ipcRenderer)

const api = {
  settings: settingsApi,
  folders: foldersApi,
  chat: chatApi,
  message: messageApi
}

export function exposeApi() {
  if (process.contextIsolated) {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } else {
    // @ts-ignore
    window.electron = electronAPI
    // @ts-ignore
    window.api = api
  }
}
