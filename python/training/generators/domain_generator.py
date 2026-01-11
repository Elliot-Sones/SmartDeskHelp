"""
Domain-Specific Generator - Layer 4: Your Use Cases

Generates synthetic examples for:
- File content queries ("What does my resume say...")
- System diagnostics ("Why is my computer slow")
- Personal memory ("What's my favorite...")
- Mixed multi-source contexts
- Comparison/decision queries
"""

import json
import random
from pathlib import Path
from config import FORMAT_TEMPLATES, CHUNK_TEMPLATES, LAYER_4_SIZE, NO_ANSWER

# Content pools for realistic synthetic data
SYSTEM_SPECS = [
    {"cpu": "Apple M2", "cores": 8, "ram_total": "8GB", "ram_free": "2GB", "disk": "256GB SSD", "disk_free": "48GB"},
    {"cpu": "Apple M3 Pro", "cores": 12, "ram_total": "18GB", "ram_free": "6GB", "disk": "512GB SSD", "disk_free": "200GB"},
    {"cpu": "Intel i7-12700", "cores": 12, "ram_total": "32GB", "ram_free": "12GB", "disk": "1TB SSD", "disk_free": "400GB"},
    {"cpu": "AMD Ryzen 9 5900X", "cores": 12, "ram_total": "64GB", "ram_free": "32GB", "disk": "2TB NVMe", "disk_free": "1.2TB"},
    {"cpu": "Apple M1", "cores": 8, "ram_total": "8GB", "ram_free": "1GB", "disk": "256GB SSD", "disk_free": "20GB"},
]

PERSONAL_FACTS = [
    {"name": "Alex", "job": "software engineer", "company": "tech startup", "fav_lang": "Python", "city": "Montreal", "interests": ["AI/ML", "gaming", "music"]},
    {"name": "Jordan", "job": "data scientist", "company": "finance firm", "fav_lang": "R", "city": "Toronto", "interests": ["statistics", "hiking", "cooking"]},
    {"name": "Sam", "job": "frontend developer", "company": "agency", "fav_lang": "TypeScript", "city": "Vancouver", "interests": ["UI design", "photography", "travel"]},
]

FILE_CONTENTS = [
    {"name": "resume.pdf", "content": "Senior Software Engineer with 5 years of experience. Led implementation of real-time search system using Elasticsearch. Expert in Python, JavaScript, TypeScript, and Go. Built ML pipelines for NLP tasks."},
    {"name": "project_notes.md", "content": "Project Alpha: Using FastAPI for backend, React for frontend. Timeline: 3 months. Team: 4 developers. Status: In development, 60% complete."},
    {"name": "todo.txt", "content": "1. Fix auth bug (HIGH priority, due tomorrow). 2. Update docs (LOW). 3. Review PR from Sarah (MEDIUM, due today). 4. Deploy to staging."},
    {"name": "meeting_notes.md", "content": "Meeting with client on Tuesday 2pm. Discuss Q1 roadmap, budget increase request, and hiring timeline. Location: Zoom call."},
    {"name": "config.py", "content": "DATABASE_URL = 'postgresql://localhost:5432/myapp'. DEBUG = True. MAX_CONNECTIONS = 100. CACHE_TTL = 3600."},
]

WEB_RESULTS = [
    {"query": "weather Montreal", "result": "Current weather: 15°C, partly cloudy. Humidity: 65%. Wind: 12 km/h. Forecast: High 18°C, low 10°C."},
    {"query": "Python 3.12 features", "result": "Python 3.12 introduces improved error messages, f-string improvements, and 5% faster execution. Released October 2023."},
    {"query": "Cyberpunk 2077 requirements", "result": "Minimum: 8GB RAM, GTX 1060, 70GB storage. Recommended: 16GB RAM, RTX 2060, SSD for faster loading."},
]

