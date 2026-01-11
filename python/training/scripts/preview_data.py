"""
Preview Script - Generate sample data from all layers

This script generates a small sample from each layer so you can see
what the training data will look like.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import *
import json
import random

def preview_squad():
    """Preview SQuAD examples without downloading full dataset."""
    print("\n" + "="*60)
    print("LAYER 1: SQuAD 2.0 (Core Extraction)")
    print("="*60)
    
    # Simulated SQuAD examples
    examples = [
        {
            "context": "The Apple M2 chip was announced in June 2022. It features 8 CPU cores, 10 GPU cores, and supports up to 24GB of unified memory.",
            "question": "How many CPU cores does the M2 chip have?",
            "answer": "8"
        },
        {
            "context": "Python was created by Guido van Rossum and first released in 1991. It is designed to emphasize code readability with its notable use of significant whitespace.",
            "question": "Who created Python?",
            "answer": "Guido van Rossum"
        },
        {
            "context": "The Great Wall of China is approximately 21,196 kilometers long. It was built over many centuries, with the most well-known sections dating to the Ming Dynasty.",
            "question": "How long is the Great Wall of China?",
            "answer": "21,196 kilometers"
        }
    ]
    
    for i, ex in enumerate(examples):
        fmt_idx = i % len(FORMAT_TEMPLATES)
        chunk_idx = i % len(CHUNK_TEMPLATES)
        
        chunk = CHUNK_TEMPLATES[chunk_idx].format(idx=1, source="document", content=ex['context'])
        
        input_text = FORMAT_TEMPLATES[fmt_idx].format(
            chunks=chunk,
            chunks_bullet=ex['context'],
            chunks_kv=f"content={ex['context']}",
            chunks_escaped=ex['context'].replace('"', '\\"'),
            chunks_messy=ex['context'],
            question=ex['question']
        )
        
        print(f"\n--- Example {i+1} (Format {fmt_idx+1}) ---")
        print(f"INPUT:\n{input_text}")
        print(f"\nOUTPUT: {ex['answer']}")

def preview_reasoning():
    """Preview reasoning examples."""
    print("\n" + "="*60)
    print("LAYER 2: Reasoning (HotpotQA, DROP, CoQA)")
    print("="*60)
    
    examples = [
        {
            "context": "[1] wiki_Python: Python is a high-level programming language created by Guido van Rossum.\n[2] wiki_Guido: Guido van Rossum is a Dutch programmer who was born in the Netherlands in 1956.",
            "question": "Where was the creator of Python born?",
            "answer": "the Netherlands",
            "type": "HotpotQA (multi-hop)"
        },
        {
            "context": "[1] stats: In the 2022 season, the team won 15 games and lost 8. In the playoffs, they won 4 additional games.",
            "question": "How many total games did the team win?",
            "answer": "19",
            "type": "DROP (numerical)"
        },
        {
            "context": "[1] story: Sarah went to the store to buy groceries. She picked up milk, bread, and eggs. At checkout, she realized she forgot her wallet.",
            "question": "What did Sarah forget?",
            "answer": "her wallet",
            "type": "CoQA (conversational)"
        }
    ]
    
    for ex in examples:
        print(f"\n--- {ex['type']} ---")
        print(f"INPUT:\nContext:\n{ex['context']}\n\nQuestion: {ex['question']}")
        print(f"\nOUTPUT: {ex['answer']}")

def preview_format_variance():
    """Preview format variance examples."""
    print("\n" + "="*60)
    print("LAYER 3: Format Variance (Same Q&A, Different Formats)")
    print("="*60)
    
    base_content = "CPU: Apple M2, 8 cores. RAM: 8GB total, 2GB free."
    question = "Why is my computer slow?"
    answer = "Only 2GB RAM free"
    
    print("\nShowing the SAME Q&A in 4 different formats:\n")
    
    for i, fmt in enumerate(FORMAT_TEMPLATES[:4]):
        chunk = CHUNK_TEMPLATES[i % len(CHUNK_TEMPLATES)].format(idx=1, source="system", content=base_content)
        
        input_text = fmt.format(
            chunks=chunk,
            chunks_bullet=base_content,
            chunks_kv=f"cpu=Apple M2 (8 cores)\nram=8GB total, 2GB free",
            chunks_escaped=base_content.replace('"', '\\"'),
            chunks_messy=base_content,
            question=question
        )
        
        print(f"--- Format {i+1} ---")
        print(f"INPUT:\n{input_text}")
        print(f"\nOUTPUT: {answer}\n")

def preview_domain():
    """Preview domain-specific examples."""
    print("\n" + "="*60)
    print("LAYER 4: Domain-Specific (Your Use Cases)")
    print("="*60)
    
    examples = [
        {
            "context": "[1] resume.pdf: Senior Software Engineer with 5 years of experience. Expert in Python, JavaScript, TypeScript, and Go. Built ML pipelines.",
            "question": "What programming languages do I know?",
            "answer": "Python, JavaScript, TypeScript, Go",
            "type": "File Content"
        },
        {
            "context": "[1] system: CPU: Apple M2, 8 cores. RAM: 8GB total, 2GB free. Chrome: 47 tabs open.",
            "question": "Why is my computer slow?",
            "answer": "Only 2GB RAM free with Chrome using 47 tabs",
            "type": "System Diagnostics"
        },
        {
            "context": "[1] memory: Works as a software engineer. Favorite language is Python. Lives in Montreal.",
            "question": "What's my favorite programming language?",
            "answer": "Python",
            "type": "Personal Memory"
        },
        {
            "context": "[1] todo.txt: 1. Fix auth bug (HIGH, due tomorrow). 2. Update docs (LOW). 3. Review PR (MEDIUM, due today).",
            "question": "What should I work on first?",
            "answer": "Review PR (due today) then fix auth bug (due tomorrow)",
            "type": "File + Reasoning"
        },
        {
            "context": "[1] system: RAM: 8GB. GPU: Intel UHD.\n[2] web: Game requires 16GB RAM, RTX 2060.",
            "question": "Can I run this game?",
            "answer": "No, need 16GB RAM (have 8GB) and RTX 2060 (have Intel UHD)",
            "type": "Comparison"
        }
    ]
    
    for ex in examples:
        print(f"\n--- {ex['type']} ---")
        print(f"INPUT:\nContext:\n{ex['context']}\n\nQuestion: {ex['question']}")
        print(f"\nOUTPUT: {ex['answer']}")

def preview_negatives():
    """Preview negative examples."""
    print("\n" + "="*60)
    print("LAYER 5: Negative Examples (Appropriate Refusal)")
    print("="*60)
    
    examples = [
        {
            "context": "[1] system: CPU: Apple M2. RAM: 8GB. Disk: 256GB SSD.",
            "question": "What does my resume say about my education?",
            "answer": NO_ANSWER,
            "reason": "Context is system info, not resume"
        },
        {
            "context": "[1] weather: Current: 15°C, partly cloudy in Montreal.",
            "question": "What will the weather be next week?",
            "answer": NO_ANSWER,
            "reason": "Future prediction not in context"
        },
        {
            "context": "[1] notes.md: Meeting on Tuesday. Location TBD. Attendees: Sarah, Mike.",
            "question": "Where is the meeting?",
            "answer": NO_ANSWER,
            "reason": "Location explicitly not determined"
        }
    ]
    
    for ex in examples:
        print(f"\n--- Negative: {ex['reason']} ---")
        print(f"INPUT:\nContext:\n{ex['context']}\n\nQuestion: {ex['question']}")
        print(f"\nOUTPUT: {ex['answer']}")

def main():
    print("\n" + "#"*60)
    print("# T5Gemma Training Data Preview")
    print("# Showing real examples from each layer")
    print("#"*60)
    
    preview_squad()
    preview_reasoning()
    preview_format_variance()
    preview_domain()
    preview_negatives()
    
    print("\n" + "="*60)
    print("SUMMARY: 5 Layers, ~55K Examples")
    print("="*60)
    print("""
Layer 1: SQuAD 2.0 (15K)     - Basic extraction from documents
Layer 2: Reasoning (15K)      - Multi-hop, numerical, conversational
Layer 3: Format Variance (10K) - Same Q&A in 8+ formats
Layer 4: Domain (10K)         - Your files, system, memory
Layer 5: Negatives (5K, 9%)   - Appropriate refusal
""")

if __name__ == "__main__":
    main()
