import { sqliteTable, text, integer, blob } from 'drizzle-orm/sqlite-core'

/**
 * Session context - ephemeral conversation topic embeddings
 * Stores extracted topics/intents from user queries, NOT full messages.
 * Deleted immediately when chat session closes.
 */
export const sessionContext = sqliteTable('session_context', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  chatId: integer('chat_id').notNull(),

  // Extracted topic/intent (e.g., "tax documents", "system performance")
  topic: text('topic').notNull(),
  embedding: blob('embedding').notNull(),

  // Relevance tracking
  queryCount: integer('query_count').default(1),
  lastUsed: integer('last_used', { mode: 'timestamp' }).$defaultFn(() => new Date()),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date())
})
