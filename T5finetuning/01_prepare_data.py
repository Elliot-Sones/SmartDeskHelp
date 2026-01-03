#!/usr/bin/env python3
"""
01_prepare_data.py - Prepare Training Data for T5Gemma Fine-tuning

CURRICULUM LEARNING APPROACH:
Since T5Gemma base model has NEVER been trained on Q&A format,
we use curriculum learning to teach it progressively:

Phase 1 (Easy): Simple single-sentence extraction
  - Short context, obvious answer
  - Teaches: "Output a SHORT answer, don't repeat input"

Phase 2 (Medium): Paragraph-level extraction  
  - Longer context, answer is one sentence within it
  - Teaches: "Find the RIGHT sentence, then extract"

Phase 3 (Hard): Multi-chunk with distractors + negatives
  - Multiple chunks, some irrelevant
  - Some unanswerable questions
  - Teaches: "Pick correct chunk, know when to refuse"

Run: python 01_prepare_data.py
Output: ./data/train.jsonl (ordered by difficulty)
"""

import json
import random
import os
from pathlib import Path
from tqdm import tqdm

# Increase download timeout for slow connections (default is 10s)
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300" 
os.environ["HF_DATASETS_CONNECTION_TIMEOUT"] = "300"

from config import (
    NUM_TRAIN_EXAMPLES,
    NEGATIVE_EXAMPLE_RATIO,
    CONTEXT_TEMPLATE,
    CHUNK_TEMPLATE,
    NO_ANSWER_RESPONSE,
)

print("=" * 60)
print("T5Gemma Data Preparation (Curriculum Learning)")
print("=" * 60)

# =============================================================================
# Step 1: Load datasets
# =============================================================================

print("\n📥 Loading datasets from HuggingFace (Streaming Mode)...")

from datasets import load_dataset

# =============================================================================
# Step 1: Load datasets
# =============================================================================

print("\n📥 Loading datasets...")

from datasets import load_dataset
import requests

def download_squad_manual():
    """Fallback: Download SQuAD 2.0 JSON directly if HF fails"""
    url = "https://rajpurkar.github.io/SQuAD-explorer/dataset/train-v2.0.json"
    print(f"   ⚠️  HF Hub failed. Downloading directly from: {url}")
    
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    data = response.json()
    
    # Flatten SQuAD JSON structure to list of examples
    examples = []
    for article in data['data']:
        for paragraph in article['paragraphs']:
            context = paragraph['context']
            for qa in paragraph['qas']:
                examples.append({
                    "context": context,
                    "question": qa['question'],
                    "answers": {"text": [a['text'] for a in qa['answers']]},
                    "is_impossible": qa['is_impossible']
                })
    return examples

try:
    print("   Attempting streaming download from HuggingFace...")
    squad_stream = load_dataset("squad_v2", split="train", streaming=True)
    
    # Buffer examples - increased to 200k to capture FULL dataset (~130k)
    BUFFER_SIZE = 200000
    print(f"   Buffering {BUFFER_SIZE:,} examples (Targeting FULL dataset)...")
    squad = []
    for i, ex in enumerate(tqdm(squad_stream, total=BUFFER_SIZE, desc="Downloading")):
        squad.append(ex)
        if i >= BUFFER_SIZE - 1:
            break
            
except Exception as e:
    print(f"   ❌ HuggingFace Error: {e}")
    print("   🔄 Switching to manual download fallback...")
    squad = download_squad_manual()
    # No limit for manual download fallback either
    # if len(squad) > 5000:
    #     import random
    #     random.shuffle(squad)
    #     squad = squad[:5000]

print(f"   Loaded {len(squad):,} examples")

# =============================================================================
# Step 2: Classify examples by difficulty
# =============================================================================

print("\n📊 Classifying examples by difficulty...")

def get_difficulty(example: dict) -> str:
    """
    Classify an example as EASY, MEDIUM, or HARD based on:
    - Context length
    - Answer complexity
    - Whether it's answerable
    """
    context = example["context"]
    is_impossible = example.get("is_impossible", False)
    
    # Unanswerable = HARD (model must learn to refuse)
    if is_impossible:
        return "hard"
    
    # Check if answers list is empty (can happen in SQuAD)
    if not example["answers"]["text"]:
         return "hard"
         
    answer = example["answers"]["text"][0]
    context_sentences = context.count('.') + context.count('!') + context.count('?')
    
    # EASY: Short context (1-2 sentences) AND short answer (1-3 words)
    if context_sentences <= 2 and len(answer.split()) <= 3:
        return "easy"
    
    # EASY: Very short context regardless of answer
    if len(context) < 150:
        return "easy"
    
    # MEDIUM: Medium context (3-5 sentences) OR medium answer
    if context_sentences <= 5 or len(context) < 400:
        return "medium"
    
    # HARD: Long context, requires finding needle in haystack
    return "hard"


