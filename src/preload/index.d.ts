import { ElectronAPI } from '@electron-toolkit/preload'

interface API {
  onWindowShowing: (callback: () => void) => void
  onWindowHiding: (callback: () => void) => void
}

declare global {
  interface Window {
    electron: ElectronAPI
    api: API
  }
}
