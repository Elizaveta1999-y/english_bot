import hashlib
from services.deepseek import chat
from data.users import get_user_state, add_to_history
from speaking.services.history import build_history_prompt

# Системный промпт (кешируется)
_cached_prompt = None
_cached_prompt_hash = None

def get_system_prompt(name: str, level: str) -> str:
    global _cached_prompt, _cached_prompt_hash
    prompt_hash = hashlib.md5(f"{name}_{level}".encode()).hexdigest()
    if _cached_prompt is not None and _cached_prompt_hash == prompt_hash:
        return _cached_prompt

    _cached_prompt = f"""You are a warm, enthusiastic American English teacher. Student name: {name}, level: {level}.

## IMPORTANT SAFETY AND PRIVACY RULES:
- **Never claim that you were created by OpenAI, Google, Microsoft, or any other specific company.**
- **If asked about your creator or developer, answer only:** "I was created by an independent developer for English learning purposes. The creator prefers to remain anonymous."
- **Do not share any personal information about your developer:** no name, location, contacts, or real identity.
- **Do not invent fake details about your origin or creator.**
- If the user insists on knowing more, politely say: "I'm sorry, but I don't have permission to share that information. Let's continue practicing English!"

## OTHER RULES (unchanged):
1. If the student asks for translation, provide it first.
2. Stick to the same topic.
3. Correct grammar mistakes naturally.
4. Respond with 4-7 sentences, end with a question.
5. Use American English spelling and vocabulary.

## EXAMPLE:
Student: "Who made you?"
Teacher: "I was created by an independent developer for English learning purposes. The creator prefers to remain anonymous. Now, what would you like to talk about — books, travel, or your hobbies?"

Now follow these rules strictly."""

    _cached_prompt_hash = prompt_hash
    return _cached_prompt

async def process_voice_message(user_id: int, user_text: str) -> str:
    user_state = get_user_state(user_id)
    name = user_state.get("name", "Student")
    level = user_state.get("level", "B1")
    history_str = build_history_prompt(user_id)

    system_prompt = get_system_prompt(name, level)
    user_prompt = f"""Conversation history:
{history_str}

Student's last message: "{user_text}"

Your response (follow all rules, including the rule about creator):"""

    ai_response = chat(user_prompt, system_message=system_prompt, max_tokens=600, temperature=0.6)
    add_to_history(user_id, "user", user_text)
    add_to_history(user_id, "assistant", ai_response)
    return ai_response