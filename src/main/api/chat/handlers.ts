import { ipcMain } from 'electron'
import { eq, desc } from 'drizzle-orm'
import { db } from '../../db'
import { chat } from '../../db/tables/chat'
import {
  createChatSchema,
  updateChatSchema,
  type Chat,
  type ChatApi,
  type CreateChatData,
  type UpdateChatData
} from './schema'

export function createChatApi(ipcRenderer: any): ChatApi {
  return {
    list: () => ipcRenderer.invoke('chat:list'),
    create: (data) => ipcRenderer.invoke('chat:create', data),
    update: (id, data) => ipcRenderer.invoke('chat:update', id, data),
    delete: (id) => ipcRenderer.invoke('chat:delete', id),
    get: (id) => ipcRenderer.invoke('chat:get', id)
  }
}

export function registerChatHandlers() {
  ipcMain.handle('chat:list', async (): Promise<Chat[]> => {
    return await db.select().from(chat).orderBy(desc(chat.updatedAt))
  })

  ipcMain.handle('chat:create', async (_event, data: CreateChatData): Promise<Chat> => {
    const validated = createChatSchema.parse(data)
    const result = await db.insert(chat).values(validated).returning()
    return result[0]
  })

  ipcMain.handle(
    'chat:update',
    async (_event, id: number, data: UpdateChatData): Promise<Chat | null> => {
      const validated = updateChatSchema.parse(data)
      await db
        .update(chat)
        .set({ ...validated, updatedAt: new Date() })
        .where(eq(chat.id, id))

      const result = await db.select().from(chat).where(eq(chat.id, id))
      return result[0] || null
    }
  )

  ipcMain.handle('chat:delete', async (_event, id: number): Promise<boolean> => {
    try {
      await db.delete(chat).where(eq(chat.id, id))
      return true
    } catch {
      return false
    }
  })

  ipcMain.handle('chat:get', async (_event, id: number): Promise<Chat | null> => {
    const result = await db.select().from(chat).where(eq(chat.id, id))
    return result[0] || null
  })
}
