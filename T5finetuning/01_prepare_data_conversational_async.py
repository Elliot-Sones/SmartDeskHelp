#!/usr/bin/env python3
"""
01_prepare_data_conversational_async.py - OPTIMIZED Async Version

This version processes examples in parallel using asyncio for 10x speedup.

SEQUENTIAL:  150K examples × 1.2s = ~50 hours
ASYNC (10x): 150K examples ÷ 10 = ~5 hours

Run: python3 01_prepare_data_conversational_async.py
"""

import json
import os
import random
import asyncio
from pathlib import Path
from tqdm.asyncio import tqdm_asyncio
import anthropic

# =============================================================================
# CONFIGURATION
# =============================================================================

# TEST: 50 examples for Phase 2-3 (change to 30000 for full run on GPU)
NUM_EXAMPLES_TO_GENERATE = 50

# Concurrency (how many requests in parallel)
# Anthropic allows high concurrency on Haiku
MAX_CONCURRENT_REQUESTS = 20  # Process 20 at a time

# Source files
POSITIVE_SOURCE_FILES = [
    "generated/layer1_squad.jsonl",
    "generated/layer2_reasoning.jsonl",
]

NEGATIVE_SOURCE_FILES = [
    "generated/layer5_negatives.jsonl",
]

# Output files
OUTPUT_FILE_POSITIVE = "./data/generated/train_conversational_positive.jsonl"
OUTPUT_FILE_NEGATIVE = "./data/generated/train_conversational_negative.jsonl"

GENERATE_TYPE = "both"  # or set via env: export GENERATE_TYPE="positive"

# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_PROMPT_POSITIVE = """You are a helpful AI assistant that answers questions based on provided context.

Your task: Given a context and question, rewrite the extractive answer as a natural, conversational response.

STRICT RULES:
1. Keep answers concise: 1-2 sentences maximum
2. Only use information from the provided context - never make things up
3. Be helpful and natural, but not overly chatty
4. For file paths: say "I found that at [path]" or "Your file is at [path]"
5. For system info: explain what it means briefly (e.g., "97% RAM means you're nearly out of memory")
6. Never start with "Based on the context" - just answer naturally
7. Never use phrases like "According to the provided information" - be direct"""

SYSTEM_PROMPT_NEGATIVE = """You are a helpful AI assistant that answers questions based on provided context.

Your task: Given a context and question, provide a polite refusal when the answer is not in the context.

STRICT RULES:
1. Keep refusals short: 1 sentence only
2. Be polite and helpful, not robotic
3. Vary the phrasing - don't always say the same thing
4. Examples of good refusals:
   - "I couldn't find that information in the provided context."
   - "The context doesn't mention [topic]."
   - "That information isn't available in the files I searched."
   - "I don't see any details about [topic] in the context."
5. Never apologize excessively or sound overly formal"""

USER_PROMPT_TEMPLATE = """Context and Question:
{input}

The factual answer extracted from the context is: {extractive_answer}

