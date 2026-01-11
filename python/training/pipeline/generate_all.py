"""
Master Pipeline - Generate Full 55K Dataset

Downloads all source datasets and generates the complete training data.
"""

import json
import random
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import *

def generate_layer1_squad(output_path: str, num_examples: int = 15000):
    """Layer 1: SQuAD 2.0 answerable examples."""
    from datasets import load_dataset
    
    print(f"\n{'='*60}")
    print("LAYER 1: Downloading SQuAD 2.0...")
    print(f"{'='*60}")
    
    dataset = load_dataset("rajpurkar/squad_v2", split="train")
    
    examples = []
    format_count = len(FORMAT_TEMPLATES)
    chunk_count = len(CHUNK_TEMPLATES)
    
    for i, ex in enumerate(dataset):
        if len(examples) >= num_examples:
            break
        
        # Skip unanswerable
        if not ex["answers"]["text"]:
            continue
        
        context = ex["context"]
        question = ex["question"]
        answer = ex["answers"]["text"][0]
        
        # Format variance
        fmt_idx = i % format_count
        chunk_idx = i % chunk_count
        
        chunk = CHUNK_TEMPLATES[chunk_idx].format(idx=1, source="document", content=context)
        
        input_text = FORMAT_TEMPLATES[fmt_idx].format(
            chunks=chunk,
            chunks_bullet=context,
            chunks_kv=f"content={context}",
            chunks_escaped=context.replace('"', '\\"')[:500],
            chunks_messy=context,
            question=question
        )
        
        examples.append({
            "input": input_text,
            "output": answer,
            "source": "squad_v2",
            "layer": 1
        })
        
        if len(examples) % 5000 == 0:
            print(f"  Processed {len(examples)} examples...")
    
    random.shuffle(examples)
    
    output_file = Path(output_path) / "layer1_squad.jsonl"
    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"  Saved {len(examples)} examples to {output_file}")
    return len(examples)

