"""
Training Data Configuration
"""

# Output paths
OUTPUT_DIR = "./data/generated"
CACHE_DIR = "./data/cache"

# Dataset sizes per layer
LAYER_1_SIZE = 15000  # SQuAD answerable
LAYER_2_SIZE = 15000  # Reasoning (HotpotQA, DROP, CoQA)
LAYER_3_SIZE = 10000  # Format variance
LAYER_4_SIZE = 10000  # Domain-specific
LAYER_5_SIZE = 5000   # Negative examples

# Negative example ratio
NEGATIVE_RATIO = 0.09

# Format templates for format variance
FORMAT_TEMPLATES = [
    # Format 1: Numbered chunks (production format)
    "Context:\n{chunks}\n\nQuestion: {question}",
    # Format 2: Markdown headers
    "## Context\n{chunks}\n\n## Question\n{question}",
    # Format 3: Plain text
    "Information: {chunks}\n\nQuery: {question}",
    # Format 4: Bullet points
    "• {chunks_bullet}\n\nQuestion: {question}",
    # Format 5: Key-value style
    "DATA:\n{chunks_kv}\n\nQUESTION: {question}",
    # Format 6: JSON-like
    '{{"context": "{chunks_escaped}", "question": "{question}"}}',
    # Format 7: Conversational
    "Here's what I found: {chunks}\n\nYou asked: {question}",
    # Format 8: Mixed/messy
    "{chunks_messy}\n---\n{question}",
]

# Chunk format templates
CHUNK_TEMPLATES = [
    "[{idx}] {source}: {content}",
    "**{source}**: {content}",
    "{source} - {content}",
    "({idx}) {content}",
    "{content}",
]

# Standard refusal response
NO_ANSWER = "Not found in provided context."