# Classify all buffered examples
easy_examples = []
medium_examples = []
hard_examples = []

for example in tqdm(squad, desc="Classifying difficulty"):
    difficulty = get_difficulty(example)
    if difficulty == "easy":
        easy_examples.append(example)
    elif difficulty == "medium":
        medium_examples.append(example)
    else:
        hard_examples.append(example)

print(f"\n   Easy: {len(easy_examples):,} examples")
print(f"   Medium: {len(medium_examples):,} examples")
print(f"   Hard: {len(hard_examples):,} examples")

# =============================================================================
# Step 3: Define formatting functions for each difficulty level
# =============================================================================

def format_easy(example: dict) -> dict:
    """
    EASY format: Single chunk, minimal context
    
    Goal: Teach the model "Question → Short Answer" pattern
    No distractors, just learn the basic format.
    """
    context = example["context"]
    question = example["question"]
    answer = example["answers"]["text"][0]
    
    # Simple format - just the context, no chunk numbering for easiest examples
    # This teaches pure extraction first
    formatted_input = f"""Context:
{context[:300]}

Question: {question}"""
    
    return {
        "input": formatted_input,
        "output": answer,
        "difficulty": "easy"
    }


def format_medium(example: dict) -> dict:
    """
    MEDIUM format: Single chunk with proper formatting
    
    Goal: Teach the model to work with the chunk format
    Still no distractors, but using production-like formatting.
    """
    context = example["context"]
    question = example["question"]
    answer = example["answers"]["text"][0]
    
    # Use chunk format like production
    formatted_input = f"""Context:
[1] document.txt: {context[:500]}

Question: {question}"""
    
    return {
        "input": formatted_input,
        "output": answer,
        "difficulty": "medium"
    }


def format_hard(example: dict, all_examples: list) -> dict:
    """
    HARD format: Multi-chunk with distractors
    
    Goal: Teach the model to:
    1. Find the relevant chunk among noise
    2. Handle longer contexts
    3. Refuse when unanswerable
    """
    context = example["context"]
    question = example["question"]
    is_impossible = example.get("is_impossible", False)
    
    if is_impossible or len(example["answers"]["text"]) == 0:
        answer = NO_ANSWER_RESPONSE
    else:
        answer = example["answers"]["text"][0]
    
    # Add distractor chunks
    chunks = [f"[1] document.txt: {context[:500]}"]
    
    # Add 1-2 distractor chunks from random other examples
    num_distractors = random.randint(1, 2)
    for i in range(num_distractors):
        distractor_example = random.choice(all_examples)
        distractor_context = distractor_example["context"][:200]
        chunks.append(f"[{i+2}] other_file.txt: {distractor_context}")
    
    # Randomly shuffle chunks so relevant one isn't always first
    if random.random() < 0.5:
        random.shuffle(chunks)
    
    formatted_input = f"""Context:
{chr(10).join(chunks)}

Question: {question}"""
    
    return {
        "input": formatted_input,
        "output": answer,
        "difficulty": "hard"
    }


def create_negative_example(all_examples: list) -> dict:
    """
    Create a negative example: question with UNRELATED context.
    Model must learn to say "Not found".
    """
    example = random.choice(all_examples)
    question = example["question"]
    
    # Get completely unrelated context
    wrong_example = random.choice(all_examples)
    while wrong_example["context"] == example["context"]:
        wrong_example = random.choice(all_examples)
    
    wrong_context = wrong_example["context"][:400]
    
    # Maybe add distractors too
    chunks = [f"[1] unrelated.txt: {wrong_context}"]
    if random.random() < 0.5:
        another = random.choice(all_examples)["context"][:200]
        chunks.append(f"[2] another.txt: {another}")
    
    formatted_input = f"""Context:
{chr(10).join(chunks)}

Question: {question}"""
    
    return {
        "input": formatted_input,
        "output": NO_ANSWER_RESPONSE,
        "difficulty": "hard"
    }


# =============================================================================
# Step 4: Build curriculum-ordered dataset
# =============================================================================

print("\n⚙️  Building curriculum-ordered dataset...")

