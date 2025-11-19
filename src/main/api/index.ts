import { registerSettingsHandlers } from './settings/handlers'
import { registerFoldersHandlers } from './folders/handlers'
import { registerChatHandlers } from './chat/handlers'
import { registerMessageHandlers } from './message/handlers'

export function registerAllApis() {
  registerSettingsHandlers()
  registerFoldersHandlers()
  registerChatHandlers()
  registerMessageHandlers()
}

// Re-export schemas for type-safe imports (safe for client-side)
export * from './settings/schema'
export * from './chat/schema'
export * from './folders/schema'
export * from './message/schema'
