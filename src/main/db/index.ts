import { drizzle } from 'drizzle-orm/libsql';
import { getDatabasePath } from './config';
import * as schema from './schema.js';

// Get the database URL
const databasePath = getDatabasePath();
const databaseUrl = `file:${databasePath}`;

// Initialize Drizzle
export const db = drizzle(databaseUrl, { schema });

// Export types
export type Database = typeof db;
