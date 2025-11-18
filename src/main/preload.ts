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

const api = {
  settings: settingsApi,
  folders: foldersApi
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
