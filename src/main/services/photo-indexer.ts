import { readdirSync, statSync } from 'fs'
import { join, basename, extname } from 'path'
import { homedir } from 'os'
import { knowledgeTreeService } from './knowledge-tree'
import { embeddingService } from './embedding'

// Supported image extensions
const IMAGE_EXTENSIONS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp'])

// Directories to skip
const SKIP_DIRS = new Set(['node_modules', '.git', 'Library', '.Trash', 'Applications'])

interface PhotoInfo {
  path: string
  name: string
  content: string // Description for embedding
}

class PhotoIndexerService {
  /**
   * Scan photo directories and build semantic tree
   */
  async indexPhotos(directories?: string[]): Promise<void> {
    const dirs = directories || this.getDefaultPhotoDirectories()
    console.log(`[PhotoIndexer] Scanning directories: ${dirs.join(', ')}`)

    const photos: PhotoInfo[] = []

    for (const dir of dirs) {
      try {
        await this.scanDirectory(dir, photos, 0)
      } catch (e) {
        console.error(`[PhotoIndexer] Error scanning ${dir}:`, e)
      }
    }

    console.log(`[PhotoIndexer] Found ${photos.length} photos`)

    if (photos.length === 0) return

    // Embed all photo descriptions
    const items = await Promise.all(
      photos.map(async (photo) => ({
        content: photo.content,
        embedding: await embeddingService.embed(photo.content),
        sourceType: 'file' as const,
        sourcePath: photo.path
      }))
    )

    // Build knowledge tree for photos domain
    await knowledgeTreeService.buildTree(items, 'photos')

    console.log('[PhotoIndexer] Photos indexed successfully')
  }

  /**
   * Recursively scan directory for images
   */
  private async scanDirectory(dir: string, photos: PhotoInfo[], depth: number): Promise<void> {
    if (depth > 5) return // Max depth

    try {
      const entries = readdirSync(dir, { withFileTypes: true })

      for (const entry of entries) {
        if (entry.name.startsWith('.')) continue

        const fullPath = join(dir, entry.name)

        if (entry.isDirectory()) {
          if (SKIP_DIRS.has(entry.name)) continue
          await this.scanDirectory(fullPath, photos, depth + 1)
        } else if (entry.isFile()) {
          const ext = extname(entry.name).toLowerCase()
          if (IMAGE_EXTENSIONS.has(ext)) {
            photos.push({
              path: fullPath,
              name: entry.name,
              content: this.describePhoto(fullPath, entry.name)
            })
          }
        }
      }
    } catch (e) {
      // Skip directories we can't read
    }
  }

  /**
   * Generate a text description for a photo
   * Based on filename, path, and metadata
   */
  private describePhoto(path: string, name: string): string {
    const parts: string[] = []

    // Clean filename (remove extension, replace underscores/dashes)
    const cleanName = basename(name, extname(name))
      .replace(/[-_]/g, ' ')
      .replace(/\d{8,}/g, '') // Remove date stamps like 20231225
      .trim()

    parts.push(`Photo: ${cleanName}`)

    // Extract folder context
    const pathParts = path.split('/').filter((p) => !SKIP_DIRS.has(p))
    const relevantFolders = pathParts.slice(-4, -1) // Last 3 folders before filename
    if (relevantFolders.length > 0) {
      parts.push(`in ${relevantFolders.join('/')}`)
    }

    // Try to detect common patterns
    const lowerPath = path.toLowerCase()

    if (lowerPath.includes('screenshot')) {
      parts.push('screenshot')
    }
    if (lowerPath.includes('vacation') || lowerPath.includes('travel')) {
      parts.push('vacation travel photo')
    }
    if (lowerPath.includes('family')) {
      parts.push('family photo')
    }
    if (lowerPath.includes('selfie')) {
      parts.push('selfie')
    }
    if (lowerPath.includes('beach') || lowerPath.includes('ocean')) {
      parts.push('beach ocean photo')
    }
    if (lowerPath.includes('birthday') || lowerPath.includes('party')) {
      parts.push('birthday party celebration')
    }
    if (lowerPath.includes('wedding')) {
      parts.push('wedding photo')
    }
    if (lowerPath.includes('graduation')) {
      parts.push('graduation photo')
    }

    return parts.join(' ')
  }

  /**
   * Get default directories to scan for photos
   */
  private getDefaultPhotoDirectories(): string[] {
    const home = homedir()
    return [
      join(home, 'Pictures'),
      join(home, 'Photos'),
      join(home, 'Desktop'),
      join(home, 'Downloads')
    ].filter((dir) => {
      try {
        statSync(dir)
        return true
      } catch {
        return false
      }
    })
  }

  /**
   * Add a single photo to the index
   */
  async addPhoto(path: string): Promise<void> {
    const name = basename(path)
    const content = this.describePhoto(path, name)

    await knowledgeTreeService.addItem(content, 'photos', 'file', path)
  }
}

export const photoIndexerService = new PhotoIndexerService()