Rewrite this as a helpful, conversational response (1-2 sentences only):"""

# =============================================================================
# SETUP
# =============================================================================

print("=" * 70)
print("ASYNC CONVERSATIONAL DATA GENERATION (Optimized)")
print("=" * 70)

api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    print("\n❌ ERROR: ANTHROPIC_API_KEY environment variable not set!")
    exit(1)

client = anthropic.AsyncAnthropic(api_key=api_key)
print(f"\n✓ Anthropic async client initialized")

# =============================================================================
# LOAD DATA
# =============================================================================

print(f"\n📥 Loading source data...")

positive_examples = []
negative_examples = []
data_dir = Path("./data")

if GENERATE_TYPE in ["positive", "both"]:
    print(f"\n   Loading POSITIVE examples...")
    for source_file in POSITIVE_SOURCE_FILES:
        file_path = data_dir / source_file
        if file_path.exists():
            with open(file_path) as f:
                examples = [json.loads(line) for line in f]
                positive = [ex for ex in examples if "not found" not in ex["output"].lower()]
                positive_examples.extend(positive)
                print(f"   Loaded {len(positive):,} from {source_file}")

if GENERATE_TYPE in ["negative", "both"]:
    print(f"\n   Loading NEGATIVE examples...")
    for source_file in NEGATIVE_SOURCE_FILES:
        file_path = data_dir / source_file
        if file_path.exists():
            with open(file_path) as f:
                examples = [json.loads(line) for line in f]
                negative = [ex for ex in examples if "not found" in ex["output"].lower()]
                negative_examples.extend(negative)
                print(f"   Loaded {len(negative):,} from {source_file}")

print(f"\n   Total positive: {len(positive_examples):,}")
print(f"   Total negative: {len(negative_examples):,}")

# =============================================================================
# ASYNC GENERATION
# =============================================================================

async def generate_one(input_text: str, extractive_answer: str, is_negative: bool, semaphore) -> str:
    """Generate one conversational answer with semaphore for rate limiting"""

    async with semaphore:  # Limit concurrency
        system_prompt = SYSTEM_PROMPT_NEGATIVE if is_negative else SYSTEM_PROMPT_POSITIVE

        user_message = USER_PROMPT_TEMPLATE.format(
            input=input_text,
            extractive_answer=extractive_answer
        )

        try:
            response = await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=150,
                temperature=0.7,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            return response.content[0].text.strip()

        except anthropic.RateLimitError:
            # Retry after delay
            await asyncio.sleep(5)
            return await generate_one(input_text, extractive_answer, is_negative, semaphore)

        except Exception as e:
            print(f"\n   Error: {e}")
            return extractive_answer  # Fallback


async def process_batch(examples, is_negative: bool, label: str):
    """Process a batch of examples in parallel"""

    if not examples:
        return []

    print(f"\n🤖 Generating {label}...")
    print(f"   Examples: {len(examples):,}")
    print(f"   Concurrency: {MAX_CONCURRENT_REQUESTS}x parallel")
    print(f"   Estimated time: {len(examples) / MAX_CONCURRENT_REQUESTS / 1.5 / 60:.1f} minutes")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    # Create tasks for all examples
    tasks = [
        generate_one(ex["input"], ex["output"], is_negative, semaphore)
        for ex in examples
    ]

    # Run all tasks with progress bar
    results = await tqdm_asyncio.gather(*tasks, desc=f"Generating {label}")

    # Package results
    conversational = []
    failed = 0
    for i, (ex, result) in enumerate(zip(examples, results)):
        if len(result) < 5:
            failed += 1
            result = ex["output"]

        conversational.append({
            "input": ex["input"],
            "output": result,
            "original_extractive": ex["output"]
        })

    print(f"   ✓ Generated {len(conversational):,} examples")
    print(f"   ⚠️  Failed/fallback: {failed}")

    return conversational


async def main():
    """Main async execution"""

    # Sample examples
    positive_sample = []
    negative_sample = []

    if GENERATE_TYPE in ["positive", "both"] and positive_examples:
        if GENERATE_TYPE == "both":
            num_positive = int(NUM_EXAMPLES_TO_GENERATE * 0.75)
        else:
            num_positive = NUM_EXAMPLES_TO_GENERATE

        num_positive = min(num_positive, len(positive_examples))
        random.shuffle(positive_examples)
        positive_sample = positive_examples[:num_positive]

    if GENERATE_TYPE in ["negative", "both"] and negative_examples:
        if GENERATE_TYPE == "both":
            num_negative = int(NUM_EXAMPLES_TO_GENERATE * 0.25)
        else:
            num_negative = NUM_EXAMPLES_TO_GENERATE

        num_negative = min(num_negative, len(negative_examples))
        random.shuffle(negative_examples)
        negative_sample = negative_examples[:num_negative]

    # Process batches
    positive_conv = await process_batch(
        positive_sample,
        is_negative=False,
        label="positive conversational answers"
    )

    negative_conv = await process_batch(
        negative_sample,
        is_negative=True,
        label="negative conversational refusals"
    )

    # Save results
    print(f"\n💾 Saving output files...")

    if positive_conv:
        output_path = Path(OUTPUT_FILE_POSITIVE)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for ex in positive_conv:
                f.write(json.dumps({"input": ex["input"], "output": ex["output"]}) + "\n")
        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"   ✓ Positive: {len(positive_conv):,} examples ({size_mb:.1f} MB)")
        print(f"     {OUTPUT_FILE_POSITIVE}")

    if negative_conv:
        output_path = Path(OUTPUT_FILE_NEGATIVE)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for ex in negative_conv:
                f.write(json.dumps({"input": ex["input"], "output": ex["output"]}) + "\n")
        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"   ✓ Negative: {len(negative_conv):,} examples ({size_mb:.1f} MB)")
        print(f"     {OUTPUT_FILE_NEGATIVE}")

    # Show examples
    print("\n" + "=" * 70)
    print("SAMPLE EXAMPLES")
    print("=" * 70)

    if positive_conv:
        print("\n🟢 POSITIVE:")
        ex = positive_conv[0]
        print(f"Original: {ex['original_extractive']}")
        print(f"New:      {ex['output']}")

    if negative_conv:
        print("\n🔴 NEGATIVE:")
        ex = negative_conv[0]
        print(f"Original: {ex['original_extractive']}")
        print(f"New:      {ex['output']}")

    print("\n" + "=" * 70)
    print("✅ ASYNC GENERATION COMPLETE")
    print("=" * 70)

# Run
if __name__ == "__main__":
    asyncio.run(main())
