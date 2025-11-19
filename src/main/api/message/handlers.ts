import { ipcMain } from 'electron'
import { eq } from 'drizzle-orm'
import { db } from '../../db'
import { message } from '../../db/tables/message'
import {
  createMessageSchema,
  type Message,
  type MessageApi,
  type CreateMessageData
} from './schema'

export function createMessageApi(ipcRenderer: any): MessageApi {
  return {
    listByChatId: (chatId) => ipcRenderer.invoke('message:listByChatId', chatId),
    create: (data) => ipcRenderer.invoke('message:create', data),
    delete: (id) => ipcRenderer.invoke('message:delete', id)
  }
}

export function registerMessageHandlers() {
  ipcMain.handle('message:listByChatId', async (_event, chatId: number): Promise<Message[]> => {
    return await db
      .select()
      .from(message)
      .where(eq(message.chatId, chatId))
      .orderBy(message.createdAt)
  })

  ipcMain.handle('message:create', async (_event, data: CreateMessageData): Promise<Message> => {
    const validated = createMessageSchema.parse(data)
    const result = await db.insert(message).values(validated).returning()
    return result[0]
  })

  ipcMain.handle('message:delete', async (_event, id: number): Promise<boolean> => {
    try {
      await db.delete(message).where(eq(message.id, id))
      return true
    } catch {
      return false
    }
  })
}
