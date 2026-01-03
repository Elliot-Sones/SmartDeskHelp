import { ollama } from 'ai-sdk-ollama'

/**
 * Get an Ollama language model instance for local inference.
 * Uses the default Ollama server at http://localhost:11434
 */
export function getOllamaModel(modelId: string) {
  return ollama(modelId)
}

/**
 * Parse an Ollama model ID from the SupportedModels format.
 * e.g., 'ollama/phi3.5:latest' -> 'phi3.5:latest'
 */
export function parseOllamaModel(modelId: string): string {
  return modelId.replace('ollama/', '')
}
