import { db } from '../db'
import { knowledgeNodes, knowledgeItems } from '../db/schema'
import { embeddingService } from './embedding'
import { eq, isNull, and } from 'drizzle-orm'

// Clustering configuration
const CLUSTERING_CONFIG = {
  // Target children per level
  L0_TARGET: 4, // 3-5 clusters at root
  L1_TARGET: 7, // 5-10 clusters at level 1
  L2_TARGET: 15, // 10-20 items at level 2+

  // Leaf size constraints
  MIN_LEAF_SIZE: 10, // Don't split clusters smaller than this
  MAX_LEAF_SIZE: 50, // Must split clusters larger than this

  // Max tree depth
  MAX_DEPTH: 4
}

type Domain = 'photos' | 'computer' | 'personal'

interface ClusterResult {
  centroid: Float32Array
  itemIndices: number[]
}

/**
 * K-means clustering implementation
 * Groups embeddings into k clusters based on cosine similarity
 */
function kMeansClustering(embeddings: Float32Array[], k: number, maxIterations = 20): ClusterResult[] {
  if (embeddings.length <= k) {
    // Each embedding is its own cluster
    return embeddings.map((emb, i) => ({
      centroid: emb,
      itemIndices: [i]
    }))
  }

  // Initialize centroids using k-means++ (spread out initial centers)
  const centroids: Float32Array[] = []
  const usedIndices = new Set<number>()

  // First centroid: random
  const firstIdx = Math.floor(Math.random() * embeddings.length)
  centroids.push(embeddings[firstIdx])
  usedIndices.add(firstIdx)

  // Remaining centroids: pick points far from existing centroids
  while (centroids.length < k) {
    let maxDist = -1
    let bestIdx = 0

    for (let i = 0; i < embeddings.length; i++) {
      if (usedIndices.has(i)) continue

      // Find min distance to any existing centroid
      let minDistToCentroid = Infinity
      for (const centroid of centroids) {
        const sim = embeddingService.cosineSimilarity(embeddings[i], centroid)
        const dist = 1 - sim
        if (dist < minDistToCentroid) minDistToCentroid = dist
      }

      if (minDistToCentroid > maxDist) {
        maxDist = minDistToCentroid
        bestIdx = i
      }
    }

    centroids.push(embeddings[bestIdx])
    usedIndices.add(bestIdx)
  }

  // Iterate: assign points to nearest centroid, then recomputecentroids
  let assignments: number[] = new Array(embeddings.length).fill(0)

  for (let iter = 0; iter < maxIterations; iter++) {
    // Assign each point to nearest centroid
    const newAssignments: number[] = []
    for (let i = 0; i < embeddings.length; i++) {
      let bestCluster = 0
      let bestSim = -Infinity

      for (let c = 0; c < k; c++) {
        const sim = embeddingService.cosineSimilarity(embeddings[i], centroids[c])
        if (sim > bestSim) {
          bestSim = sim
          bestCluster = c
        }
      }
      newAssignments.push(bestCluster)
    }

    // Check for convergence
    let changed = false
    for (let i = 0; i < embeddings.length; i++) {
      if (newAssignments[i] !== assignments[i]) {
        changed = true
        break
      }
    }

    assignments = newAssignments

    if (!changed) break

    // Recompute centroids
    for (let c = 0; c < k; c++) {
      const clusterEmbeddings = embeddings.filter((_, i) => assignments[i] === c)
      if (clusterEmbeddings.length > 0) {
        centroids[c] = embeddingService.meanPool(clusterEmbeddings)
      }
    }
  }

  // Build result
  const results: ClusterResult[] = []
  for (let c = 0; c < k; c++) {
    const itemIndices = assignments
      .map((a, i) => (a === c ? i : -1))
      .filter((i) => i >= 0)

    if (itemIndices.length > 0) {
      results.push({
        centroid: centroids[c],
        itemIndices
      })
    }
  }

  return results
}

class KnowledgeTreeService {
  /**
   * Build a semantic tree from a list of items
   * Uses hierarchical k-means clustering
   */
  async buildTree(
    items: { content: string; embedding: Float32Array; sourceType?: string; sourcePath?: string }[],
    domain: Domain
  ): Promise<void> {
    console.log(`[KnowledgeTree] Building tree for ${domain} with ${items.length} items`)

    // Clear existing tree for this domain
    await db.delete(knowledgeItems).where(eq(knowledgeItems.domain, domain))
    await db.delete(knowledgeNodes).where(eq(knowledgeNodes.domain, domain))

    if (items.length === 0) return

    // Build tree recursively starting from root
    await this.buildSubtree(items, domain, null, 0)

    console.log(`[KnowledgeTree] Tree built for ${domain}`)
  }

