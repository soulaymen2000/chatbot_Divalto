"""
Service for generating short conversation titles using the local Qwen LLM.
"""
import time
import logging
from django.conf import settings
from .rag import RAGPipeline

logger = logging.getLogger("apps.chat")


def generate_conversation_title(question: str) -> str:
    """
    Generates a concise, context-aware 3-6 word title for a conversation
    based on the user's initial question.
    """
    try:
        pipeline = RAGPipeline()
        # Ensure model is initialized
        pipeline.initialize()

        prompt = (
            "<|im_start|>system\n"
            "Tu es un assistant chargé de titrer une conversation. Génère un titre court, "
            "direct et accrocheur en français, de 3 à 5 mots maximum, résumant la question de l'utilisateur. "
            "Réponds UNIQUEMENT avec le titre de la conversation, sans guillemets ni introduction.\n"
            "<|im_end|>\n"
            f"<|im_start|>user\n"
            f"Question : {question}\n"
            f"Titre de la conversation : <|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        logger.info("Generating conversation title for: '%s'", question[:50])
        t0 = time.time()
        
        with pipeline.generation_lock:
            response = pipeline.llm(
                prompt,
                max_tokens=25,
                temperature=0.3,
                stop=["<|im_end|>", "\n"],
            )

        duration = time.time() - t0
        title = response["choices"][0]["text"].strip()
        
        # Clean title formatting
        title = title.strip('"'+"'"+"`")
        if len(title) > 60:
            title = title[:57] + "..."
            
        logger.info("Generated title: '%s' in %.3fs", title, duration)
        return title if title else "Nouvelle Conversation"

    except Exception as e:
        logger.error("Failed to generate title, using default: %s", e)
        return "Nouvelle Conversation"
