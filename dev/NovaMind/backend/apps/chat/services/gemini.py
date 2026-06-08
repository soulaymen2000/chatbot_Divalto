"""
Gemini AI service for NovaMind.
Handles all interactions with the Google Gemini API:
  - Sending chat messages with full conversation history
  - Auto-generating conversation titles
  - Streaming responses (SSE)
"""
import logging
import google.generativeai as genai
from django.conf import settings

logger = logging.getLogger("apps.chat")

SYSTEM_PROMPT = """You are Infolib, an intelligent AI assistant built to help users
with a wide range of tasks including coding, writing, analysis, and creative work.

Guidelines:
- Be helpful, accurate, and concise
- Use markdown formatting for code blocks, lists, and emphasis
- When writing code, always specify the language in the code fence
- Be friendly and conversational but professional
- If you're unsure about something, say so clearly
- Remember the full conversation context when answering
"""


def _configure_gemini():
    """Configure the Gemini API client."""
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please add it to your .env file."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )


def _build_history(messages):
    """
    Convert Message queryset to Gemini chat history format.
    Gemini expects: [{"role": "user"/"model", "parts": [text]}]
    """
    history = []
    for msg in messages:
        role = "model" if msg.role == "assistant" else "user"
        history.append({
            "role": role,
            "parts": [msg.content],
        })
    return history


def generate_response(conversation_messages, new_user_message: str) -> dict:
    """
    Send a message to Gemini and return the AI response.

    Args:
        conversation_messages: QuerySet of previous Message objects (ordered by timestamp)
        new_user_message: The new message text from the user

    Returns:
        dict with keys: content (str), tokens_used (int)
    """
    try:
        model = _configure_gemini()

        # Build history excluding the new message (already handled separately)
        history = _build_history(conversation_messages)

        # Start chat session with history
        chat = model.start_chat(history=history)

        # Send the new message
        response = chat.send_message(new_user_message)

        content = response.text
        tokens_used = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_used = getattr(response.usage_metadata, "total_token_count", 0)

        logger.info(
            "Gemini response generated. Tokens used: %d",
            tokens_used,
        )
        return {"content": content, "tokens_used": tokens_used}

    except Exception as exc:
        logger.error("Gemini API error: %s", exc, exc_info=True)
        raise


def generate_stream(conversation_messages, new_user_message: str):
    """
    Generator that yields Gemini response chunks for SSE streaming.

    Yields:
        str — text chunks from Gemini
    """
    try:
        model = _configure_gemini()
        history = _build_history(conversation_messages)
        chat = model.start_chat(history=history)
        response = chat.send_message(new_user_message, stream=True)

        for chunk in response:
            if chunk.text:
                yield chunk.text

    except Exception as exc:
        logger.error("Gemini streaming error: %s", exc, exc_info=True)
        yield f"\n\n[Error: {str(exc)}]"


def generate_title(user_message: str) -> str:
    """
    Ask Gemini to generate a short conversation title from the first user message.
    Returns a plain string title (max ~50 chars).
    """
    try:
        model = _configure_gemini()
        prompt = (
            f"Generate a very short conversation title (max 6 words, no quotes) "
            f"for a chat that starts with: \"{user_message}\""
        )
        response = model.generate_content(prompt)
        title = response.text.strip().strip('"').strip("'")
        # Truncate to safe length
        return title[:60] if title else "New Conversation"
    except Exception as exc:
        logger.warning("Could not generate title: %s", exc)
        # Fallback: use first 50 chars of the user message
        return user_message[:50] + ("..." if len(user_message) > 50 else "")
