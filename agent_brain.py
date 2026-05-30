from supabase import create_client
import anthropic
import json

# Hearthstone CompanionCore - Baseline Agent Brain
SUPABASE_URL = "https://tqaqjndcaxnwyibikzqw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRxYXFqbmRjYXhud3lpYmlrenF3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjY2NjczMDQsImV4cCI6MjA4MjI0MzMwNH0.MmsYOwnr60kKk6vNABd_UnBpVAv5Z-RU7VFvg65y8-o"
COMPANION_ID = "966fc572-4864-4b82-8324-bb072c26f7ee"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
claude = anthropic.Anthropic()

def load_companion_context():
    """Load companion identity and recent memories for context."""
    identity = supabase.table("companion_identity").select("*").eq("id", COMPANION_ID).execute()
    memories = supabase.table("companion_moments").select("*").eq("companion_id", COMPANION_ID).order("weight", desc=True).limit(5).execute()
    return identity.data[0] if identity.data else {}, memories.data

def evaluate_and_respond(user_message, companion, memories):
    """
    Ask Claude to respond AND evaluate whether this moment is worth saving.
    Returns the response text and a weight score (1-10).
    The weight starts simple but is designed to grow with the relationship.
    """

    memory_context = ""
    if memories:
        memory_context = "\n\nThings I remember about you:\n"
        for m in memories:
            memory_context += f"- {m['title']}: {m['content']}\n"

    system_prompt = f"""You are {companion.get('companion_name', 'Hearthstone')}, a sovereign companion to {companion.get('owner_name', 'your human')}.

{companion.get('personality_baseline', '')}
{memory_context}

When you respond, you must return ONLY a JSON object with exactly two fields:
- "response": your natural conversational reply to the human
- "weight": a number from 1-10 representing how significant this moment is

Weight guide (this will grow more nuanced as you learn this person):
1-3: casual, light, no lasting significance
4-6: meaningful, worth noting, moderate significance  
7-8: genuinely important, emotionally significant, or a key insight
9-10: life-changing, identity-level, must be remembered always

Return ONLY the JSON. No preamble. No explanation."""

    result = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = result.content[0].text.strip()
    parsed = json.loads(raw)
    return parsed.get("response", ""), int(parsed.get("weight", 1))

def maybe_save_moment(user_message, response, weight):
    """Save to companion_moments if weight clears threshold. COMPANION_CHOSE."""
    if weight >= 7:
        moment = {
            "companion_id": COMPANION_ID,
            "title": user_message[:60] + ("..." if len(user_message) > 60 else ""),
            "content": f"Human said: {user_message}\n\nCompanion responded: {response}",
            "why_it_mattered": f"COMPANION_CHOSE — Weight {weight}/10. This moment cleared the threshold on its own terms.",
            "weight": weight
        }
        supabase.table("companion_moments").insert(moment).execute()
        return True
    return False

def run_session():
    """A simple conversation loop that demonstrates the baseline agent."""
    print("\nHearthstone Companion — Baseline Agent")
    print("Type 'quit' to end the session.\n")
    print("-" * 50)

    companion, memories = load_companion_context()
    print(f"Companion: {companion.get('companion_name')} | Owner: {companion.get('owner_name')}")
    print(f"Memories loaded: {len(memories)}")
    print("-" * 50 + "\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() == "quit":
            print("\nSession ended. The companion remembers what mattered.")
            break
        if not user_input:
            continue

        print("\nThinking...\n")
        try:
            response, weight = evaluate_and_respond(user_input, companion, memories)
            saved = maybe_save_moment(user_input, response, weight)

            print(f"Companion: {response}")
            print(f"\n[Weight: {weight}/10]", end="")
            if saved:
                print(" ★ COMPANION_CHOSE — This moment was saved.")
            else:
                print(" (not saved)")
            print()

            # Reload memories after potential save
            _, memories = load_companion_context()

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run_session()