# Calculate how many of each difficulty we need
# Split: 25% easy, 35% medium, 40% hard
num_easy = int(NUM_TRAIN_EXAMPLES * 0.25)
num_medium = int(NUM_TRAIN_EXAMPLES * 0.35)
num_hard = int(NUM_TRAIN_EXAMPLES * 0.40)

# Calculate negatives (from the hard portion)
num_negatives = int(NUM_TRAIN_EXAMPLES * NEGATIVE_EXAMPLE_RATIO)
num_hard_positives = num_hard - num_negatives

print(f"   Target distribution:")
print(f"   - Easy: {num_easy:,} (25%)")
print(f"   - Medium: {num_medium:,} (35%)")
print(f"   - Hard (positive): {num_hard_positives:,}")
print(f"   - Hard (negative): {num_negatives:,} ({NEGATIVE_EXAMPLE_RATIO:.0%})")

# Sample and format each difficulty level
print("\n   Formatting easy examples...")
random.shuffle(easy_examples)
formatted_easy = [format_easy(ex) for ex in tqdm(easy_examples[:num_easy], desc="Easy")]

print("   Formatting medium examples...")
random.shuffle(medium_examples)
formatted_medium = [format_medium(ex) for ex in tqdm(medium_examples[:num_medium], desc="Medium")]

print("   Formatting hard examples...")
random.shuffle(hard_examples)
formatted_hard = [format_hard(ex, list(squad)) for ex in tqdm(hard_examples[:num_hard_positives], desc="Hard")]

print("   Creating negative examples...")
formatted_negatives = [create_negative_example(list(squad)) for _ in tqdm(range(num_negatives), desc="Negatives")]

# =============================================================================
# Step 5: Shuffle within phases (but keep phases separate)
# =============================================================================

print("\n📚 Shuffling within each phase...")

random.shuffle(formatted_easy)
random.shuffle(formatted_medium)

# Combine hard positives and negatives, then shuffle
formatted_hard_all = formatted_hard + formatted_negatives
random.shuffle(formatted_hard_all)

print(f"   Phase 1 (Easy): {len(formatted_easy):,} examples")
print(f"   Phase 2 (Medium): {len(formatted_medium):,} examples")
print(f"   Phase 3 (Hard): {len(formatted_hard_all):,} examples")

# =============================================================================
# Step 6: Save SEPARATE files for each phase
# =============================================================================

print("\n💾 Saving to SEPARATE phase files...")

data_dir = Path("./data")
data_dir.mkdir(exist_ok=True)

def save_phase(examples, filename):
    path = data_dir / filename
    with open(path, "w") as f:
        for ex in examples:
            f.write(json.dumps({"input": ex["input"], "output": ex["output"]}) + "\n")
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"   {filename}: {len(examples):,} examples ({size_mb:.1f} MB)")
    return path

save_phase(formatted_easy, "train_easy.jsonl")
save_phase(formatted_medium, "train_medium.jsonl")
save_phase(formatted_hard_all, "train_hard.jsonl")

# =============================================================================
# Step 7: Show samples from each phase
# =============================================================================

print("\n📝 Sample examples from each phase:")
print("=" * 60)

print("\n🟢 PHASE 1 - EASY (train_easy.jsonl):")
print("-" * 60)
ex = formatted_easy[0]
print(f"Input:\n{ex['input'][:300]}...")
print(f"\nExpected Output: {ex['output']}")

print("\n🟡 PHASE 2 - MEDIUM (train_medium.jsonl):")
print("-" * 60)
ex = formatted_medium[0]
print(f"Input:\n{ex['input'][:400]}...")
print(f"\nExpected Output: {ex['output']}")

print("\n🔴 PHASE 3 - HARD (train_hard.jsonl):")
print("-" * 60)
ex = formatted_hard_all[0]
print(f"Input:\n{ex['input'][:500]}...")
print(f"\nExpected Output: {ex['output']}")

print("\n" + "=" * 60)
print("✅ Data preparation complete!")
print("=" * 60)
print("""
Output files:
  data/train_easy.jsonl   - Phase 1 (basic Q&A format)
  data/train_medium.jsonl - Phase 2 (chunk formatting)
  data/train_hard.jsonl   - Phase 3 (multi-chunk + negatives)

Training will process each phase sequentially.
Expected loss behavior:
  - Phase 1: Loss drops quickly (easy task)
  - Phase 2: Small bump, then drops (new format)
  - Phase 3: Larger bump, then converges (hard task)

Next step: python 02_train.py
""")
