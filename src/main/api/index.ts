import { registerSettingsApi } from './settings'
import { registerFoldersApi } from './folders'
import { registerChatApi } from './chat'
import { registerMessageApi } from './message'

export function registerAllApis() {
  registerSettingsApi()
  registerFoldersApi()
  registerChatApi()
  registerMessageApi()
}
