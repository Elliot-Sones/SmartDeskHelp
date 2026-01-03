import { knowledgeStoreService } from './knowledge-store'
import { embeddingService } from '../../indexing/embedding'

class PersonalMemoryService {
  /**
   * Learn a new fact about the user
   */
  async learn(fact: string, source: 'user' | 'inferred' = 'user'): Promise<void> {
    console.log(`[PersonalMemory] Learning: "${fact}" (source: ${source})`)

    await knowledgeStoreService.addItem(
      fact,
      'personal',
      source === 'user' ? 'user' : 'inferred'
    )
  }

  /**
   * Recall facts relevant to a query
   */
  async recall(query: string): Promise<string[]> {
    const items = await knowledgeStoreService.query(query, 'personal')
    return items.map((item) => item.content)
  }

  /**
   * Extract potential facts from a conversation message
   * Returns facts that should be stored
   */
  extractFromConversation(message: string): string[] {
    const facts: string[] = []
    const lowerMessage = message.toLowerCase()

    // Pattern: "I am a ___" or "I'm a ___"
    const iAmMatch = lowerMessage.match(/i(?:'m| am) (?:a |an )?(\w+(?:\s+\w+)?)/i)
    if (iAmMatch) {
      const role = iAmMatch[1]
      if (!this.isCommonWord(role)) {
        facts.push(`User is a ${role}`)
      }
    }

    // Pattern: "I like ___" or "I love ___"
    const likeMatch = lowerMessage.match(/i (?:like|love|enjoy|prefer) (\w+(?:\s+\w+)*)/i)
    if (likeMatch) {
      facts.push(`User likes ${likeMatch[1]}`)
    }

    // Pattern: "My name is ___"
    const nameMatch = lowerMessage.match(/my name is (\w+)/i)
    if (nameMatch) {
      facts.push(`User's name is ${nameMatch[1]}`)
    }

    // Pattern: "I work on ___" or "I'm working on ___"
    const workMatch = lowerMessage.match(/i(?:'m)? work(?:ing)? on (\w+(?:\s+\w+)*)/i)
    if (workMatch) {
      facts.push(`User works on ${workMatch[1]}`)
    }

    // Pattern: "I study ___" or "I'm studying ___"
    const studyMatch = lowerMessage.match(/i(?:'m)? study(?:ing)? (\w+(?:\s+\w+)*)/i)
    if (studyMatch) {
      facts.push(`User studies ${studyMatch[1]}`)
    }

    // Pattern: "I prefer ___ over ___"
    const preferMatch = lowerMessage.match(/i prefer (\w+) over (\w+)/i)
    if (preferMatch) {
      facts.push(`User prefers ${preferMatch[1]} over ${preferMatch[2]}`)
    }

    return facts
  }

  /**
   * Check if word is too common to be meaningful
   */
  private isCommonWord(word: string): boolean {
    const commonWords = new Set([
      'the',
      'a',
      'an',
      'is',
      'am',
      'are',
      'was',
      'be',
      'been',
      'being',
      'have',
      'has',
      'had',
      'do',
      'does',
      'did',
      'will',
      'would',
      'could',
      'should',
      'may',
      'might',
      'can',
      'here',
      'there',
      'going',
      'not',
      'just',
      'so',
      'very',
      'really'
    ])

    return commonWords.has(word.toLowerCase())
  }

  /**
   * Initialize with some default personal tree structure
   * Creates empty tree ready to receive facts
   */
  async initialize(): Promise<void> {
    // Check if tree already exists
    const stats = await knowledgeStoreService.getTreeStats('personal')
    if (stats.itemCount > 0) {
      console.log('[PersonalMemory] Tree already initialized')
      return
    }

    // Start with some seed facts that can be used as cluster centers
    const seedFacts = [
      { content: 'User preferences and settings', sourceType: 'system' as const },
      { content: 'User interests and hobbies', sourceType: 'system' as const },
      { content: 'User work and projects', sourceType: 'system' as const }
    ]

    const items = await Promise.all(
      seedFacts.map(async (fact) => ({
        content: fact.content,
        embedding: await embeddingService.embed(fact.content),
        sourceType: fact.sourceType
      }))
    )

    await knowledgeStoreService.buildTree(items, 'personal')
    console.log('[PersonalMemory] Initialized personal memory')
  }
}

export const personalMemoryService = new PersonalMemoryService()
