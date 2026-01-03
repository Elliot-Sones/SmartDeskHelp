import { sqliteTable, text, integer, blob, real } from 'drizzle-orm/sqlite-core'

/**
 * Knowledge tree nodes — hierarchical clusters for semantic routing
 * Each node represents a cluster at some level of the tree
 * Routing works by comparing query to nodes at each level, descending
 */
export const knowledgeNodes = sqliteTable('knowledge_nodes', {
  id: integer('id').primaryKey({ autoIncrement: true }),

  // Tree structure
  parentId: integer('parent_id'), // null = root node
  domain: text('domain').notNull(), // 'photos' | 'computer' | 'personal'
  depth: integer('depth').notNull(), // 0 = root, 1 = level 1, etc.

  // Embedding for routing (mean of all children)
  embedding: blob('embedding').notNull(),

  // Metadata
  itemCount: integer('item_count').default(0), // How many leaf items under this
  label: text('label'), // Optional human-readable label for debugging
  createdAt: integer('created_at', { mode: 'timestamp' }),
  updatedAt: integer('updated_at', { mode: 'timestamp' })
})

/**
 * Knowledge metadata — tracks tree state for caching
 * Used to skip rebuilding trees if data hasn't changed
 */
export const knowledgeMetadata = sqliteTable('knowledge_metadata', {
  domain: text('domain').primaryKey(), // 'photos' | 'computer' | 'personal'
  version: integer('version').notNull().default(1),
  itemHash: text('item_hash'), // Hash of all item contents for change detection
  lastBuilt: integer('last_built', { mode: 'timestamp' }),
  nodeCount: integer('node_count'),
  itemCount: integer('item_count')
})

/**
 * Knowledge items — leaf nodes containing actual content
 * Things like "User has 8GB RAM" or a photo description
 */
export const knowledgeItems = sqliteTable('knowledge_items', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  nodeId: integer('node_id').notNull(), // Which cluster this belongs to

  // Content
  domain: text('domain').notNull(), // 'photos' | 'computer' | 'personal'
  content: text('content').notNull(), // The actual fact/description
  embedding: blob('embedding').notNull(), // Content embedding

  // Source tracking
  sourceType: text('source_type'), // 'file' | 'system' | 'inferred' | 'user'
  sourcePath: text('source_path'), // Path if from file

  // Metadata
  confidence: real('confidence').default(1.0), // 0-1, how confident we are
  accessCount: integer('access_count').default(0), // How often retrieved
  createdAt: integer('created_at', { mode: 'timestamp' })
})