  /**
   * Recursively build subtree
   */
  private async buildSubtree(
    items: { content: string; embedding: Float32Array; sourceType?: string; sourcePath?: string }[],
    domain: Domain,
    parentId: number | null,
    depth: number
  ): Promise<void> {
    // Determine target cluster count based on depth
    let targetK: number
    if (depth === 0) {
      targetK = CLUSTERING_CONFIG.L0_TARGET
    } else if (depth === 1) {
      targetK = CLUSTERING_CONFIG.L1_TARGET
    } else {
      targetK = CLUSTERING_CONFIG.L2_TARGET
    }

    // Check if we should stop splitting
    const shouldBeLeaf =
      items.length <= CLUSTERING_CONFIG.MIN_LEAF_SIZE ||
      depth >= CLUSTERING_CONFIG.MAX_DEPTH ||
      items.length <= targetK

    if (shouldBeLeaf) {
      // Create a single node with all items as leaves
      const nodeEmbedding = embeddingService.meanPool(items.map((i) => i.embedding))

      const [node] = await db
        .insert(knowledgeNodes)
        .values({
          parentId,
          domain,
          depth,
          embedding: embeddingService.serializeEmbedding(nodeEmbedding),
          itemCount: items.length,
          createdAt: new Date(),
          updatedAt: new Date()
        })
        .returning()

      // Insert all items under this node
      for (const item of items) {
        await db.insert(knowledgeItems).values({
          nodeId: node.id,
          domain,
          content: item.content,
          embedding: embeddingService.serializeEmbedding(item.embedding),
          sourceType: item.sourceType || 'system',
          sourcePath: item.sourcePath,
          createdAt: new Date()
        })
      }

      return
    }

    // Cluster the items
    const embeddings = items.map((i) => i.embedding)
    const clusters = kMeansClustering(embeddings, targetK)

    console.log(
      `[KnowledgeTree] Depth ${depth}: Split ${items.length} items into ${clusters.length} clusters`
    )

    // Create a node for each cluster and recurse
    for (const cluster of clusters) {
      const clusterItems = cluster.itemIndices.map((i) => items[i])

      // Create node
      const [node] = await db
        .insert(knowledgeNodes)
        .values({
          parentId,
          domain,
          depth,
          embedding: embeddingService.serializeEmbedding(cluster.centroid),
          itemCount: clusterItems.length,
          createdAt: new Date(),
          updatedAt: new Date()
        })
        .returning()

      // Recurse
      await this.buildSubtree(clusterItems, domain, node.id, depth + 1)
    }
  }

  /**
   * Query the tree to find relevant items
   * Navigates down the tree, only comparing at each level
   */
  async query(queryText: string, domain: Domain, topK = 5): Promise<typeof knowledgeItems.$inferSelect[]> {
    console.log(`[KnowledgeTree] Query: "${queryText}" in domain: ${domain}`)

    const queryVec = await embeddingService.embed(queryText)

    // Start at root nodes for this domain
    let currentNodes = await db
      .select()
      .from(knowledgeNodes)
      .where(and(eq(knowledgeNodes.domain, domain), isNull(knowledgeNodes.parentId)))

    if (currentNodes.length === 0) {
      console.log(`[KnowledgeTree] No tree found for domain: ${domain}`)
      return []
    }

    let comparisons = 0

    // Navigate down the tree
    while (true) {
      // Score current level nodes
      const scored = currentNodes.map((node) => {
        const nodeEmbedding = node.embedding as Buffer
        const score = embeddingService.cosineSimilarity(queryVec, nodeEmbedding)
        comparisons++
        return { node, score }
      })

      scored.sort((a, b) => b.score - a.score)
      const bestNode = scored[0].node

      console.log(
        `[KnowledgeTree] Level ${bestNode.depth}: Picked node ${bestNode.id} (score: ${scored[0].score.toFixed(3)})`
      )

      // Get children of best node
      const children = await db
        .select()
        .from(knowledgeNodes)
        .where(eq(knowledgeNodes.parentId, bestNode.id))

      if (children.length === 0) {
        // We're at a leaf node, get the items
        const items = await db
          .select()
          .from(knowledgeItems)
          .where(eq(knowledgeItems.nodeId, bestNode.id))

        // Score and sort items
        const scoredItems = items.map((item) => {
          const itemEmbedding = item.embedding as Buffer
          const score = embeddingService.cosineSimilarity(queryVec, itemEmbedding)
          comparisons++
          return { item, score }
        })

        scoredItems.sort((a, b) => b.score - a.score)

        console.log(`[KnowledgeTree] Total comparisons: ${comparisons} (vs ${await this.getTotalItemCount(domain)} items)`)

        return scoredItems.slice(0, topK).map((s) => s.item)
      }

      // Continue down to children
      currentNodes = children
    }
  }

