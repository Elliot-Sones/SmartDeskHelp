"""
Reasoning Dataset Adapters - Layer 2: Inference & Multi-hop

Downloads and adapts:
- HotpotQA (multi-hop reasoning)
- DROP (numerical reasoning)
- CoQA (conversational reasoning)
"""

import json
import random
from pathlib import Path
from datasets import load_dataset
from config import FORMAT_TEMPLATES, CHUNK_TEMPLATES, LAYER_2_SIZE

def adapt_hotpotqa(example: dict, format_idx: int) -> dict:
    """Adapt HotpotQA example - multi-hop reasoning."""
    # HotpotQA has multiple supporting facts from different documents
    context_parts = []
    for i, (title, sentences) in enumerate(zip(example["context"]["title"], example["context"]["sentences"])):
        content = " ".join(sentences)
        chunk_template = CHUNK_TEMPLATES[i % len(CHUNK_TEMPLATES)]
        context_parts.append(chunk_template.format(idx=i+1, source=title, content=content))
    
    chunks = "\n".join(context_parts)
    question = example["question"]
    answer = example["answer"]
    
    format_template = FORMAT_TEMPLATES[format_idx % len(FORMAT_TEMPLATES)]
    input_text = format_template.format(
        chunks=chunks,
        chunks_bullet=chunks.replace("[", "• "),
        chunks_kv=chunks,
        chunks_escaped=chunks.replace('"', '\\"'),
        chunks_messy=chunks,
        question=question
    )
    
    return {
        "input": input_text,
        "output": answer,
        "source": "hotpotqa",
        "layer": 2
    }

def adapt_drop(example: dict, format_idx: int) -> dict:
    """Adapt DROP example - numerical reasoning."""
    context = example["passage"]
    question = example["question"]
    
    # DROP answers can be spans, numbers, or dates
    answer_info = example["answers_spans"]
    if answer_info["spans"]:
        answer = answer_info["spans"][0]
    else:
        return None  # Skip complex multi-span answers
    
    chunk_template = CHUNK_TEMPLATES[format_idx % len(CHUNK_TEMPLATES)]
    chunk = chunk_template.format(idx=1, source="document", content=context)
    
    format_template = FORMAT_TEMPLATES[format_idx % len(FORMAT_TEMPLATES)]
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=context,
        chunks_kv=f"passage={context}",
        chunks_escaped=context.replace('"', '\\"'),
        chunks_messy=context,
        question=question
    )
    
    return {
        "input": input_text,
        "output": answer,
        "source": "drop",
        "layer": 2
    }

def adapt_coqa(example: dict, format_idx: int) -> dict:
    """Adapt CoQA example - conversational reasoning."""
    context = example["story"]
    # CoQA has multiple Q&A turns - we'll use one at a time
    questions = example["questions"]
    answers = example["answers"]["input_text"]
    
    if not questions or not answers:
        return None
    
    # Pick a random Q&A turn
    turn_idx = random.randint(0, len(questions) - 1)
    question = questions[turn_idx]
    answer = answers[turn_idx]
    
    chunk_template = CHUNK_TEMPLATES[format_idx % len(CHUNK_TEMPLATES)]
    chunk = chunk_template.format(idx=1, source="story", content=context)
    
    format_template = FORMAT_TEMPLATES[format_idx % len(FORMAT_TEMPLATES)]
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=context,
        chunks_kv=f"story={context}",
        chunks_escaped=context.replace('"', '\\"'),
        chunks_messy=context,
        question=question
    )
    
    return {
        "input": input_text,
        "output": answer,
        "source": "coqa",
        "layer": 2
    }

def generate_reasoning_dataset(output_path: str, num_examples: int = LAYER_2_SIZE):
    """Generate Layer 2 dataset from reasoning datasets."""
    examples = []
    per_dataset = num_examples // 3
    
    # HotpotQA
    print("Loading HotpotQA...")
    try:
        hotpot = load_dataset("hotpot_qa", "distractor", split="train")
        for i, ex in enumerate(hotpot):
            if len([e for e in examples if e["source"] == "hotpotqa"]) >= per_dataset:
                break
            adapted = adapt_hotpotqa(ex, i)
            if adapted:
                examples.append(adapted)
        print(f"  Added {len([e for e in examples if e['source'] == 'hotpotqa'])} HotpotQA examples")
    except Exception as e:
        print(f"  HotpotQA failed: {e}")
    
    # DROP
    print("Loading DROP...")
    try:
        drop = load_dataset("ucinlp/drop", split="train")
        for i, ex in enumerate(drop):
            if len([e for e in examples if e["source"] == "drop"]) >= per_dataset:
                break
            adapted = adapt_drop(ex, i)
            if adapted:
                examples.append(adapted)
        print(f"  Added {len([e for e in examples if e['source'] == 'drop'])} DROP examples")
    except Exception as e:
        print(f"  DROP failed: {e}")
    
    # CoQA
    print("Loading CoQA...")
    try:
        coqa = load_dataset("stanfordnlp/coqa", split="train")
        for i, ex in enumerate(coqa):
            if len([e for e in examples if e["source"] == "coqa"]) >= per_dataset:
                break
            adapted = adapt_coqa(ex, i)
            if adapted:
                examples.append(adapted)
        print(f"  Added {len([e for e in examples if e['source'] == 'coqa'])} CoQA examples")
    except Exception as e:
        print(f"  CoQA failed: {e}")
    
    # Shuffle
    random.shuffle(examples)
    
    # Save
    output_file = Path(output_path) / "layer2_reasoning.jsonl"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"Saved {len(examples)} examples to {output_file}")
    return examples[:10]

if __name__ == "__main__":
    samples = generate_reasoning_dataset("./data/generated")
    print("\n=== Sample Reasoning Examples ===\n")
    for i, ex in enumerate(samples[:5]):
        print(f"--- {ex['source'].upper()} Example ---")
        print(f"INPUT:\n{ex['input'][:400]}...")
        print(f"\nOUTPUT: {ex['output']}")
        print()
