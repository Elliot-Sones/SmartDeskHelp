import { app } from 'electron';
import path from 'path';
import fs from 'fs';

/**
 * Get the database directory path based on the environment
 * Development: project_root/.kel/
 * Production: ~/.kel/
 */
export function getDatabasePath(): string {
  const isDev = !app.isPackaged;
  
  let dbDir: string;
  
  if (isDev) {
    // In development, use .kel/ in the project root
    dbDir = path.join(process.cwd(), '.kel');
  } else {
    // In production, use ~/.kel/
    dbDir = path.join(app.getPath('home'), '.kel');
  }
  
  // Ensure the directory exists
  if (!fs.existsSync(dbDir)) {
    fs.mkdirSync(dbDir, { recursive: true });
  }
  
  return path.join(dbDir, 'database.db');
}
