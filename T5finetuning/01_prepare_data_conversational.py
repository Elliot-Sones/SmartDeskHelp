#!/usr/bin/env python3
"""
01_prepare_data_conversational.py - Generate Conversational Training Data

WHAT THIS SCRIPT DOES:
======================
1. Loads your existing SQuAD-based extractive data (from 01_prepare_data.py)
2. For each example, sends it to Claude Haiku with a prompt
3. Claude Haiku rewrites the terse answer as a conversational response
4. Saves the new (input, conversational_output) pairs for training

EXAMPLE TRANSFORMATION:
=======================
BEFORE (extractive):
  Input:  "Context: [1] system.txt: RAM usage 7.8GB/8GB (97%)\nQuestion: Why is my computer slow?"
  Output: "RAM usage 7.8GB/8GB (97%)"

AFTER (conversational):
  Input:  "Context: [1] system.txt: RAM usage 7.8GB/8GB (97%)\nQuestion: Why is my computer slow?"
  Output: "Your computer is running slow because your RAM is nearly full at 97% (7.8GB out of 8GB). Try closing some applications to free up memory."

Run: python 01_prepare_data_conversational.py
Requires: ANTHROPIC_API_KEY environment variable
"""

import json
import os
import time
import random
from pathlib import Path
from tqdm import tqdm
import anthropic

# =============================================================================
# CONFIGURATION
# =============================================================================

# How many examples to generate (start small to test, then scale up)
NUM_EXAMPLES_TO_GENERATE = 100  # TEST MODE: 100 examples (change to full number for GPU)

# Which phase files to use as source (from 01_prepare_data.py)
# SEPARATE POSITIVE AND NEGATIVE EXAMPLES
POSITIVE_SOURCE_FILES = [
    "generated/layer1_squad.jsonl",      # Extractive examples
    "generated/layer2_reasoning.jsonl",  # Reasoning examples
]

NEGATIVE_SOURCE_FILES = [
    "generated/layer5_negatives.jsonl",  # Refusal examples
]

# Output files (separate for positive and negative)
OUTPUT_FILE_POSITIVE = "./data/generated/train_conversational_positive.jsonl"
OUTPUT_FILE_NEGATIVE = "./data/generated/train_conversational_negative.jsonl"

# Which type to generate (set via command line or change here)
GENERATE_TYPE = "both"  # Options: "positive", "negative", "both"

# Rate limiting (Haiku is fast, but be respectful)
REQUESTS_PER_MINUTE = 500  # Haiku limit is higher, but be safe
DELAY_BETWEEN_REQUESTS = 60 / REQUESTS_PER_MINUTE  # seconds

# =============================================================================
# THE PROMPT THAT CONTROLS OUTPUT STYLE
# =============================================================================

# This is the EXACT prompt sent to Claude Haiku.
# The output style is determined by this prompt.
# Modify this to change how conversational the answers are.

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
# STEP 1: Initialize Anthropic Client
# =============================================================================

print("=" * 70)
print("CONVERSATIONAL DATA GENERATION (Using Claude Haiku)")
print("=" * 70)

# Check for API key
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    print("\n❌ ERROR: ANTHROPIC_API_KEY environment variable not set!")
    print("   Run: export ANTHROPIC_API_KEY='your-key-here'")
    exit(1)

client = anthropic.Anthropic(api_key=api_key)
print(f"\n✓ Anthropic client initialized")

# =============================================================================
# STEP 2: Load Source Data
# =============================================================================

print(f"\n📥 Loading source data...")

positive_examples = []
negative_examples = []
data_dir = Path("./data")

if GENERATE_TYPE in ["positive", "both"]:
    print(f"\n   Loading POSITIVE examples (answers found)...")
    for source_file in POSITIVE_SOURCE_FILES:
        file_path = data_dir / source_file
        if file_path.exists():
            with open(file_path) as f:
                examples = [json.loads(line) for line in f]
                # Filter out "Not found" examples
                positive = [ex for ex in examples if "not found" not in ex["output"].lower()]
                positive_examples.extend(positive)
                print(f"   Loaded {len(positive):,} positive from {source_file}")
        else:
            print(f"   ⚠️  Not found: {source_file}")

