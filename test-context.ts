#!/usr/bin/env node
/**
 * Test script to show exactly what context would be fed to the LLM
 * Run with: npx ts-node --esm test-context.ts
 */

import { fileSearchService } from './src/main/services/tools/helpers/file-search.js'
import { knowledgeStoreService } from './src/main/services/tools/helpers/knowledge-store.js'
import { embeddingService } from './src/main/services/indexing/embedding.js'

async function testQuery(query: string, type: 'files' | 'system' | 'memory') {
  console.log('\n' + '='.repeat(60))
  console.log(`QUERY: "${query}"`)
  console.log(`TYPE: ${type}`)
  console.log('='.repeat(60))
  
  await embeddingService.initialize()
  
  let context = ''
  
  if (type === 'files') {
    const files = await fileSearchService.findRelevantFiles(query)
    if (files.length === 0) {
      context = '\n\n## File Search\nNo matching files found.'
    } else {
      context = `\n\n## File Search Results\n${files.slice(0, 5).map((f, i) => 
        `${i + 1}. **${f.name}** (score: ${f.score.toFixed(3)})\n   Path: ${f.path}`).join('\n')}`
    }
  } else if (type === 'system') {
    const items = await knowledgeStoreService.query(query, 'computer')
    if (items.length === 0) {
      context = '\n\n## System Info\nNo system information indexed yet.'
    } else {
      context = `\n\n## System Information\n${items.slice(0, 5).map(item => `- ${item.content}`).join('\n')}`
    }
  }
  
  console.log('\n--- CONTEXT FED TO LLM ---')
  console.log(context)
  console.log('--- END CONTEXT ---\n')
  
  return context
}

async function main() {
  console.log('Testing LLM Context Generation\n')
  
  // Test file queries
  await testQuery('find my resume', 'files')
  await testQuery('python scripts', 'files')
  await testQuery('PDF documents', 'files')
  
  // Test system queries
  await testQuery('how much RAM do I have', 'system')
  await testQuery('what apps are installed', 'system')
  await testQuery('storage space available', 'system')
  await testQuery('computer specs', 'system')
  
  process.exit(0)
}

main().catch(console.error)