def generate_layer2_reasoning(output_path: str, num_examples: int = 15000):
    """Layer 2: Reasoning datasets (HotpotQA, DROP, CoQA)."""
    from datasets import load_dataset
    
    print(f"\n{'='*60}")
    print("LAYER 2: Downloading Reasoning Datasets...")
    print(f"{'='*60}")
    
    examples = []
    per_dataset = num_examples // 3
    
    # HotpotQA
    print("  Loading HotpotQA...")
    try:
        hotpot = load_dataset("hotpot_qa", "distractor", split="train")
        count = 0
        for i, ex in enumerate(hotpot):
            if count >= per_dataset:
                break
            
            # Combine supporting facts
            context_parts = []
            for j, (title, sentences) in enumerate(zip(ex["context"]["title"], ex["context"]["sentences"])):
                content = " ".join(sentences)
                chunk = CHUNK_TEMPLATES[j % len(CHUNK_TEMPLATES)].format(idx=j+1, source=title, content=content)
                context_parts.append(chunk)
            
            chunks = "\n".join(context_parts[:3])  # Limit to 3 chunks
            question = ex["question"]
            answer = ex["answer"]
            
            fmt_idx = i % len(FORMAT_TEMPLATES)
            input_text = FORMAT_TEMPLATES[fmt_idx].format(
                chunks=chunks,
                chunks_bullet=chunks,
                chunks_kv=chunks,
                chunks_escaped=chunks.replace('"', '\\"')[:500],
                chunks_messy=chunks,
                question=question
            )
            
            examples.append({
                "input": input_text,
                "output": answer,
                "source": "hotpotqa",
                "layer": 2
            })
            count += 1
        print(f"    Added {count} HotpotQA examples")
    except Exception as e:
        print(f"    HotpotQA error: {e}")
    
    # DROP
    print("  Loading DROP...")
    try:
        drop = load_dataset("ucinlp/drop", split="train")
        count = 0
        for i, ex in enumerate(drop):
            if count >= per_dataset:
                break
            
            context = ex["passage"]
            question = ex["question"]
            
            answer_info = ex["answers_spans"]
            if not answer_info["spans"]:
                continue
            answer = answer_info["spans"][0]
            
            chunk = CHUNK_TEMPLATES[i % len(CHUNK_TEMPLATES)].format(idx=1, source="document", content=context)
            
            fmt_idx = i % len(FORMAT_TEMPLATES)
            input_text = FORMAT_TEMPLATES[fmt_idx].format(
                chunks=chunk,
                chunks_bullet=context,
                chunks_kv=f"passage={context}",
                chunks_escaped=context.replace('"', '\\"')[:500],
                chunks_messy=context,
                question=question
            )
            
            examples.append({
                "input": input_text,
                "output": answer,
                "source": "drop",
                "layer": 2
            })
            count += 1
        print(f"    Added {count} DROP examples")
    except Exception as e:
        print(f"    DROP error: {e}")
    
    # CoQA
    print("  Loading CoQA...")
    try:
        coqa = load_dataset("stanfordnlp/coqa", split="train")
        count = 0
        for i, ex in enumerate(coqa):
            if count >= per_dataset:
                break
            
            context = ex["story"]
            questions = ex["questions"]
            answers = ex["answers"]["input_text"]
            
            if not questions or not answers:
                continue
            
            # Pick a Q&A turn
            turn_idx = i % len(questions)
            question = questions[turn_idx]
            answer = answers[turn_idx]
            
            chunk = CHUNK_TEMPLATES[i % len(CHUNK_TEMPLATES)].format(idx=1, source="story", content=context)
            
            fmt_idx = i % len(FORMAT_TEMPLATES)
            input_text = FORMAT_TEMPLATES[fmt_idx].format(
                chunks=chunk,
                chunks_bullet=context,
                chunks_kv=f"story={context}",
                chunks_escaped=context.replace('"', '\\"')[:500],
                chunks_messy=context,
                question=question
            )
            
            examples.append({
                "input": input_text,
                "output": answer,
                "source": "coqa",
                "layer": 2
            })
            count += 1
        print(f"    Added {count} CoQA examples")
    except Exception as e:
        print(f"    CoQA error: {e}")
    
    random.shuffle(examples)
    
    output_file = Path(output_path) / "layer2_reasoning.jsonl"
    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"  Saved {len(examples)} examples to {output_file}")
    return len(examples)

def generate_layer3_format_variance(output_path: str, num_examples: int = 10000):
    """Layer 3: Format variance - same Q&A in multiple formats."""
    from datasets import load_dataset
    
    print(f"\n{'='*60}")
    print("LAYER 3: Generating Format Variance...")
    print(f"{'='*60}")
    
    # Use SQuAD as base, apply all formats to each example
    dataset = load_dataset("rajpurkar/squad_v2", split="train")
    
    examples = []
    base_count = num_examples // len(FORMAT_TEMPLATES)
    
    count = 0
    for ex in dataset:
        if count >= base_count:
            break
        
        if not ex["answers"]["text"]:
            continue
        
        context = ex["context"]
        question = ex["question"]
        answer = ex["answers"]["text"][0]
        
        # Generate same Q&A in ALL formats
        for fmt_idx, fmt in enumerate(FORMAT_TEMPLATES):
            chunk = CHUNK_TEMPLATES[fmt_idx % len(CHUNK_TEMPLATES)].format(
                idx=1, source="document", content=context
            )
            
            input_text = fmt.format(
                chunks=chunk,
                chunks_bullet=context,
                chunks_kv=f"content={context}",
                chunks_escaped=context.replace('"', '\\"')[:500],
                chunks_messy=context,
                question=question
            )
            
            examples.append({
                "input": input_text,
                "output": answer,
                "source": f"format_variance_{fmt_idx}",
                "layer": 3
            })
        
        count += 1
        if count % 500 == 0:
            print(f"  Processed {count} base examples ({len(examples)} total with variants)...")
    
    random.shuffle(examples)
    
    output_file = Path(output_path) / "layer3_format_variance.jsonl"
    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"  Saved {len(examples)} examples to {output_file}")
    return len(examples)