if GENERATE_TYPE in ["negative", "both"]:
    print(f"\n   Loading NEGATIVE examples (refusals)...")
    for source_file in NEGATIVE_SOURCE_FILES:
        file_path = data_dir / source_file
        if file_path.exists():
            with open(file_path) as f:
                examples = [json.loads(line) for line in f]
                # Filter for "Not found" examples
                negative = [ex for ex in examples if "not found" in ex["output"].lower()]
                negative_examples.extend(negative)
                print(f"   Loaded {len(negative):,} negative from {source_file}")
        else:
            print(f"   ⚠️  Not found: {source_file}")

print(f"\n   Total positive examples: {len(positive_examples):,}")
print(f"   Total negative examples: {len(negative_examples):,}")

# =============================================================================
# STEP 3: Generate Conversational Answers
# =============================================================================

def generate_conversational_answer(input_text: str, extractive_answer: str, is_negative: bool = False) -> str:
    """
    Send one example to Claude Haiku and get conversational response.

    Args:
        input_text: The full "Context: ... Question: ..." string
        extractive_answer: The short extracted answer (e.g., "RAM usage 97%")
        is_negative: True if this is a refusal example

    Returns:
        Conversational answer string (e.g., "Your RAM is at 97%, which...")
    """

    system_prompt = SYSTEM_PROMPT_NEGATIVE if is_negative else SYSTEM_PROMPT_POSITIVE

    user_message = USER_PROMPT_TEMPLATE.format(
        input=input_text,
        extractive_answer=extractive_answer
    )

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=150,  # Conversational answers should be short
            temperature=0.7,  # Some variety, but not too random
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        return response.content[0].text.strip()

    except anthropic.RateLimitError:
        print("   Rate limited, waiting 60s...")
        time.sleep(60)
        return generate_conversational_answer(input_text, extractive_answer, is_negative)

    except Exception as e:
        print(f"   Error: {e}")
        return extractive_answer  # Fallback to original


def process_examples(examples, is_negative, label):
    """Process a list of examples through Haiku"""
    if not examples:
        print(f"   Skipping {label} (no examples)")
        return []

    print(f"\n🤖 Generating {label} with Claude Haiku...")
    print(f"   Examples: {len(examples):,}")
    print(f"   Estimated time: {len(examples) * DELAY_BETWEEN_REQUESTS / 60:.1f} minutes")
    print(f"   Estimated cost: ${len(examples) * 0.00003:.2f}")

    conversational_examples = []
    failed_count = 0

    for i, example in enumerate(tqdm(examples, desc=f"Generating {label}")):

        # Get conversational version from Haiku
        conv_answer = generate_conversational_answer(
            input_text=example["input"],
            extractive_answer=example["output"],
            is_negative=is_negative
        )

        # Validate the response (basic checks)
        if len(conv_answer) < 5:
            failed_count += 1
            conv_answer = example["output"]  # Fallback

        conversational_examples.append({
            "input": example["input"],
            "output": conv_answer,
            "original_extractive": example["output"]  # Keep for debugging
        })

        # Rate limiting
        if i < len(examples) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

        # Progress update every 500
        if (i + 1) % 500 == 0:
            print(f"\n   Processed {i+1:,}/{len(examples):,} examples")

    print(f"\n   ✓ Generated {len(conversational_examples):,} {label}")
    print(f"   ⚠️  Failed/fallback: {failed_count}")

    return conversational_examples


# Process positive examples
positive_conversational = []
if GENERATE_TYPE in ["positive", "both"] and positive_examples:
    # Sample based on NUM_EXAMPLES_TO_GENERATE
    # For "both" mode: split the budget 75% positive, 25% negative
    if GENERATE_TYPE == "both":
        num_positive = int(NUM_EXAMPLES_TO_GENERATE * 0.75)  # 75 out of 100 for test
    else:
        num_positive = NUM_EXAMPLES_TO_GENERATE

    num_positive = min(num_positive, len(positive_examples))
    random.shuffle(positive_examples)
    positive_conversational = process_examples(
        positive_examples[:num_positive],
        is_negative=False,
        label="positive conversational answers"
    )

