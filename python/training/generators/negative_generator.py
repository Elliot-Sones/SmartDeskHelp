"""
Negative Example Generator - Layer 5: Appropriate Refusal

Generates examples where the model should refuse to answer:
- Wrong domain (asking about files when context is system info)
- Out of scope (opinions, future predictions)
- Partial matches (related but not exact)
"""

import json
import random
from pathlib import Path
from config import FORMAT_TEMPLATES, CHUNK_TEMPLATES, LAYER_5_SIZE, NO_ANSWER

# Context pools that DON'T contain answers to the questions
SYSTEM_CONTEXTS = [
    "CPU: Apple M2, 8 cores. RAM: 8GB total, 2GB free. Disk: 256GB SSD.",
    "Running processes: Chrome, Slack, VS Code, Docker. CPU usage: 45%.",
    "Network: Connected to WiFi. Download: 50 Mbps. Upload: 10 Mbps.",
]

MEMORY_CONTEXTS = [
    "Works as a software engineer. Lives in Montreal. Interested in AI.",
    "Prefers dark mode. Uses VS Code. Favorite language is Python.",
    "Last project was a web scraper. Currently learning Rust.",
]

FILE_CONTEXTS = [
    "Project timeline: Q1 planning, Q2 development, Q3 testing, Q4 launch.",
    "Meeting notes from Tuesday: Discussed roadmap, assigned tasks to team.",
    "Budget report: Marketing $50K, Engineering $200K, Operations $30K.",
]

WEB_CONTEXTS = [
    "Weather in Montreal: 15°C, partly cloudy. Humidity: 65%.",
    "Python 3.12 features: Improved error messages, faster execution.",
    "Stock market today: S&P 500 up 0.5%, NASDAQ up 0.8%.",
]

def generate_wrong_domain() -> dict:
    """Generate example where question doesn't match context domain."""
    combinations = [
        (random.choice(SYSTEM_CONTEXTS), "system", "What does my resume say about my skills?"),
        (random.choice(SYSTEM_CONTEXTS), "system", "What's in my todo list?"),
        (random.choice(MEMORY_CONTEXTS), "memory", "How much disk space do I have?"),
        (random.choice(MEMORY_CONTEXTS), "memory", "What files are in my Documents folder?"),
        (random.choice(FILE_CONTEXTS), "notes.md", "What's the current weather?"),
        (random.choice(FILE_CONTEXTS), "report.pdf", "What time is my meeting?"),
        (random.choice(WEB_CONTEXTS), "web", "What's my favorite programming language?"),
    ]
    
    content, source, question = random.choice(combinations)
    
    fmt_idx = random.randint(0, len(FORMAT_TEMPLATES) - 1)
    chunk_template = CHUNK_TEMPLATES[fmt_idx % len(CHUNK_TEMPLATES)]
    chunk = chunk_template.format(idx=1, source=source, content=content)
    
    format_template = FORMAT_TEMPLATES[fmt_idx]
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=content,
        chunks_kv=f"{source}={content}",
        chunks_escaped=content.replace('"', '\\"'),
        chunks_messy=content,
        question=question
    )
    
    return {
        "input": input_text,
        "output": NO_ANSWER,
        "source": "negative_wrong_domain",
        "layer": 5
    }

def generate_out_of_scope() -> dict:
    """Generate example with out-of-scope questions (opinions, predictions)."""
    contexts = SYSTEM_CONTEXTS + MEMORY_CONTEXTS + FILE_CONTEXTS
    context = random.choice(contexts)
    source = random.choice(["document", "system", "memory"])
    
    out_of_scope_questions = [
        "What will the weather be next week?",
        "Should I buy this stock?",
        "Is Python better than JavaScript?",
        "Will AI take over my job?",
        "What will my salary be next year?",
        "Is this a good investment?",
        "How will the project turn out?",
        "What's the meaning of life?",
    ]
    
    question = random.choice(out_of_scope_questions)
    
    fmt_idx = random.randint(0, len(FORMAT_TEMPLATES) - 1)
    chunk_template = CHUNK_TEMPLATES[fmt_idx % len(CHUNK_TEMPLATES)]
    chunk = chunk_template.format(idx=1, source=source, content=context)
    
    format_template = FORMAT_TEMPLATES[fmt_idx]
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=context,
        chunks_kv=f"{source}={context}",
        chunks_escaped=context.replace('"', '\\"'),
        chunks_messy=context,
        question=question
    )
    
    return {
        "input": input_text,
        "output": NO_ANSWER,
        "source": "negative_out_of_scope",
        "layer": 5
    }

def generate_partial_match() -> dict:
    """Generate example where context has related but not exact info."""
    examples = [
        # Has meeting info but not location
        ("Meeting on Tuesday with Sarah and Mike. Topics: roadmap, budget.", "notes.md", "Where is the meeting located?"),
        # Has project info but not specific deadline
        ("Project Alpha: 60% complete. Team of 4 developers.", "project.md", "When is the project due?"),
        # Has personal info but not phone number
        ("Email: john@example.com. Lives in Montreal.", "contacts.txt", "What's my phone number?"),
        # Has weather but not for requested city
        ("Weather in Montreal: 15°C, sunny.", "web", "What's the weather in Toronto?"),
        # Has file list but not the requested file
        ("Files found: resume.pdf, notes.md, config.py", "search", "Show me my tax documents"),
    ]
    
    content, source, question = random.choice(examples)
    
    fmt_idx = random.randint(0, len(FORMAT_TEMPLATES) - 1)
    chunk_template = CHUNK_TEMPLATES[fmt_idx % len(CHUNK_TEMPLATES)]
    chunk = chunk_template.format(idx=1, source=source, content=content)
    
    format_template = FORMAT_TEMPLATES[fmt_idx]
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=content,
        chunks_kv=f"{source}={content}",
        chunks_escaped=content.replace('"', '\\"'),
        chunks_messy=content,
        question=question
    )
    
    return {
        "input": input_text,
        "output": NO_ANSWER,
        "source": "negative_partial_match",
        "layer": 5
    }

def generate_negative_dataset(output_path: str, num_examples: int = LAYER_5_SIZE):
    """Generate Layer 5 negative examples dataset."""
    examples = []
    
    generators = [
        ("wrong_domain", generate_wrong_domain, 0.40),
        ("out_of_scope", generate_out_of_scope, 0.35),
        ("partial_match", generate_partial_match, 0.25),
    ]
    
    for name, gen_func, ratio in generators:
        count = int(num_examples * ratio)
        print(f"Generating {count} {name} examples...")
        for _ in range(count):
            try:
                ex = gen_func()
                examples.append(ex)
            except Exception as e:
                print(f"  Error: {e}")
    
    random.shuffle(examples)
    
    output_file = Path(output_path) / "layer5_negatives.jsonl"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"Saved {len(examples)} examples to {output_file}")
    return examples[:10]

if __name__ == "__main__":
    samples = generate_negative_dataset("./data/generated", num_examples=100)
    print("\n=== Sample Negative Examples ===\n")
    for ex in samples[:5]:
        print(f"--- {ex['source']} ---")
        print(f"INPUT:\n{ex['input'][:300]}...")
        print(f"\nOUTPUT: {ex['output']}")
        print()
