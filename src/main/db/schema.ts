/**
 * Database Schema Exports
 *
 * This file exports all Drizzle table schemas.
 *
 * Active tables:
 *   - settings: App configuration
 *   - chat: Conversation sessions
 *   - message: Chat messages
 *
 * Deprecated tables (kept for migration compatibility):
 *   - semantic: Old file indexing (replaced by LEANN)
 *   - knowledge: Old knowledge tree (replaced by LEANN)
 *   - session: Unused session context
 *
 * @module db/schema
 */

// Active tables
export * from './tables/settings'
export * from './tables/chat'
export * from './tables/message'

// Deprecated tables - kept for migration compatibility only
// These are no longer used; indexing is handled by Python LEANN server
export * from './tables/semantic'
export * from './tables/knowledge'
export * from './tables/session'
