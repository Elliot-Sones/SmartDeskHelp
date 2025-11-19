import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// Define the settings API directly in preload to avoid importing main process code
const settingsApi = {
  get: () => ipcRenderer.invoke('settings:get'),
  update: (data: any) => ipcRenderer.invoke('settings:update', data)
}

const foldersApi = {
  list: () => ipcRenderer.invoke('folders:list'),
  create: (data: any) => ipcRenderer.invoke('folders:create', data),
  update: (id: number, data: any) => ipcRenderer.invoke('folders:update', id, data),
  delete: (id: number) => ipcRenderer.invoke('folders:delete', id),
  getByPath: (path: string) => ipcRenderer.invoke('folders:getByPath', path)
}

const chatApi = {
  list: () => ipcRenderer.invoke('chat:list'),
  create: (data: any) => ipcRenderer.invoke('chat:create', data),
  update: (id: number, data: any) => ipcRenderer.invoke('chat:update', id, data),
  delete: (id: number) => ipcRenderer.invoke('chat:delete', id),
  get: (id: number) => ipcRenderer.invoke('chat:get', id)
}

const messageApi = {
  listByChatId: (chatId: number) => ipcRenderer.invoke('message:listByChatId', chatId),
  create: (data: any) => ipcRenderer.invoke('message:create', data),
  delete: (id: number) => ipcRenderer.invoke('message:delete', id)
}

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
