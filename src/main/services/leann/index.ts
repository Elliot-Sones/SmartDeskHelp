/**
 * LEANN Service Module
 *
 * Provides semantic search capabilities over indexed files, photos, and memory.
 *
 * Quick Start:
 *   import { leannClient } from './services/leann'
 *
 *   // Find files
 *   const files = await leannClient.findFiles("project report")
 *
 *   // Read content
 *   const chunks = await leannClient.readContent("what does my resume say")
 *
 * Architecture:
 *   This module is a TypeScript client for the Python LEANN server.
 *   The server must be running at localhost:8765 for search to work.
 *
 *   Start the server with:
 *     python python/function_gemma_server.py
 *
 *   Build the index with:
 *     python python/leann_indexer.py
 *
 * @module services/leann
 */

export {
  // Client class and singleton
  LeannClient,
  leannClient,

  // Types
  type SearchIntent,
  type DataSource,
  type SearchParams,
  type SearchResult,
  type SearchResponse,
  type IndexStatus
} from './client'
