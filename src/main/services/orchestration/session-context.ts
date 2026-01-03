/**
 * Session Context Service
 *
 * Manages ephemeral conversation topic embeddings.
 * Extracts topic/intent from user queries (not full messages) and stores them
 * for context retrieval during the conversation. Cleaned up when chat closes.
 */

import { db } from '../../db'
import { sessionContext } from '../../db/tables/session'
import { embeddingService } from '../indexing/embedding'
import { eq, lt } from 'drizzle-orm'

// Topic extraction patterns - extract the semantic core of what user is asking about
const TOPIC_EXTRACTORS: { pattern: RegExp; type: string }[] = [
  // File operations
  { pattern: /(?:find|search|look(?:ing)? for|locate)\s+(?:my\s+)?(.+?)(?:\s+(?:file|document|folder)s?)?(?:\.|$)/i, type: 'file_search' },
  { pattern: /open(?:ing)?\s+(?:my\s+)?(.+?)(?:\.|$)/i, type: 'file_open' },
  { pattern: /read(?:ing)?\s+(?:my\s+)?(.+?)(?:\.|$)/i, type: 'file_read' },
  // System queries
  { pattern: /(?:how much|what(?:'s| is))\s+(?:my\s+)?(.+?)(?:\s+(?:do i have|available|used|free))?/i, type: 'system' },
  { pattern: /(?:why is|is my)\s+(?:my\s+)?(?:computer|system|mac)\s+(.+)/i, type: 'system_issue' },
  // Personal context
  { pattern: /(?:what do you know|tell me)\s+about\s+(.+)/i, type: 'recall' },
  { pattern: /(?:my favorite|i (?:like|love|prefer))\s+(.+)/i, type: 'preference' },
  { pattern: /(?:remember|recall)\s+(?:when|that)\s+(.+)/i, type: 'memory' }
]

class SessionContextService {
  /**
   * Extract topic/intent from a user query.
   * Returns a compact topic string, not the full message.
   */
  extractTopic(query: string): { topic: string; type: string } {
    const queryLower = query.toLowerCase().trim()

    for (const { pattern, type } of TOPIC_EXTRACTORS) {
      const match = queryLower.match(pattern)
      if (match && match[1]) {
        const extracted = match[1].trim()
        // Clean up extracted topic
        const cleaned = extracted
          .replace(/[^\w\s-]/g, ' ')
          .replace(/\s+/g, ' ')
          .trim()
          .slice(0, 100)
        if (cleaned.length > 2) {
          return { topic: cleaned, type }
        }
      }
    }

    // Fallback: extract key nouns/phrases (first 50 chars, cleaned)
    const topic = queryLower
      .replace(/^(what|where|how|why|when|can you|could you|please|help me)\s+/gi, '')
      .replace(/[^\w\s-]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 50)

    return { topic: topic || 'general query', type: 'general' }
  }

  /**
   * Add a topic to session context for a chat.
   * Deduplicates similar topics to avoid bloat.
   */
  async addContext(chatId: number, query: string): Promise<void> {
    const { topic, type } = this.extractTopic(query)

    if (topic.length < 3) return // Skip very short topics

    // Check for duplicate or similar topics
    const existing = await db
      .select()
      .from(sessionContext)
      .where(eq(sessionContext.chatId, chatId))

    // Simple deduplication: skip if topic is substring of existing or vice versa
    const isDuplicate = existing.some(
      (e) =>
        e.topic.toLowerCase().includes(topic.toLowerCase()) ||
        topic.toLowerCase().includes(e.topic.toLowerCase())
    )

    if (isDuplicate) {
      console.log(`[SessionContext] Skipping duplicate topic: "${topic}"`)
      return
    }

    // Embed and store the topic
    const embedding = await embeddingService.embed(topic)

    await db.insert(sessionContext).values({
      chatId,
      topic,
      embedding: embeddingService.serializeEmbedding(embedding)
    })

    console.log(`[SessionContext] Added topic: "${topic}" (${type}) for chat ${chatId}`)
  }

  /**
   * Get relevant context topics for a query.
   * Returns topics sorted by relevance.
   */
  async getRelevantContext(chatId: number, query: string, topK = 3): Promise<string[]> {
    const contexts = await db
      .select()
      .from(sessionContext)
      .where(eq(sessionContext.chatId, chatId))

    if (contexts.length === 0) return []

    // Embed the query
    const queryVec = await embeddingService.embed(query)

    // Score each context by similarity
    const scored = contexts.map((ctx) => ({
      topic: ctx.topic,
      score: embeddingService.cosineSimilarity(
        queryVec,
        embeddingService.deserializeEmbedding(ctx.embedding as Buffer)
      )
    }))

    // Sort by score descending
    scored.sort((a, b) => b.score - a.score)

    // Return top K with minimum relevance threshold
    return scored
      .slice(0, topK)
      .filter((s) => s.score > 0.3)
      .map((s) => s.topic)
  }

  /**
   * Get all topics for a chat (for debugging/display).
   */
  async getAllTopics(chatId: number): Promise<string[]> {
    const contexts = await db
      .select({ topic: sessionContext.topic })
      .from(sessionContext)
      .where(eq(sessionContext.chatId, chatId))

    return contexts.map((c) => c.topic)
  }

  /**
   * Cleanup all session context for a chat.
   * Called when user navigates away from chat.
   */
  async cleanup(chatId: number): Promise<void> {
    await db.delete(sessionContext).where(eq(sessionContext.chatId, chatId))
    console.log(`[SessionContext] Cleaned up context for chat ${chatId}`)
  }

  /**
   * Cleanup all stale sessions (safety net).
   * Removes context older than 24 hours.
   * Called on app startup.
   */
  async cleanupStale(): Promise<void> {
    const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000)

    await db.delete(sessionContext).where(lt(sessionContext.createdAt, cutoff))

    console.log('[SessionContext] Cleaned up stale sessions (>24h old)')
  }
}

export const sessionContextService = new SessionContextService()
