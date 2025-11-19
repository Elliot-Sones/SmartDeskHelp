import { z } from 'zod'
import type { InferSelectModel } from 'drizzle-orm'
import type { folders } from '../../db/tables/folders'

// Inferred type from database schema
export type Folder = InferSelectModel<typeof folders>

// Zod schemas for validation
export const createFolderSchema = z.object({
  path: z.string().min(1, 'Path is required'),
  name: z.string().min(1, 'Name is required').max(255),
  isFavorite: z.boolean().optional()
})

export const updateFolderSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255).optional(),
  isFavorite: z.boolean().optional(),
  lastAccessedAt: z.date().optional()
})

// TypeScript types
export type CreateFolderData = z.infer<typeof createFolderSchema>
export type UpdateFolderData = z.infer<typeof updateFolderSchema>

// Client-side API interface
export interface FoldersApi {
  list: () => Promise<Folder[]>
  create: (data: CreateFolderData) => Promise<Folder>
  update: (id: number, data: UpdateFolderData) => Promise<Folder | null>
  delete: (id: number) => Promise<boolean>
  getByPath: (path: string) => Promise<Folder | null>
}
