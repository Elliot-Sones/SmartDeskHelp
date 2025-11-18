import { ipcMain } from 'electron'
import { eq } from 'drizzle-orm'
import type { InferSelectModel } from 'drizzle-orm'
import { db } from '../db'
import { folders } from '../db/tables/folders'

export type Folder = InferSelectModel<typeof folders>

export interface CreateFolderData {
  path: string
  name: string
  isFavorite?: boolean
}

export interface UpdateFolderData {
  name?: string
  isFavorite?: boolean
  lastAccessedAt?: Date
}

export interface FoldersApi {
  list: () => Promise<Folder[]>
  create: (data: CreateFolderData) => Promise<Folder>
  update: (id: number, data: UpdateFolderData) => Promise<Folder | null>
  delete: (id: number) => Promise<boolean>
  getByPath: (path: string) => Promise<Folder | null>
}

export function createFoldersApi(ipcRenderer: any): FoldersApi {
  return {
    list: () => ipcRenderer.invoke('folders:list'),
    create: (data) => ipcRenderer.invoke('folders:create', data),
    update: (id, data) => ipcRenderer.invoke('folders:update', id, data),
    delete: (id) => ipcRenderer.invoke('folders:delete', id),
    getByPath: (path) => ipcRenderer.invoke('folders:getByPath', path)
  }
}

export function registerFoldersApi() {
  ipcMain.handle('folders:list', async (): Promise<Folder[]> => {
    return await db.select().from(folders)
  })

  ipcMain.handle('folders:create', async (_event, data: CreateFolderData): Promise<Folder> => {
    const result = await db.insert(folders).values(data).returning()
    return result[0]
  })

  ipcMain.handle(
    'folders:update',
    async (_event, id: number, data: UpdateFolderData): Promise<Folder | null> => {
      await db
        .update(folders)
        .set({ ...data, updatedAt: new Date() })
        .where(eq(folders.id, id))

      const result = await db.select().from(folders).where(eq(folders.id, id))
      return result[0] || null
    }
  )

  ipcMain.handle('folders:delete', async (_event, id: number): Promise<boolean> => {
    try {
      await db.delete(folders).where(eq(folders.id, id))
      return true
    } catch {
      return false
    }
  })

  ipcMain.handle('folders:getByPath', async (_event, path: string): Promise<Folder | null> => {
    const result = await db.select().from(folders).where(eq(folders.path, path))
    return result[0] || null
  })
}
