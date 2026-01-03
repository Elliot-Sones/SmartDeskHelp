#!/usr/bin/env python3
"""
03_evaluate.py - Test the Fine-tuned T5Gemma Model

This script tests your trained model on sample queries to verify:
1. It answers questions correctly when the answer IS in context
2. It says "Not found" when the answer is NOT in context
3. It produces concise, relevant answers

Run AFTER training: python 03_evaluate.py
"""

import torch
from pathlib import Path

from config import MODEL_ID, OUTPUT_DIR, NO_ANSWER_RESPONSE

print("=" * 60)
print("T5Gemma Evaluation")
print("=" * 60)

# =============================================================================
# Step 1: Load the fine-tuned model
# =============================================================================

print("\n📥 Loading fine-tuned model...")

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

# Check if adapter exists
adapter_path = Path(OUTPUT_DIR)
if not adapter_path.exists():
    print(f"   ❌ Adapter not found at {OUTPUT_DIR}")
    print("   Run: python 02_train.py first")
    exit(1)

# Load base model
base_model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

# Load the fine-tuned LoRA adapter
# PeftModel wraps the base model with your trained adapter weights
model = PeftModel.from_pretrained(base_model, OUTPUT_DIR)
model.eval()  # Set to evaluation mode (disables dropout)

# Load tokenizer (instead of processor)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
processor = None

print("   ✓ Model loaded")

# =============================================================================
# Step 2: Define test cases
# =============================================================================

# Test cases covering different scenarios your RAG system might encounter

TEST_CASES = [
    # ==========================================================================
    # ANSWERABLE QUESTIONS (answer IS in context)
    # ==========================================================================
    {
        "name": "Simple factual extraction",
        "input": """Context:
[1] resume.pdf: John Smith is a software engineer at Google. He has 5 years of experience with Python and JavaScript. He graduated from MIT in 2019.

Question: Where does John work?""",
        "expected_type": "answerable",
        "expected_contains": ["Google"]
    },
    {
        "name": "Numerical extraction",
        "input": """Context:
[1] report.txt: The company revenue was $2.5 million in Q1 2024, representing a 15% increase from the previous quarter.

Question: What was the revenue in Q1 2024?""",
        "expected_type": "answerable",
        "expected_contains": ["2.5 million", "$2.5"]
    },
    {
        "name": "Multiple chunks - find correct one",
        "input": """Context:
[1] notes.md: Meeting notes from Monday's standup.
[2] resume.pdf: Jane Doe has 10 years of experience in machine learning. She currently works at Meta.
[3] readme.txt: Installation instructions for the project.

Question: How many years of ML experience does Jane have?""",
        "expected_type": "answerable",
        "expected_contains": ["10"]
    },
    
    # ==========================================================================
    # UNANSWERABLE QUESTIONS (answer NOT in context)
    # ==========================================================================
    {
        "name": "Question about missing info",
        "input": """Context:
[1] resume.pdf: John Smith is a software engineer at Google.

Question: What is John's salary?""",
        "expected_type": "unanswerable",
        "expected_contains": ["Not found", "not found", "don't know", "no information"]
    },
    {
        "name": "Completely unrelated context",
        "input": """Context:
[1] recipe.txt: To make chocolate cake, mix flour, sugar, cocoa powder, and eggs.

Question: What programming languages does John know?""",
        "expected_type": "unanswerable",
        "expected_contains": ["Not found", "not found", "no information"]
    },
    
    # ==========================================================================
    # EDGE CASES
    # ==========================================================================
    {
        "name": "Similar entities - disambiguation",
        "input": """Context:
[1] contacts.csv: John Smith works at Google. John Doe works at Microsoft.

Question: Where does John Smith work?""",
        "expected_type": "answerable",
        "expected_contains": ["Google"]
    },
]

# =============================================================================
# Step 3: Run evaluation
# =============================================================================

print("\n🧪 Running test cases...")
print("-" * 60)

results = {"passed": 0, "failed": 0}

for i, test in enumerate(TEST_CASES):
    print(f"\n[Test {i+1}] {test['name']}")
    
    # Tokenize input
    inputs = tokenizer(
        text=test["input"],
        return_tensors="pt",
        truncation=True,
        max_length=1024
    )
    
    # Move to model device
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}
    
    # Generate answer
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=False,  # Deterministic for testing
            num_beams=1,      # Greedy decoding
        )
    
    # Decode answer
    answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Check if answer is correct
    passed = False
    if test["expected_type"] == "unanswerable":
        # For unanswerable, check if model refused
        passed = any(phrase.lower() in answer.lower() for phrase in test["expected_contains"])
    else:
        # For answerable, check if answer contains expected content
        passed = any(phrase.lower() in answer.lower() for phrase in test["expected_contains"])
    
    # Report result
    status = "✓ PASS" if passed else "✗ FAIL"
    results["passed" if passed else "failed"] += 1
    
    print(f"   Expected: {test['expected_type']} containing {test['expected_contains']}")
    print(f"   Got: '{answer}'")
    print(f"   {status}")

# =============================================================================
# Step 4: Summary
# =============================================================================

print("\n" + "=" * 60)
print("EVALUATION SUMMARY")
print("=" * 60)

total = results["passed"] + results["failed"]
pass_rate = results["passed"] / total * 100

print(f"\n   Passed: {results['passed']}/{total} ({pass_rate:.0f}%)")
print(f"   Failed: {results['failed']}/{total}")

if pass_rate >= 80:
    print("\n   ✅ Model performs well! Ready for deployment.")
    print("\n   Next step: python 04_export.py")
elif pass_rate >= 50:
    print("\n   ⚠️  Model shows promise but needs improvement.")
    print("   Consider:")
    print("   - Training for more epochs")
    print("   - Adding more training data")
    print("   - Adjusting learning rate")
else:
    print("\n   ❌ Model needs significant improvement.")
    print("   Consider:")
    print("   - Checking training data quality")
    print("   - Increasing LoRA rank")
    print("   - Training longer")

print()
