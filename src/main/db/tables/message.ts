import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core'
import { chat } from './chat'

export const message = sqliteTable('message', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  chatId: integer('chat_id')
    .notNull()
    .references(() => chat.id, { onDelete: 'cascade' }),
  role: text('role', { enum: ['user', 'assistant'] }).notNull(),
  content: text('content').notNull(),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date())
})