def generate_system_example(format_idx: int) -> dict:
    """Generate a system info query example."""
    spec = random.choice(SYSTEM_SPECS)
    
    # Format the system info in various ways
    formats = [
        f"CPU: {spec['cpu']}, {spec['cores']} cores. RAM: {spec['ram_total']} total, {spec['ram_free']} free. Disk: {spec['disk']}, {spec['disk_free']} free.",
        f"System specs - {spec['cpu']} ({spec['cores']}c), Memory: {spec['ram_total']} ({spec['ram_free']} available), Storage: {spec['disk']}",
        f"cpu={spec['cpu']}\ncores={spec['cores']}\nram={spec['ram_total']}\nram_free={spec['ram_free']}\ndisk={spec['disk_free']} free",
    ]
    
    content = random.choice(formats)
    chunk_template = CHUNK_TEMPLATES[format_idx % len(CHUNK_TEMPLATES)]
    chunk = chunk_template.format(idx=1, source="system", content=content)
    
    # Questions and answers
    qa_pairs = [
        ("How much RAM do I have?", spec['ram_total']),
        ("How many CPU cores?", str(spec['cores'])),
        ("What CPU do I have?", spec['cpu']),
        ("How much free disk space?", spec['disk_free']),
        ("How much free RAM?", spec['ram_free']),
    ]
    
    # "Why slow" questions with reasoning
    ram_free_gb = float(spec['ram_free'].replace('GB', ''))
    if ram_free_gb <= 2:
        qa_pairs.append(("Why is my computer slow?", f"Only {spec['ram_free']} RAM free"))
    
    q, a = random.choice(qa_pairs)
    
    format_template = FORMAT_TEMPLATES[format_idx % len(FORMAT_TEMPLATES)]
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=content,
        chunks_kv=content,
        chunks_escaped=content.replace('"', '\\"'),
        chunks_messy=content,
        question=q
    )
    
    return {"input": input_text, "output": a, "source": "domain_system", "layer": 4}

def generate_file_example(format_idx: int) -> dict:
    """Generate a file content query example."""
    file = random.choice(FILE_CONTENTS)
    
    chunk_template = CHUNK_TEMPLATES[format_idx % len(CHUNK_TEMPLATES)]
    chunk = chunk_template.format(idx=1, source=file['name'], content=file['content'])
    
    # Generate question based on file type
    if "resume" in file['name']:
        qa_pairs = [
            ("What does my resume say about my experience?", "5 years of experience, led real-time search system, expert in Python, JavaScript, TypeScript, Go"),
            ("What programming languages do I know?", "Python, JavaScript, TypeScript, Go"),
            ("What's my job experience?", "Senior Software Engineer, 5 years, Elasticsearch, ML pipelines"),
        ]
    elif "todo" in file['name']:
        qa_pairs = [
            ("What should I work on first?", "Review PR from Sarah (due today) then fix auth bug (due tomorrow)"),
            ("What are my high priority tasks?", "Fix auth bug"),
            ("What's due today?", "Review PR from Sarah"),
        ]
    elif "meeting" in file['name']:
        qa_pairs = [
            ("When is my next meeting?", "Tuesday 2pm"),
            ("What's the meeting about?", "Q1 roadmap, budget increase, hiring timeline"),
        ]
    elif "project" in file['name']:
        qa_pairs = [
            ("What's Project Alpha using?", "FastAPI for backend, React for frontend"),
            ("How far along is the project?", "60% complete"),
            ("What's my current project status?", "In development, 60% complete"),
        ]
    else:
        qa_pairs = [
            ("What's in this file?", file['content'][:50]),
        ]
    
    q, a = random.choice(qa_pairs)
    
    format_template = FORMAT_TEMPLATES[format_idx % len(FORMAT_TEMPLATES)]
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=file['content'],
        chunks_kv=f"{file['name']}={file['content']}",
        chunks_escaped=file['content'].replace('"', '\\"'),
        chunks_messy=file['content'],
        question=q
    )
    
    return {"input": input_text, "output": a, "source": "domain_file", "layer": 4}

def generate_memory_example(format_idx: int) -> dict:
    """Generate a personal memory query example."""
    person = random.choice(PERSONAL_FACTS)
    
    content = f"Works as a {person['job']} at {person['company']}. Favorite programming language is {person['fav_lang']}. Lives in {person['city']}. Interested in {', '.join(person['interests'])}."
    
    chunk_template = CHUNK_TEMPLATES[format_idx % len(CHUNK_TEMPLATES)]
    chunk = chunk_template.format(idx=1, source="memory", content=content)
    
    qa_pairs = [
        ("What's my favorite programming language?", person['fav_lang']),
        ("Where do I live?", person['city']),
        ("What's my job?", person['job']),
        ("Where do I work?", person['company']),
        ("What are my interests?", ", ".join(person['interests'])),
    ]
    
    q, a = random.choice(qa_pairs)
    
    format_template = FORMAT_TEMPLATES[format_idx % len(FORMAT_TEMPLATES)]
    input_text = format_template.format(
        chunks=chunk,
        chunks_bullet=content,
        chunks_kv=content,
        chunks_escaped=content.replace('"', '\\"'),
        chunks_messy=content,
        question=q
    )
    
    return {"input": input_text, "output": a, "source": "domain_memory", "layer": 4}

