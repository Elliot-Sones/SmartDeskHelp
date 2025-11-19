import { ipcMain } from 'electron'
import { eq, desc } from 'drizzle-orm'
import type { InferSelectModel } from 'drizzle-orm'
import { db } from '../db'
import { chat } from '../db/tables/chat'

export type Chat = InferSelectModel<typeof chat>

export interface CreateChatData {
  title: string
}

export interface UpdateChatData {
  title?: string
}

export interface ChatApi {
  list: () => Promise<Chat[]>
  create: (data: CreateChatData) => Promise<Chat>
  update: (id: number, data: UpdateChatData) => Promise<Chat | null>
  delete: (id: number) => Promise<boolean>
  get: (id: number) => Promise<Chat | null>
}

export function createChatApi(ipcRenderer: any): ChatApi {
  return {
    list: () => ipcRenderer.invoke('chat:list'),
    create: (data) => ipcRenderer.invoke('chat:create', data),
    update: (id, data) => ipcRenderer.invoke('chat:update', id, data),
    delete: (id) => ipcRenderer.invoke('chat:delete', id),
    get: (id) => ipcRenderer.invoke('chat:get', id)
  }
}

export function registerChatApi() {
  ipcMain.handle('chat:list', async (): Promise<Chat[]> => {
    return await db.select().from(chat).orderBy(desc(chat.updatedAt))
  })

  ipcMain.handle('chat:create', async (_event, data: CreateChatData): Promise<Chat> => {
    const result = await db.insert(chat).values(data).returning()
    return result[0]
  })

  ipcMain.handle(
    'chat:update',
    async (_event, id: number, data: UpdateChatData): Promise<Chat | null> => {
      await db
        .update(chat)
        .set({ ...data, updatedAt: new Date() })
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
