import { sqliteTable, text, integer, blob } from 'drizzle-orm/sqlite-core'

// Semantic folder nodes in the tree
export const semanticFolders = sqliteTable('semantic_folders', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  path: text('path').notNull().unique(),
  parentId: integer('parent_id'),
  name: text('name').notNull(),
  depth: integer('depth').notNull(),
  summary: text('summary'),
  embedding: blob('embedding'),
  fileCount: integer('file_count').default(0),
  indexedAt: integer('indexed_at', { mode: 'timestamp' })
})

// Individual file index with content signatures
export const semanticFiles = sqliteTable('semantic_files', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  folderId: integer('folder_id').notNull(),
  path: text('path').notNull().unique(),
  name: text('name').notNull(),
  embedding: blob('embedding'), // Filename/path embedding
  contentSignature: text('content_signature'), // First ~500 chars of content
  contentEmbedding: blob('content_embedding'), // Embedding of content
  extension: text('extension'),
  indexedAt: integer('indexed_at', { mode: 'timestamp' })
})