def generate_mixed_example(format_idx: int) -> dict:
    """Generate a multi-source mixed context example."""
    spec = random.choice(SYSTEM_SPECS)
    file = random.choice(FILE_CONTENTS)
    person = random.choice(PERSONAL_FACTS)
    
    chunks = []
    chunk_template = CHUNK_TEMPLATES[format_idx % len(CHUNK_TEMPLATES)]
    
    chunks.append(chunk_template.format(idx=1, source=file['name'], content=file['content']))
    chunks.append(chunk_template.format(idx=2, source="system", content=f"CPU: {spec['cpu']}, RAM: {spec['ram_total']}"))
    chunks.append(chunk_template.format(idx=3, source="memory", content=f"Favorite language: {person['fav_lang']}. Lives in {person['city']}."))
    
    combined = "\n".join(chunks)
    
    # Question that needs info from specific chunk
    qa_pairs = [
        ("What's my favorite language?", person['fav_lang']),
        ("How much RAM do I have?", spec['ram_total']),
        ("What programming languages am I good at?", "Python, JavaScript, TypeScript, Go" if "resume" in file['name'] else person['fav_lang']),
    ]
    
    q, a = random.choice(qa_pairs)
    
    format_template = FORMAT_TEMPLATES[format_idx % len(FORMAT_TEMPLATES)]
    input_text = format_template.format(
        chunks=combined,
        chunks_bullet=combined.replace("[", "• "),
        chunks_kv=combined,
        chunks_escaped=combined.replace('"', '\\"'),
        chunks_messy=combined,
        question=q
    )
    
    return {"input": input_text, "output": a, "source": "domain_mixed", "layer": 4}

def generate_comparison_example(format_idx: int) -> dict:
    """Generate a comparison/decision query example."""
    spec = random.choice(SYSTEM_SPECS)
    game_req = random.choice(WEB_RESULTS)
    
    if "requirements" not in game_req['query']:
        game_req = {"query": "game requirements", "result": "Minimum: 16GB RAM, RTX 2060, 70GB storage. Recommended: 32GB RAM, RTX 3070."}
    
    chunks = []
    chunk_template = CHUNK_TEMPLATES[format_idx % len(CHUNK_TEMPLATES)]
    
    chunks.append(chunk_template.format(idx=1, source="system", content=f"RAM: {spec['ram_total']}. GPU: {spec['cpu']}. Free disk: {spec['disk_free']}."))
    chunks.append(chunk_template.format(idx=2, source="web", content=game_req['result']))
    
    combined = "\n".join(chunks)
    
    # Reasoning answer
    ram_gb = int(spec['ram_total'].replace('GB', ''))
    if ram_gb >= 16:
        answer = "Yes, meets minimum RAM requirement"
    else:
        answer = f"No, need 16GB RAM but only have {spec['ram_total']}"
    
    format_template = FORMAT_TEMPLATES[format_idx % len(FORMAT_TEMPLATES)]
    input_text = format_template.format(
        chunks=combined,
        chunks_bullet=combined,
        chunks_kv=combined,
        chunks_escaped=combined.replace('"', '\\"'),
        chunks_messy=combined,
        question="Can I run this game?"
    )
    
    return {"input": input_text, "output": answer, "source": "domain_comparison", "layer": 4}

def generate_domain_dataset(output_path: str, num_examples: int = LAYER_4_SIZE):
    """Generate Layer 4 domain-specific dataset."""
    examples = []
    per_type = num_examples // 5
    
    generators = [
        ("system", generate_system_example),
        ("file", generate_file_example),
        ("memory", generate_memory_example),
        ("mixed", generate_mixed_example),
        ("comparison", generate_comparison_example),
    ]
    
    for name, gen_func in generators:
        print(f"Generating {per_type} {name} examples...")
        for i in range(per_type):
            try:
                ex = gen_func(i)
                examples.append(ex)
            except Exception as e:
                print(f"  Error: {e}")
    
    random.shuffle(examples)
    
    output_file = Path(output_path) / "layer4_domain.jsonl"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"Saved {len(examples)} examples to {output_file}")
    return examples[:15]

if __name__ == "__main__":
    samples = generate_domain_dataset("./data/generated", num_examples=100)
    print("\n=== Sample Domain Examples ===\n")
    for ex in samples[:10]:
        print(f"--- {ex['source'].upper()} ---")
        print(f"INPUT:\n{ex['input'][:300]}...")
        print(f"\nOUTPUT: {ex['output']}")
        print()
