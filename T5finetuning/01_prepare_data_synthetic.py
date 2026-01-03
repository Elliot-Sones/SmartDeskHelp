#!/usr/bin/env python3
"""
01_prepare_data_synthetic.py - Debug script to create data WITHOUT internet

This script creates 1,000 synthetic training examples locally.
It proves that the training logic works even if your internet is too slow
to download the full SQuAD dataset.

Run: python 01_prepare_data_synthetic.py
Then: python 02_train.py (It will train on this synthetic data)
"""

import json
import random
import time
from pathlib import Path

# Config
NUM_EXAMPLES = 1000
OUTPUT_DIR = Path("./data")

print("=" * 60)
print("Generating SYNTHETIC Training Data (No Internet Required)")
print("=" * 60)

# Sample data to mix and match
ENTITIES = ["John", "Sarah", "The server", "Project X", "The API"]
ACTIONS = ["works at", "failed with", "deployed to", "started at", "connected to"]
OBJECTS = ["Google", "Error 500", "production", "10:00 AM", "database"]

DISTRACTOR_TEXTS = [
    "This is a random text about cooking pasta.",
    "The weather today is sunny with a chance of rain.",
    "Python is a programming language created by Guido van Rossum.",
    "The quick brown fox jumps over the lazy dog.",
]

def generate_example(i):
    """Generates a random valid training example"""
    
    # 1. Create a "fact"
    entity = random.choice(ENTITIES)
    action = random.choice(ACTIONS)
    obj = random.choice(OBJECTS)
    
    fact = f"{entity} {action} {obj}."
    question = f"Who {action} {obj}?" if random.random() < 0.5 else f"Where/What did {entity} {action}?"
    
    # 2. Determine complexity (Curriculum Phase)
    phase = i % 3  # 0=Easy, 1=Medium, 2=Hard
    
    if phase == 0:
        # Easy: Just the fact
        context = f"Context:\n{fact}\n\nQuestion: {question}"
        answer = entity if "Who" in question else obj
        
    elif phase == 1:
        # Medium: Chunk format
        context = f"Context:\n[1] log.txt: {fact} Additional details here.\n\nQuestion: {question}"
        answer = entity if "Who" in question else obj
        
    else:
        # Hard: Distractors
        chunks = [f"[1] log.txt: {fact}"]
        chunks.append(f"[2] noise.txt: {random.choice(DISTRACTOR_TEXTS)}")
        random.shuffle(chunks)
        context = f"Context:\n{chr(10).join(chunks)}\n\nQuestion: {question}"
        answer = entity if "Who" in question else obj
        
        # 10% chance of "Not Found" logic
        if random.random() < 0.1:
            context = f"Context:\n[1] noise.txt: {random.choice(DISTRACTOR_TEXTS)}\n\nQuestion: {question}"
            answer = "Not found in provided context."

    return {"input": context, "output": answer}

print("\n⚙️  Generating examples...")
examples = []
for i in range(NUM_EXAMPLES):
    examples.append(generate_example(i))

print(f"   Generated {len(examples)} examples.")

# Save
OUTPUT_DIR.mkdir(exist_ok=True)
output_path = OUTPUT_DIR / "train.jsonl"

with open(output_path, "w") as f:
    for ex in examples:
        f.write(json.dumps(ex) + "\n")

print(f"\n💾 Saved to {output_path}")
print(f"   You can now run 'python 02_train.py' to verify the TRAINING code.")
