
import random

# =============================================================================
# MOCKED FORMATTING LOGIC (Copied from 01_prepare_data.py)
# =============================================================================

CONTEXT_TEMPLATE = """Context:
{chunks}

Question: {question}"""
CHUNK_TEMPLATE = "[{index}] {source}: {content}"
NO_ANSWER_RESPONSE = "Not found in provided context."

def format_easy(context, question, answer):
    formatted_input = f"""Context:
{context[:300]}

Question: {question}"""
    return {"input": formatted_input, "output": answer}

def format_medium(context, question, answer):
    formatted_input = f"""Context:
[1] document.txt: {context[:500]}

Question: {question}"""
    return {"input": formatted_input, "output": answer}

def format_hard(context, question, answer, distractor_text):
    chunks = [f"[1] document.txt: {context[:500]}"]
    chunks.append(f"[2] other_file.txt: {distractor_text[:200]}")
    # Shuffle for realism
    # random.shuffle(chunks) (Deterministically keep order for demo clarity)
    
    formatted_input = f"""Context:
{chr(10).join(chunks)}

Question: {question}"""
    return {"input": formatted_input, "output": answer}

def create_negative(question, wrong_context):
    formatted_input = f"""Context:
[1] unrelated.txt: {wrong_context[:400]}

Question: {question}"""
    return {"input": formatted_input, "output": NO_ANSWER_RESPONSE}

# =============================================================================
# REAL SQuAD DATA SAMPLES (Beyonce, iPod, Chopin, etc.)
# =============================================================================

samples = [
    {
        "context": "Beyoncé Giselle Knowles-Carter (born September 4, 1981) is an American singer, songwriter, record producer, and actress. Born and raised in Houston, Texas, she performed in various singing and dancing competitions as a child, and rose to fame in the late 1990s as lead singer of R&B girl-group Destiny's Child.",
        "question": "When did Beyonce rise to fame?",
        "answer": "late 1990s"
    },
    {
        "context": "The iPod is a line of portable media players and multi-purpose pocket computers designed and marketed by Apple Inc. The first version was released on October 23, 2001, about 8 1/2 months after the Macintosh version of iTunes was released.",
        "question": "When was the first iPod released?",
        "answer": "October 23, 2001"
    },
    {
        "context": "Frédéric François Chopin was a Polish composer and virtuoso pianist of the Romantic era who wrote primarily for solo piano. He has maintained worldwide renown as a leading musician of his era, one whose poetic genius was based on a professional technique that was without equal in his generation.",
        "question": "What instrument did Chopin primarily write for?",
        "answer": "solo piano"
    },
    {
        "context": "New York City (NYC), often called the City of New York, is the most populous city in the United States. With an estimated 2019 population of 8,336,817 distributed over about 302.6 square miles (784 km2), New York is also the most densely populated major city in the United States.",
        "question": "What is the estimated 2019 population of NYC?",
        "answer": "8,336,817"
    },
    {
        "context": "Photosynthesis is a process used by plants and other organisms to convert light energy into chemical energy that can later be released to fuel the organisms' activities. This chemical energy is stored in carbohydrate molecules, such as sugars, which are synthesized from carbon dioxide and water.",
        "question": "What is chemical energy stored in?",
        "answer": "carbohydrate molecules"
    },
    {
        "context": "The Amazon River in South America is the largest river by discharge volume of water in the world, and by some definitions it is the longest. The headwaters of the Apurímac River on Nevado Mismi had been considered for nearly a century as the Amazon's most distant source.",
        "question": "Where is the Amazon River located?",
        "answer": "South America"
    },
    {
        "context": "Computational complexity theory is a branch of the theory of computation in theoretical computer science that focuses on classifying computational problems according to their inherent difficulty, and relating those classes to each other.",
        "question": "What does computational complexity theory focus on?",
        "answer": "classifying computational problems"
    },
    {
        "context": "The Normans (Norman: Nourmands; French: Normands; Latin: Normanni) were the people who in the 10th and 11th centuries gave their name to Normandy, a region in France. They were descended from Norse ('Norman' comes from 'Norseman') raiders and pirates from Denmark, Iceland and Norway.",
        "question": "Where do the Normans get their name from?",
        "answer": "Norseman"
    },
    {
        "context": "Matter is any substance that has mass and takes up space by having volume. All everyday objects that can be touched are ultimately composed of atoms, which are made up of interacting subatomic particles, and in everyday as well as scientific usage, 'matter' generally includes atoms and anything made up of them.",
        "question": "What corresponds to any substance that has mass and takes up space?",
        "answer": "Matter"
    },
    {
        "context": "In Greek mythology, Apollo is one of the most important and complex of the Olympian deities in classical Greek and Roman religion and Greek and Roman mythology. The ideal of the kouros (a beardless, athletic youth), Apollo has been recognized as a god of archery, music and dance, truth and prophecy.",
        "question": "Who is considered a god of archery?",
        "answer": "Apollo"
    }
]

distractor = "This is unrelated text about a completely different topic just to add noise to the context."

print("="*60)
print("PHASE 1: EASY EXAMPLES")
print("(Teaches basic Q->A format, no noise)")
print("="*60)
for i, s in enumerate(samples[:3]):
    formatted = format_easy(s["context"], s["question"], s["answer"])
    print(f"\n[Example 1.{i+1}]")
    print(f"INPUT:\n---\n{formatted['input']}\n---")
    print(f"OUTPUT: {formatted['output']}")

print("\n\n" + "="*60)
print("PHASE 2: MEDIUM EXAMPLES")
print("(Teaches chunk formatting, full paragraphs)")
print("="*60)
for i, s in enumerate(samples[3:6]):
    formatted = format_medium(s["context"], s["question"], s["answer"])
    print(f"\n[Example 2.{i+1}]")
    print(f"INPUT:\n---\n{formatted['input']}\n---")
    print(f"OUTPUT: {formatted['output']}")

print("\n\n" + "="*60)
print("PHASE 3: HARD EXAMPLES (Positive)")
print("(Teaches extraction from multi-chunk noise)")
print("="*60)
for i, s in enumerate(samples[6:9]):
    formatted = format_hard(s["context"], s["question"], s["answer"], distractor)
    print(f"\n[Example 3.{i+1}]")
    print(f"INPUT:\n---\n{formatted['input']}\n---")
    print(f"OUTPUT: {formatted['output']}")

print("\n\n" + "="*60)
print("PHASE 3: HARD EXAMPLES (Negative/Refusal)")
print("(Teaches to say 'Not found' when info is missing)")
print("="*60)
# Create a negative using the last sample
s = samples[9]
formatted = create_negative(s["question"], "This text is about cooking pasta. It mentions nothing about Greek gods.")
print(f"\n[Example 3.4 (Negative)]")
print(f"INPUT:\n---\n{formatted['input']}\n---")
print(f"OUTPUT: {formatted['output']}")
