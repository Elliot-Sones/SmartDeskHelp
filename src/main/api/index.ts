import { registerSettingsApi } from './settings'
import { registerFoldersApi } from './folders'

export function registerAllApis() {
  registerSettingsApi()
  registerFoldersApi()
}
