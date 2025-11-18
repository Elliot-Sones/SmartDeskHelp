import { ElectronAPI } from '@electron-toolkit/preload'
import type { SettingsApi } from './api/settings'
import type { FoldersApi } from './api/folders'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      settings: SettingsApi
      folders: FoldersApi
    }
  }
}
