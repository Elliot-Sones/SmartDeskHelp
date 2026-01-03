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
  contentSignature: text('content_signature'), // First ~500 chars of content (kept for summary)
  contentEmbedding: blob('content_embedding'), // Embedding of first chunk (for folder aggregation)
  extension: text('extension'),
  indexedAt: integer('indexed_at', { mode: 'timestamp' }),
  // Incremental indexing fields
  contentHash: text('content_hash'), // Hash of file content for change detection
  lastModified: integer('last_modified', { mode: 'timestamp' }), // File mtime for quick comparison
  // Chunking metadata
  chunkCount: integer('chunk_count').default(0) // Number of chunks for this file
})

// Document chunks for deep content search
// Each file can have multiple chunks for searching within long documents
export const semanticChunks = sqliteTable('semantic_chunks', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  fileId: integer('file_id').notNull(), // References semanticFiles.id
  chunkIndex: integer('chunk_index').notNull(), // 0, 1, 2, ... order in document
  content: text('content').notNull(), // The actual chunk text (~512 chars)
  embedding: blob('embedding').notNull(), // Embedding of this chunk
  charOffset: integer('char_offset').notNull() // Starting character position in original doc
})
