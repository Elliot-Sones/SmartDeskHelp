import { execSync } from 'child_process'
import { cpus, totalmem, freemem, platform, release, hostname } from 'os'
import { readdirSync } from 'fs'
import { knowledgeTreeService } from './knowledge-tree'
import { embeddingService } from './embedding'

interface SystemFact {
  content: string
  sourceType: 'system'
}

class SystemScraperService {
  /**
   * Scrape all system info and build knowledge tree
   */
  async scrapeAndIndex(): Promise<void> {
    console.log('[SystemScraper] Starting system info collection...')

    const facts: SystemFact[] = []

    // Collect all facts
    facts.push(...this.scrapeHardware())
    facts.push(...(await this.scrapeApps()))
    facts.push(...this.scrapeOS())

    console.log(`[SystemScraper] Collected ${facts.length} system facts`)

    // Embed all facts
    const items = await Promise.all(
      facts.map(async (fact) => ({
        content: fact.content,
        embedding: await embeddingService.embed(fact.content),
        sourceType: fact.sourceType
      }))
    )

    // Build knowledge tree for computer domain
    await knowledgeTreeService.buildTree(items, 'computer')

    console.log('[SystemScraper] System info indexed successfully')
  }

  /**
   * Get hardware information
   */
  private scrapeHardware(): SystemFact[] {
    const facts: SystemFact[] = []

    // RAM
    const totalRAM = Math.round(totalmem() / 1024 / 1024 / 1024)
    const freeRAM = Math.round(freemem() / 1024 / 1024 / 1024)
    facts.push({
      content: `Computer has ${totalRAM}GB total RAM memory`,
      sourceType: 'system'
    })
    facts.push({
      content: `Computer currently has ${freeRAM}GB free RAM available`,
      sourceType: 'system'
    })

    // CPU
    const cpuInfo = cpus()[0]
    facts.push({
      content: `Computer has a ${cpuInfo.model} processor`,
      sourceType: 'system'
    })
    facts.push({
      content: `Computer has ${cpus().length} CPU cores`,
      sourceType: 'system'
    })

    // Try to get Apple Silicon info on Mac
    if (platform() === 'darwin') {
      try {
        const chipInfo = execSync('sysctl -n machdep.cpu.brand_string', { encoding: 'utf-8' }).trim()
        facts.push({
          content: `Computer has ${chipInfo} chip`,
          sourceType: 'system'
        })
      } catch {
        // Not available or not Apple Silicon
      }

      // GPU info on Mac
      try {
        const gpuInfo = execSync(
          'system_profiler SPDisplaysDataType | grep "Chipset Model" | head -1',
          { encoding: 'utf-8' }
        ).trim()
        if (gpuInfo) {
          const gpuName = gpuInfo.replace('Chipset Model:', '').trim()
          facts.push({
            content: `Computer has ${gpuName} graphics`,
            sourceType: 'system'
          })
        }
      } catch {
        // GPU info not available
      }

      // Storage info on Mac
      try {
        const diskInfo = execSync("df -h / | tail -1 | awk '{print $2, $3, $4}'", {
          encoding: 'utf-8'
        }).trim()
        const [total, used, available] = diskInfo.split(' ')
        facts.push({
          content: `Computer has ${total} total storage, ${used} used, ${available} available`,
          sourceType: 'system'
        })
      } catch {
        // Disk info not available
      }
    }

    return facts
  }

  /**
   * Get installed applications
   */
  private async scrapeApps(): Promise<SystemFact[]> {
    const facts: SystemFact[] = []

    if (platform() === 'darwin') {
      // macOS: scan /Applications
      try {
        const appsDir = '/Applications'
        const apps = readdirSync(appsDir)
          .filter((name) => name.endsWith('.app'))
          .map((name) => name.replace('.app', ''))

        // Add as individual facts for better clustering
        for (const app of apps.slice(0, 50)) {
          // Limit to 50 apps
          facts.push({
            content: `${app} application is installed`,
            sourceType: 'system'
          })
        }

        // Also add summary
        facts.push({
          content: `User has ${apps.length} applications installed including ${apps.slice(0, 5).join(', ')}`,
          sourceType: 'system'
        })
      } catch (e) {
        console.error('[SystemScraper] Error scanning apps:', e)
      }

      // Check for specific developer tools
      const devTools = [
        { cmd: 'which node', name: 'Node.js' },
        { cmd: 'which python3', name: 'Python' },
        { cmd: 'which git', name: 'Git' },
        { cmd: 'which docker', name: 'Docker' },
        { cmd: 'which ollama', name: 'Ollama' }
      ]

      for (const tool of devTools) {
        try {
          execSync(tool.cmd, { encoding: 'utf-8' })
          facts.push({
            content: `${tool.name} is installed on this computer`,
            sourceType: 'system'
          })
        } catch {
          // Tool not installed
        }
      }
    }

    return facts
  }

  /**
   * Get OS information
   */
  private scrapeOS(): SystemFact[] {
    const facts: SystemFact[] = []

    facts.push({
      content: `Computer is running ${platform() === 'darwin' ? 'macOS' : platform()} version ${release()}`,
      sourceType: 'system'
    })

    facts.push({
      content: `Computer is named ${hostname()}`,
      sourceType: 'system'
    })

    return facts
  }

  /**
   * Get a quick summary without building tree
   */
  getSummary(): Record<string, string> {
    return {
      ram: `${Math.round(totalmem() / 1024 / 1024 / 1024)}GB`,
      cpu: cpus()[0].model,
      platform: platform() === 'darwin' ? 'macOS' : platform(),
      cores: cpus().length.toString()
    }
  }
}

export const systemScraperService = new SystemScraperService()
