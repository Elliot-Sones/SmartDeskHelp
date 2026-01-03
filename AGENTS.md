This file provides guidance when working with code in this repository.

## Project Overview

Kel is an AI agent desktop application that lives on your computer. It's built as an Electron app with React (TypeScript) frontend and uses a local SQLite database via Drizzle ORM. The app appears as a sidebar window (similar to Raycast) that can be toggled with `Control+K`.

## Development Commands

```bash
# Install dependencies (uses pnpm)
pnpm install

# Development mode with hot reload
pnpm dev

# Type checking
pnpm typecheck              # Check both node and web
pnpm typecheck:node         # Check main/preload process only
pnpm typecheck:web          # Check renderer process only

# Code quality
pnpm lint
pnpm format

# Build for production
pnpm build                  # Build without packaging
pnpm build:mac             # Build and package for macOS
pnpm build:win             # Build and package for Windows
pnpm build:linux           # Build and package for Linux

# Database operations
pnpm db:generate           # Generate migrations from schema
pnpm db:migrate            # Run migrations
pnpm db:push               # Push schema changes directly
pnpm db:studio             # Open Drizzle Studio UI
```
