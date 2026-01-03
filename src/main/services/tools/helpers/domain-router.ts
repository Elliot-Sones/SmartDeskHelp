import { fileSearchService } from './file-search'
import { knowledgeStoreService } from './knowledge-store'

type Domain = 'files' | 'photos' | 'computer' | 'personal'

// Keywords that strongly indicate a domain
const DOMAIN_KEYWORDS: Record<Domain, string[]> = {
  files: ['file', 'folder', 'document', 'open', 'find', 'project', 'code'],
  photos: ['photo', 'picture', 'image', 'pic', 'screenshot', 'selfie', 'vacation'],
  computer: [
    'ram',
    'memory',
    'storage',
    'disk',
    'cpu',
    'processor',
    'chip',
    'app',
    'application',
    'installed',
    'running',
    'computer',
    'system',
    'specs',
    'hardware'
  ],
  personal: [
    'my',
    'i',
    'me',
    'hobby',
    'hobbies',
    'interest',
    'prefer',
    'like',
    'favorite',
    'name',
    'about me'
  ]
}

// Relative weights for each domain when no strong keywords found
const DOMAIN_WEIGHTS = {
  files: 0.4, // Default to files since most queries are file-related
  photos: 0.2,
  computer: 0.2,
  personal: 0.2
}

interface RouteResult {
  domain: Domain
  results: any[]
  confidence: number
}

class DomainRouterService {
  /**
   * Route a query to the appropriate domain and get results
   */
  async route(query: string): Promise<RouteResult> {
    const domain = this.classifyDomain(query)
    console.log(`[DomainRouter] Query: "${query}" → Domain: ${domain}`)

    let results: any[]

    switch (domain) {
      case 'files':
        // Use existing file search
        results = await fileSearchService.findRelevantFiles(query)
        break

      case 'photos':
      case 'computer':
      case 'personal':
        // Use knowledge tree
        results = await knowledgeStoreService.query(query, domain)
        break

      default:
        results = []
    }

    return {
      domain,
      results,
      confidence: 1.0 // TODO: calculate actual confidence
    }
  }

  /**
   * Classify which domain a query belongs to
   * Uses keyword matching first, then falls back to embedding similarity
   */
  private classifyDomain(query: string): Domain {
    const lowerQuery = query.toLowerCase()

    // Count keyword matches for each domain
    const keywordScores: Record<Domain, number> = {
      files: 0,
      photos: 0,
      computer: 0,
      personal: 0
    }

    for (const [domain, keywords] of Object.entries(DOMAIN_KEYWORDS)) {
      for (const keyword of keywords) {
        if (lowerQuery.includes(keyword)) {
          keywordScores[domain as Domain] += 1
        }
      }
    }

    // Find domain with highest keyword score
    let bestDomain: Domain = 'files'
    let bestScore = 0

    for (const [domain, score] of Object.entries(keywordScores)) {
      // Apply weights
      const weightedScore = score * (1 + DOMAIN_WEIGHTS[domain as Domain])

      if (weightedScore > bestScore) {
        bestScore = weightedScore
        bestDomain = domain as Domain
      }
    }

    // If no clear winner (score < 1), check for question patterns
    if (bestScore < 1) {
      if (this.isSystemQuestion(lowerQuery)) {
        return 'computer'
      }
      if (this.isPersonalQuestion(lowerQuery)) {
        return 'personal'
      }
      if (this.isPhotoRequest(lowerQuery)) {
        return 'photos'
      }
    }

    return bestDomain
  }

  /**
   * Check if query is asking about system specs
   */
  private isSystemQuestion(query: string): boolean {
    const patterns = [
      'how much',
      'what.*run',
      'can i run',
      'do i have',
      'what.*installed',
      'what apps',
      'my computer',
      'my mac'
    ]

    return patterns.some((p) => new RegExp(p).test(query))
  }

  /**
   * Check if query is asking about the user
   */
  private isPersonalQuestion(query: string): boolean {
    const patterns = ['what are my', 'what do i', 'who am i', 'about me', 'my hobby', 'my interest']

    return patterns.some((p) => query.includes(p))
  }

  /**
   * Check if query is requesting photos
   */
  private isPhotoRequest(query: string): boolean {
    const patterns = ['show.*photo', 'show.*picture', 'find.*photo', 'beach.*photo', 'vacation.*pic']

    return patterns.some((p) => new RegExp(p).test(query))
  }

  /**
   * Get all domains that might be relevant (for hybrid queries)
   */
  async routeMultiple(query: string): Promise<RouteResult[]> {
    const results: RouteResult[] = []

    // Always check files
    const fileResults = await fileSearchService.findRelevantFiles(query)
    if (fileResults.length > 0) {
      results.push({ domain: 'files', results: fileResults, confidence: 0.8 })
    }

    // Check knowledge domains
    for (const domain of ['photos', 'computer', 'personal'] as const) {
      const domainResults = await knowledgeStoreService.query(query, domain)
      if (domainResults.length > 0) {
        results.push({ domain, results: domainResults, confidence: 0.6 })
      }
    }

    return results
  }
}

export const domainRouterService = new DomainRouterService()
