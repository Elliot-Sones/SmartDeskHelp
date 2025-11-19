import { ipcMain } from 'electron'
import { eq } from 'drizzle-orm'
import type { InferSelectModel } from 'drizzle-orm'
import { db } from '../db'
import { message } from '../db/tables/message'

export type Message = InferSelectModel<typeof message>

export interface CreateMessageData {
  chatId: number
  role: 'user' | 'assistant'
  content: string
}

export interface MessageApi {
  listByChatId: (chatId: number) => Promise<Message[]>
  create: (data: CreateMessageData) => Promise<Message>
  delete: (id: number) => Promise<boolean>
}

export function createMessageApi(ipcRenderer: any): MessageApi {
  return {
    listByChatId: (chatId) => ipcRenderer.invoke('message:listByChatId', chatId),
    create: (data) => ipcRenderer.invoke('message:create', data),
    delete: (id) => ipcRenderer.invoke('message:delete', id)
  }
}

export function registerMessageApi() {
  ipcMain.handle('message:listByChatId', async (_event, chatId: number): Promise<Message[]> => {
    return await db
      .select()
      .from(message)
      .where(eq(message.chatId, chatId))
      .orderBy(message.createdAt)
  })

  ipcMain.handle('message:create', async (_event, data: CreateMessageData): Promise<Message> => {
    const result = await db.insert(message).values(data).returning()
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