def generate_layer4_domain(output_path: str, num_examples: int = 10000):
    """Layer 4: Domain-specific examples."""
    print(f"\n{'='*60}")
    print("LAYER 4: Generating Domain-Specific...")
    print(f"{'='*60}")
    
    sys.path.insert(0, str(Path(__file__).parent.parent / "generators"))
    from domain_generator import generate_domain_dataset
    
    examples = generate_domain_dataset(output_path, num_examples)
    return len(examples) if isinstance(examples, list) else num_examples

def generate_layer5_negatives(output_path: str, num_examples: int = 5000):
    """Layer 5: Negative examples."""
    print(f"\n{'='*60}")
    print("LAYER 5: Generating Negative Examples...")
    print(f"{'='*60}")
    
    sys.path.insert(0, str(Path(__file__).parent.parent / "generators"))
    from negative_generator import generate_negative_dataset
    
    examples = generate_negative_dataset(output_path, num_examples)
    return len(examples) if isinstance(examples, list) else num_examples

def combine_all_layers(output_path: str):
    """Combine all layer files into a single training dataset."""
    print(f"\n{'='*60}")
    print("COMBINING ALL LAYERS...")
    print(f"{'='*60}")
    
    all_examples = []
    path = Path(output_path)
    
    for layer_file in sorted(path.glob("layer*.jsonl")):
        print(f"  Reading {layer_file.name}...")
        with open(layer_file) as f:
            for line in f:
                all_examples.append(json.loads(line))
    
    # Curriculum order: layer 1 first, then by layer
    all_examples.sort(key=lambda x: x["layer"])
    
    # Shuffle within each layer, then interleave later layers
    final_examples = []
    for layer in range(1, 6):
        layer_examples = [e for e in all_examples if e["layer"] == layer]
        random.shuffle(layer_examples)
        final_examples.extend(layer_examples)
    
    # Save combined file
    combined_file = path / "train_combined.jsonl"
    with open(combined_file, "w") as f:
        for ex in final_examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"  Saved {len(final_examples)} total examples to {combined_file}")
    
    # Stats
    print(f"\n{'='*60}")
    print("DATASET STATISTICS")
    print(f"{'='*60}")
    
    layer_counts = {}
    source_counts = {}
    for ex in final_examples:
        layer = ex["layer"]
        source = ex["source"]
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
    
    print("\nBy Layer:")
    for layer in sorted(layer_counts.keys()):
        print(f"  Layer {layer}: {layer_counts[layer]:,} examples")
    
    print("\nBy Source:")
    for source in sorted(source_counts.keys()):
        print(f"  {source}: {source_counts[source]:,} examples")
    
    # File size
    size_bytes = combined_file.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    print(f"\nFile size: {size_mb:.2f} MB")
    
    return len(final_examples)

def main():
    output_path = Path(__file__).parent.parent.parent.parent / "T5finetuning" / "data" / "generated"
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'#'*60}")
    print("# T5Gemma Training Data Generation")
    print(f"# Output: {output_path}")
    print(f"{'#'*60}")
    
    total = 0
    
    # Generate each layer
    total += generate_layer1_squad(str(output_path), 15000)
    total += generate_layer2_reasoning(str(output_path), 15000)
    total += generate_layer3_format_variance(str(output_path), 10000)
    total += generate_layer4_domain(str(output_path), 10000)
    total += generate_layer5_negatives(str(output_path), 5000)
    
    # Combine
    combine_all_layers(str(output_path))
    
    print(f"\n{'#'*60}")
    print(f"# COMPLETE! Generated {total:,} examples")
    print(f"{'#'*60}")

if __name__ == "__main__":
    main()