# Process negative examples
negative_conversational = []
if GENERATE_TYPE in ["negative", "both"] and negative_examples:
    # Sample based on NUM_EXAMPLES_TO_GENERATE
    # For "both" mode: split the budget 75% positive, 25% negative
    if GENERATE_TYPE == "both":
        num_negative = int(NUM_EXAMPLES_TO_GENERATE * 0.25)  # 25 out of 100 for test
    else:
        num_negative = NUM_EXAMPLES_TO_GENERATE

    num_negative = min(num_negative, len(negative_examples))
    random.shuffle(negative_examples)
    negative_conversational = process_examples(
        negative_examples[:num_negative],
        is_negative=True,
        label="negative conversational refusals"
    )

# =============================================================================
# STEP 4: Save Output
# =============================================================================

print(f"\n💾 Saving output files...")

def save_examples(examples, output_path, label):
    """Save examples to file"""
    if not examples:
        print(f"   Skipping {label} (no examples)")
        return

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for ex in examples:
            # Save only input/output (not the debug field)
            f.write(json.dumps({
                "input": ex["input"],
                "output": ex["output"]
            }) + "\n")

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"   Saved {label}: {len(examples):,} examples ({size_mb:.1f} MB)")
    print(f"   Location: {output_path}")

# Save positive examples
if positive_conversational:
    save_examples(
        positive_conversational,
        OUTPUT_FILE_POSITIVE,
        "positive conversational answers"
    )

# Save negative examples
if negative_conversational:
    save_examples(
        negative_conversational,
        OUTPUT_FILE_NEGATIVE,
        "negative conversational refusals"
    )

# =============================================================================
# STEP 5: Show Examples
# =============================================================================

print("\n" + "=" * 70)
print("EXAMPLE TRANSFORMATIONS")
print("=" * 70)

if positive_conversational:
    print("\n🟢 POSITIVE EXAMPLES (Answers Found):")
    print("-" * 70)
    for i in range(min(3, len(positive_conversational))):
        ex = positive_conversational[i]
        print(f"\n--- Example {i+1} ---")
        print(f"Input (first 200 chars):\n{ex['input'][:200]}...")
        print(f"\nOriginal (extractive): {ex['original_extractive']}")
        print(f"New (conversational):  {ex['output']}")

if negative_conversational:
    print("\n🔴 NEGATIVE EXAMPLES (Refusals):")
    print("-" * 70)
    for i in range(min(3, len(negative_conversational))):
        ex = negative_conversational[i]
        print(f"\n--- Example {i+1} ---")
        print(f"Input (first 200 chars):\n{ex['input'][:200]}...")
        print(f"\nOriginal (extractive): {ex['original_extractive']}")
        print(f"New (conversational):  {ex['output']}")

print("\n" + "=" * 70)
print("✅ CONVERSATIONAL DATA GENERATION COMPLETE")
print("=" * 70)

summary = []
if positive_conversational:
    summary.append(f"Positive: {OUTPUT_FILE_POSITIVE} ({len(positive_conversational):,} examples)")
if negative_conversational:
    summary.append(f"Negative: {OUTPUT_FILE_NEGATIVE} ({len(negative_conversational):,} examples)")

print(f"""
Output files:
  {chr(10).join('  ' + s for s in summary)}

Next step: Update 02_train.py PHASES configuration:

PHASES = [
    ("🟢 PHASE 1: EXTRACTION", "generated/layer1_squad.jsonl", "Extractive foundation"),
    ("🔵 PHASE 2: CONVERSATIONAL", "generated/train_conversational_positive.jsonl", "Natural answers"),
    ("🟠 PHASE 3: REFUSALS", "generated/train_conversational_negative.jsonl", "Polite refusals"),
]

This gives you a consistent conversational model.
""")
