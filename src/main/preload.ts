import { electronAPI } from '@electron-toolkit/preload'
import { contextBridge, ipcRenderer } from 'electron'

const settingsApi = {
  get: () => ipcRenderer.invoke('settings:get'),
  update: (data) => ipcRenderer.invoke('settings:update', data)
}

const foldersApi = {
  list: () => ipcRenderer.invoke('folders:list'),
  create: (data) => ipcRenderer.invoke('folders:create', data),
  update: (id, data) => ipcRenderer.invoke('folders:update', id, data),
  delete: (id) => ipcRenderer.invoke('folders:delete', id),
  getByPath: (path) => ipcRenderer.invoke('folders:getByPath', path)
}

const chatApi = {
  list: () => ipcRenderer.invoke('chat:list'),
  create: (data) => ipcRenderer.invoke('chat:create', data),
  update: (id, data) => ipcRenderer.invoke('chat:update', id, data),
  delete: (id) => ipcRenderer.invoke('chat:delete', id),
  get: (id) => ipcRenderer.invoke('chat:get', id)
}

const messageApi = {
  listByChatId: (chatId) => ipcRenderer.invoke('message:listByChatId', chatId),
  create: (data) => ipcRenderer.invoke('message:create', data),
  delete: (id) => ipcRenderer.invoke('message:delete', id)
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
