import { drizzle } from 'drizzle-orm/libsql'
import { migrate } from 'drizzle-orm/libsql/migrator'
import { app } from 'electron'
import { join } from 'path'
import { getDatabasePath } from './config'
import * as schema from './schema.js'

const databasePath = getDatabasePath()
const databaseUrl = `file:${databasePath}`

export const db = drizzle(databaseUrl, { schema })

export async function runMigrations() {
  // In production, migrations are bundled with the app
  const migrationsPath = app.isPackaged
    ? join(process.resourcesPath, 'drizzle')
    : join(__dirname, '../../..', 'drizzle')

  await migrate(db, { migrationsFolder: migrationsPath })
}

export type Database = typeof db
