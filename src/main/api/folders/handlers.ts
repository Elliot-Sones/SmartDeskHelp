import { eq } from 'drizzle-orm'
import { ipcMain } from 'electron'
import { db } from '../../db'
import { folders } from '../../db/tables/folders'
import {
  createFolderSchema,
  updateFolderSchema,
  type CreateFolderData,
  type Folder,
  type UpdateFolderData
} from './schema'

export function registerFoldersHandlers() {
  ipcMain.handle('folders:list', async (): Promise<Folder[]> => {
    return await db.select().from(folders)
  })

  ipcMain.handle('folders:create', async (_event, data: CreateFolderData): Promise<Folder> => {
    const validated = createFolderSchema.parse(data)
    const result = await db.insert(folders).values(validated).returning()
    return result[0]
  })

  ipcMain.handle(
    'folders:update',
    async (_event, id: number, data: UpdateFolderData): Promise<Folder | null> => {
      const validated = updateFolderSchema.parse(data)
      await db
        .update(folders)
        .set({ ...validated, updatedAt: new Date() })
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
