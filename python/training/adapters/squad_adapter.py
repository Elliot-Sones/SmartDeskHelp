"""
SQuAD 2.0 Adapter - Layer 1: Core Extraction

Downloads SQuAD 2.0 and adapts ONLY answerable examples to our chunk format.
Applies format variance to prevent format overfitting.
"""

import json
import random
from pathlib import Path
from datasets import load_dataset
from config import FORMAT_TEMPLATES, CHUNK_TEMPLATES, LAYER_1_SIZE

def adapt_squad_example(example: dict, format_template: str, chunk_template: str) -> dict:
    """Convert a single SQuAD example to our training format."""
    context = example["context"]
    question = example["question"]
    
    # Skip unanswerable examples (we'll add controlled negatives in Layer 5)
    if not example["answers"]["text"]:
        return None
    
    answer = example["answers"]["text"][0]
    
    # Format the chunk
    chunk = chunk_template.format(
        idx=1,
        source="document",
        content=context
    )
    
    # Handle different format variations
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=context,
        chunks_kv=f"content={context}",
        chunks_escaped=context.replace('"', '\\"'),
        chunks_messy=context,
        question=question
    )
    
    return {
        "input": input_text,
        "output": answer,
        "source": "squad_v2",
        "layer": 1
    }

def generate_squad_dataset(output_path: str, num_examples: int = LAYER_1_SIZE):
    """Generate Layer 1 dataset from SQuAD 2.0."""
    print(f"Loading SQuAD 2.0...")
    dataset = load_dataset("rajpurkar/squad_v2", split="train")
    
    examples = []
    format_count = len(FORMAT_TEMPLATES)
    chunk_count = len(CHUNK_TEMPLATES)
    
    print(f"Processing {len(dataset)} examples...")
    
    for i, example in enumerate(dataset):
        if len(examples) >= num_examples:
            break
        
        # Rotate through format/chunk templates for variance
        format_template = FORMAT_TEMPLATES[i % format_count]
        chunk_template = CHUNK_TEMPLATES[i % chunk_count]
        
        adapted = adapt_squad_example(example, format_template, chunk_template)
        if adapted:
            examples.append(adapted)
    
    # Shuffle
    random.shuffle(examples)
    
    # Save
    output_file = Path(output_path) / "layer1_squad.jsonl"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"Saved {len(examples)} examples to {output_file}")
    return examples[:10]  # Return sample for preview

if __name__ == "__main__":
    samples = generate_squad_dataset("./data/generated")
    print("\n=== Sample Examples ===\n")
    for i, ex in enumerate(samples[:5]):
        print(f"--- Example {i+1} ---")
        print(f"INPUT:\n{ex['input'][:300]}...")
        print(f"\nOUTPUT: {ex['output']}")
        print()