  /**
   * Add a single item to the tree (finds best cluster)
   */
  async addItem(
    content: string,
    domain: Domain,
    sourceType: string,
    sourcePath?: string
  ): Promise<void> {
    const embedding = await embeddingService.embed(content)

    // Find the best leaf node to add this to
    let currentNodes = await db
      .select()
      .from(knowledgeNodes)
      .where(and(eq(knowledgeNodes.domain, domain), isNull(knowledgeNodes.parentId)))

    if (currentNodes.length === 0) {
      // No tree exists, create root node
      const [node] = await db
        .insert(knowledgeNodes)
        .values({
          parentId: null,
          domain,
          depth: 0,
          embedding: embeddingService.serializeEmbedding(embedding),
          itemCount: 1,
          createdAt: new Date(),
          updatedAt: new Date()
        })
        .returning()

      await db.insert(knowledgeItems).values({
        nodeId: node.id,
        domain,
        content,
        embedding: embeddingService.serializeEmbedding(embedding),
        sourceType,
        sourcePath,
        createdAt: new Date()
      })

      return
    }

    // Navigate to best leaf
    while (true) {
      const scored = currentNodes.map((node) => {
        const nodeEmbedding = node.embedding as Buffer
        const score = embeddingService.cosineSimilarity(embedding, nodeEmbedding)
        return { node, score }
      })

      scored.sort((a, b) => b.score - a.score)
      const bestNode = scored[0].node

      const children = await db
        .select()
        .from(knowledgeNodes)
        .where(eq(knowledgeNodes.parentId, bestNode.id))

      if (children.length === 0) {
        // Found leaf, add item here
        await db.insert(knowledgeItems).values({
          nodeId: bestNode.id,
          domain,
          content,
          embedding: embeddingService.serializeEmbedding(embedding),
          sourceType,
          sourcePath,
          createdAt: new Date()
        })

        // Update node embedding (mean pool with new item)
        const items = await db
          .select()
          .from(knowledgeItems)
          .where(eq(knowledgeItems.nodeId, bestNode.id))

        const embeddings = items.map((i) => {
          const buf = i.embedding as Buffer
          return embeddingService.deserializeEmbedding(buf)
        })

        const newNodeEmbedding = embeddingService.meanPool(embeddings)

        await db
          .update(knowledgeNodes)
          .set({
            embedding: embeddingService.serializeEmbedding(newNodeEmbedding),
            itemCount: items.length,
            updatedAt: new Date()
          })
          .where(eq(knowledgeNodes.id, bestNode.id))

        // Check if we need to split this node
        if (items.length > CLUSTERING_CONFIG.MAX_LEAF_SIZE) {
          console.log(`[KnowledgeTree] Node ${bestNode.id} exceeded max size, needs rebalancing`)
          // TODO: Implement split logic
        }

        return
      }

      currentNodes = children
    }
  }

  /**
   * Get total item count for a domain
   */
  private async getTotalItemCount(domain: Domain): Promise<number> {
    const items = await db.select().from(knowledgeItems).where(eq(knowledgeItems.domain, domain))
    return items.length
  }

  /**
   * Get tree statistics for debugging
   */
  async getTreeStats(domain: Domain): Promise<{
    nodeCount: number
    itemCount: number
    maxDepth: number
  }> {
    const nodes = await db.select().from(knowledgeNodes).where(eq(knowledgeNodes.domain, domain))
    const items = await db.select().from(knowledgeItems).where(eq(knowledgeItems.domain, domain))

    const maxDepth = nodes.reduce((max, n) => Math.max(max, n.depth), 0)

    return {
      nodeCount: nodes.length,
      itemCount: items.length,
      maxDepth
    }
  }
}

export const knowledgeTreeService = new KnowledgeTreeService()
