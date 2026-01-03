import { pipeline, env } from '@xenova/transformers'

// Configure model path for Electron
env.allowRemoteModels = true
env.useBrowserCache = false

type EmbeddingPipeline = Awaited<ReturnType<typeof pipeline>>

// Batch size for embedding multiple texts at once
const BATCH_SIZE = 32

class EmbeddingService {
  private embedder: EmbeddingPipeline | null = null
  private initPromise: Promise<void> | null = null

  /**
   * Ensure the model is loaded. Called automatically on first use.
   * This enables lazy-loading to save ~33MB RAM at startup.
   */
  private async ensureInitialized(): Promise<void> {
    if (this.embedder) return
    if (this.initPromise) return this.initPromise

    this.initPromise = (async () => {
      console.log('[Embedding] Lazy-loading MiniLM model...')
      this.embedder = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2')
      console.log('[Embedding] Model loaded successfully')
    })()

    return this.initPromise
  }

  /**
   * @deprecated Use embed() or embedBatch() directly - they auto-initialize
   */
  async initialize(): Promise<void> {
    return this.ensureInitialized()
  }

  /**
   * Embed a single text. Auto-initializes model on first use.
   */
  async embed(text: string): Promise<Float32Array> {
    await this.ensureInitialized()

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const embedder = this.embedder as any
    const result = await embedder(text, {
      pooling: 'mean',
      normalize: true
    })

    return new Float32Array(result.data)
  }

  /**
   * Embed multiple texts in a batch (much faster for bulk processing)
   * Returns array of embeddings in the same order as input texts.
   * Auto-initializes model on first use.
   */
  async embedBatch(texts: string[]): Promise<Float32Array[]> {
    if (texts.length === 0) return []

    await this.ensureInitialized()

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const embedder = this.embedder as any

    // Process in batches to avoid memory issues
    const results: Float32Array[] = []

    for (let i = 0; i < texts.length; i += BATCH_SIZE) {
      const batch = texts.slice(i, i + BATCH_SIZE)

      const batchResults = await embedder(batch, {
        pooling: 'mean',
        normalize: true
      })

      // Extract embeddings from batch result
      // For batch input, result.data contains all embeddings concatenated
      const embeddingDim = 384 // MiniLM embedding dimension
      for (let j = 0; j < batch.length; j++) {
        const start = j * embeddingDim
        const end = start + embeddingDim
        results.push(new Float32Array(batchResults.data.slice(start, end)))
      }
    }

    return results
  }

  cosineSimilarity(a: Float32Array | Buffer, b: Float32Array | Buffer): number {
    let vecA: Float32Array
    let vecB: Float32Array

    if (a instanceof Float32Array) {
      vecA = a
    } else if (Buffer.isBuffer(a)) {
      vecA = new Float32Array(new Uint8Array(a).buffer)
    } else {
      console.error('[Embedding] Unexpected type for a:', typeof a)
      return 0
    }

    if (b instanceof Float32Array) {
      vecB = b
    } else if (Buffer.isBuffer(b)) {
      vecB = new Float32Array(new Uint8Array(b).buffer)
    } else {
      console.error('[Embedding] Unexpected type for b:', typeof b)
      return 0
    }

    if (vecA.length !== vecB.length) {
      console.error(`[Embedding] Vector length mismatch: ${vecA.length} vs ${vecB.length}`)
      return 0
    }

    let dot = 0
    for (let i = 0; i < vecA.length; i++) {
      dot += vecA[i] * vecB[i]
    }
    return dot
  }

  serializeEmbedding(embedding: Float32Array): Buffer {
    const buffer = Buffer.alloc(embedding.length * 4)
    for (let i = 0; i < embedding.length; i++) {
      buffer.writeFloatLE(embedding[i], i * 4)
    }
    return buffer
  }

  deserializeEmbedding(buffer: Buffer): Float32Array {
    const floats = new Float32Array(buffer.length / 4)
    for (let i = 0; i < floats.length; i++) {
      floats[i] = buffer.readFloatLE(i * 4)
    }
    return floats
  }

  /**
   * Compute mean of multiple embeddings
   * Used for folder content aggregation
   */
  meanPool(embeddings: Float32Array[]): Float32Array {
    const dim = 384 // MiniLM embedding dimension
    if (embeddings.length === 0) return new Float32Array(dim)

    const result = new Float32Array(dim)
    for (const emb of embeddings) {
      for (let i = 0; i < dim; i++) {
        result[i] += emb[i]
      }
    }
    for (let i = 0; i < dim; i++) {
      result[i] /= embeddings.length
    }

    // Normalize the result
    let norm = 0
    for (let i = 0; i < dim; i++) {
      norm += result[i] * result[i]
    }
    norm = Math.sqrt(norm)
    if (norm > 0) {
      for (let i = 0; i < dim; i++) {
        result[i] /= norm
      }
    }

    return result
  }
}

export const embeddingService = new EmbeddingService()
