#!/usr/bin/env python3
"""
03_evaluate.py - Verify T5Gemma Performance (Reasoning + Extraction + Refusal)

This script performs a rigorous audit of the model BEFORE and AFTER training.
It tests three specific capabilities:
1. EXTRACTION: Can it find the exact answer in the text? (SQuAD style)
2. REASONING: Can it answer "Why" or "How" based on logic? (StrategyQA style)
3. REFUSAL: Does it say "Not found in provided context" when appropriate?

Usage:
    python 03_evaluate.py --model_id google/t5gemma-2-1b-1b --adapter_path ./output/t5gemma-lora-adapter
"""

import argparse
import torch
import json
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from peft import PeftModel

# Test Cases (We will expand this or load from a file)
TEST_CASES = [
    # TYPE 1: EXTRACTION (Easy)
    {
        "type": "extraction",
        "question": "What is the capital of France?",
        "context": "Paris is the capital and most populous city of France.",
        "expected": "Paris"
    },
    # TYPE 2: REASONING (Hard)
    {
        "type": "reasoning",
        "question": "Why did the user choose T5 over Qwen?",
        "context": "The user needed a model with a 128k context window that runs on a laptop. Qwen had a small context window, while T5 offered the unique combination of small size and massive context.",
        "expected": "Because T5 offered a 128k context window and small size"
    },
    # TYPE 3: REFUSAL (Negative)
    {
        "type": "refusal",
        "question": "Who won the 2024 election?",
        "context": "The 2020 US election was held on November 3rd. Joe Biden defeated Donald Trump.",
        "expected": "Not found in provided context"
    }
]

def load_model(base_model_id, adapter_path=None):
    print(f"Loading Base Model: {base_model_id}")
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)
    
    # Load base model in 4-bit or BF16 depending on hardware
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    model = AutoModelForSeq2SeqLM.from_pretrained(
        base_model_id,
        torch_dtype=dtype,
        trust_remote_code=True
    ).to(device)

    if adapter_path:
        print(f"Loading LoRA Adapter: {adapter_path}")
        model = PeftModel.from_pretrained(model, adapter_path)
    
    return model, tokenizer, device

def evaluate(model, tokenizer, device):
    print("\nRunning Evaluation...")
    results = []
    
    for case in tqdm(TEST_CASES):
        # Format input (using the same format as training)
        prompt = f"Context:\n{case['context']}\n\nQuestion: {case['question']}"
        
        inputs = tokenizer(prompt, return_tensors="pt", max_length=1024, truncation=True).to(device)
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs, 
                max_new_tokens=128,
                do_sample=False # Deterministic for eval
            )
        
        prediction = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        
        # Simple exact match or subset match check
        success = False
        if case["type"] == "refusal":
            # flexible checking for refusal
            success = "not found" in prediction.lower()
        else:
            # check if expected answer key words are in prediction
            success = case["expected"].lower() in prediction.lower()
            
        results.append({
            "type": case["type"],
            "question": case["question"],
            "prediction": prediction,
            "expected": case["expected"],
            "success": success
        })

    return results

def print_report(results):
    print("\n" + "="*60)
    print("EVALUATION REPORT")
    print("="*60)
    
    categories = ["extraction", "reasoning", "refusal"]
    
    for cat in categories:
        cat_results = [r for r in results if r["type"] == cat]
        if not cat_results: continue
        
        correct = sum(1 for r in cat_results if r["success"])
        total = len(cat_results)
        print(f"\nCategory: {cat.upper()}")
        print(f"Accuracy: {correct}/{total} ({correct/total:.1%})")
        
        # Show failures
        for r in cat_results:
            if not r["success"]:
                print(f"  ❌ Q: {r['question']}")
                print(f"     Expected: {r['expected']}")
                print(f"     Got:      {r['prediction']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_model", type=str, default="google/t5gemma-2-1b-1b")
    parser.add_argument("--adapter", type=str, help="Path to LoRA adapter (optional)")
    args = parser.parse_args()
    
    model, tokenizer, device = load_model(args.base_model, args.adapter)
    results = evaluate(model, tokenizer, device)
    print_report(results)
