# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kel (internally "Minnie") is an AI assistant desktop app built with Electron + React (TypeScript). It appears as a sidebar window toggled with `Cmd/Ctrl+K` (quick search popup) or `Cmd/Ctrl+Shift+K` (full window). Uses OpenRouter for cloud LLMs or Ollama for local models.

## Final output goal
Optmise perfect context manipulation on your computer. With almost 0 space taken (disk or ram), and all locally (8gb of ram mac m2), I want to be able to query my computer about anything i need.

Find a file? 
Open, read etc... 
Ask questions about my computer, why is my computer so slow etc 
Personal context. 

It all gets embedded and saved to the db so that when we need the information it can call it. I even want to feed the current conversation details to the embedding since we are dealing with small models it doenst handle contexts so we embed the context and if the info in the context is needed we pull it. After the conversation ends the context data gets deleted.


## Development Commands

```bash
pnpm install                # Install dependencies
pnpm dev                    # Development with hot reload

# For development, also run the Python router server:
python3 python/function_gemma_server.py

pnpm typecheck              # Check both node and web
pnpm lint                   # ESLint
pnpm format                 # Prettier

pnpm build:mac              # Build for macOS
pnpm build:win              # Build for Windows
pnpm build:linux            # Build for Linux

pnpm db:generate            # Generate Drizzle migrations
pnpm db:push                # Push schema changes directly
pnpm db:studio              # Open Drizzle Studio UI
```

## Architecture

### Electron Process Structure
- **Main process** (`src/main/`): Node.js backend handling IPC, database, AI streaming, file indexing
- **Preload** (`src/preload/`, `src/main/preload.ts`): Bridges main/renderer via `window.api` object
- **Renderer** (`src/renderer/`): React frontend with react-router-dom

### IPC API Pattern
APIs are defined in `src/main/api/{domain}/`:
- `schema.ts`: Zod schemas + TypeScript types for IPC contracts
- `handlers.ts`: IPC handler implementations

All APIs are registered in `src/main/api/index.ts` → `registerAllApis()`.

The preload script exposes typed APIs: `window.api.settings`, `window.api.chat`, `window.api.message`, `window.api.ai`.

### Database
SQLite via Drizzle ORM. Tables in `src/main/db/tables/`:
- `settings`: App configuration (API keys, selected model)
- `chat`, `message`: Conversation history
- `semantic`: Indexed files with embeddings for semantic search
- `knowledge`: System info, photos, personal memory facts

Schema definition: `src/main/db/schema.ts`
Drizzle config: `drizzle.config.ts` (outputs to `./drizzle/`)

### AI & Tool Routing
1. User query → `src/main/api/ai/handlers.ts` → `processAiStream()`
2. Gemma Router (`src/main/services/orchestration/tool-router.ts`) selects tool via Python server or keyword fallback
3. Tool execution gathers context → injected into LLM system prompt
4. Response streamed via IPC `chat:stream` events

Meta-tools: `local_query` (files, system, memory), `web_query` (Google search), `conversation` (no context), `see` (screenshot + vision)

### Services Structure
- `src/main/services/indexing/`: Embedding generation, file indexer
- `src/main/services/orchestration/`: Tool router (Gemma-based)
- `src/main/services/tools/actions/`: File opener, screen capture, Google search
- `src/main/services/tools/helpers/`: File reader, content extraction, knowledge store, personal memory

### Frontend Routing
Hash router in `src/renderer/src/routes/index.tsx`:
- `/` - Home page
- `/chat/:id` - Chat conversation
- `/settings` - Settings page
- `/search-popup` - Quick search popup (separate window)

### Model Configuration
Supports OpenRouter models (prefixed normally) and Ollama models (prefixed `ollama/`). Model selection stored in settings table.

---

## TODO: Retrieval System Improvements

### Problem 1: Shallow Content Extraction (CRITICAL) ⬜
**Current:** Only first 500 chars of documents are embedded.
**Impact:** Can't answer questions about content beyond the intro.
**Fix:** Implement document chunking - split into overlapping ~512 char segments, store multiple embeddings per file.

### Problem 2: Photos Are Just Paths (BROKEN) ⬜
**Current:** Photo "descriptions" are just file paths like `Photo: Mcgill in current---ntangible-website...`
**Impact:** Can't do semantic photo search like "find sunset photos"
**Fix:** Use Ollama vision model (llava) to generate actual descriptions, or extract EXIF metadata.

### Problem 3: Static Computer Knowledge (OUTDATED) ⬜
**Current:** Computer facts are snapshot-in-time (e.g., "0GB free RAM" from index time)
**Impact:** Can't answer "Why is my computer slow right now?"
**Fix:** Add live system queries instead of relying solely on indexed facts.

### Problem 4: Session Context Not Implemented ⬜
**Current:** `session_context` table has 0 rows. Conversations aren't being embedded.
**Impact:** Can't retrieve relevant past conversation context.
**Fix:** Embed conversation topics/summaries, clean up after session ends.

### Problem 5: Personal Memory is Minimal ⬜
**Current:** Only 16 personal facts, mostly manually added.
**Impact:** Limited personalization and memory.
**Fix:** Auto-learn from conversations - extract facts when user mentions preferences, work, etc.

### Problem 6: Knowledge Tree Single-Path ⬜
**Current:** Tree search only follows the single best node at each level.
**Impact:** Misses relevant items if they're in a different but related cluster.
**Fix:** Multi-path search - explore top 2-3 nodes above threshold.
