"""
Core RAG Pipeline Service.
Thread-safe singleton combining Qdrant dense vector search and local Qwen GGUF inference.
"""
import time
import logging
import threading
from typing import List, Dict, Tuple, Any

from django.conf import settings

# Thread-safe locks and logging
rag_logger = logging.getLogger("rag_pipeline")

# Lazy imports for ML stack to prevent startup crashes before package installation finishes
SentenceTransformerModel = None
QdrantClientClass = None
LlamaModel = None


def import_ml_stack():
    """Lazily import ML stack libraries."""
    global SentenceTransformerModel, QdrantClientClass, LlamaModel
    if SentenceTransformerModel is None:
        from sentence_transformers import SentenceTransformer
        SentenceTransformerModel = SentenceTransformer
    if QdrantClientClass is None:
        from qdrant_client import QdrantClient
        QdrantClientClass = QdrantClient
    if LlamaModel is None:
        from llama_cpp import Llama
        LlamaModel = Llama


class RAGPipeline:
    """
    RAG Pipeline Singleton.
    Manages loading of Qdrant client, SentenceTransformer, and Qwen GGUF model in a thread-safe manner.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RAGPipeline, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def initialize(self):
        """Initialise and load the models and Qdrant client."""
        if self._initialized:
            return

        rag_logger.info("Initializing RAG Pipeline models and Qdrant client...")
        start_time = time.time()

        # Import stack
        import_ml_stack()

        # 1. Device auto-detection
        import torch
        if settings.RAG_DEVICE == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = settings.RAG_DEVICE
        rag_logger.info("RAG Pipeline running on device: %s", self.device)

        # 2. Load BGE-M3 Embeddings
        rag_logger.info("Loading Embedding model: %s", settings.RAG_EMBEDDING_MODEL)
        self.embed_model = SentenceTransformerModel(
            settings.RAG_EMBEDDING_MODEL,
            device=self.device,
            trust_remote_code=True,
        )

        # 3. Connect to Qdrant
        rag_logger.info(
            "Connecting to Qdrant at %s:%s (collection: %s)",
            settings.QDRANT_HOST, settings.QDRANT_PORT, settings.QDRANT_COLLECTION,
        )
        self.qdrant = QdrantClientClass(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            check_compatibility=False,
        )
        # Verify collection exists
        if not self.qdrant.collection_exists(collection_name=settings.QDRANT_COLLECTION):
            raise ValueError(
                f"Qdrant collection '{settings.QDRANT_COLLECTION}' does not exist. "
                "Run create_collection.py and index_documents.py first."
            )
        collection_info = self.qdrant.get_collection(collection_name=settings.QDRANT_COLLECTION)
        rag_logger.info(
            "Qdrant collection '%s' connected — %d vectors indexed",
            settings.QDRANT_COLLECTION, collection_info.points_count,
        )

        # 4. Load local Qwen LLM
        import os
        model_path = settings.RAG_LLAMA_MODEL_PATH
        rag_logger.info("Loading local LLM from GGUF path: %s", model_path)
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Llama model file not found at {model_path}")

        # Calculate GPU layers (enable full acceleration if CUDA is active)
        n_gpu_layers = -1 if self.device == "cuda" else 0
        self.llm = LlamaModel(
            model_path=model_path,
            n_ctx=settings.RAG_CONTEXT_WINDOW,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )

        self._initialized = True
        rag_logger.info("RAG Pipeline initialization completed in %.2fs", time.time() - start_time)

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = False
        # Thread lock for inference/generation (llama-cpp is not internally thread-safe for parallel generations)
        self.generation_lock = threading.Lock()

    def retrieve(self, query: str, k: int = 3) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """
        Retrieves top relevant chunks using BGE-M3 dense embedding search via Qdrant.
        Returns (formatted_results, timings_dict).
        """
        rag_logger.info("Starting retrieval for query: '%s'", query)

        # 1. Query Embedding
        t0 = time.time()
        query_vector = self.embed_model.encode(query).tolist()
        embed_time = time.time() - t0

        # 2. Qdrant Vector Search
        t0 = time.time()
        results = self.qdrant.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            limit=k,
            with_payload=True,
        )
        qdrant_time = time.time() - t0

        # Log details
        rag_logger.info(
            "Retrieval timings — Embed: %.3fs, Qdrant: %.3fs",
            embed_time, qdrant_time,
        )

        # 3. Format output to match what views.py expects
        formatted_results = []
        for i, point in enumerate(results.points, 1):
            payload = point.payload
            source_file = payload.get("source_file", "")
            folder_name = payload.get("folder_name", "")

            rag_logger.info(
                "  #%d [%s] Score: %.4f (Folder: %s)",
                i, source_file, point.score, folder_name,
            )

            formatted_results.append({
                "titre": source_file,
                "texte": payload.get("text", ""),
                "source_file": source_file,
                "score": point.score,
                "raw_meta": {
                    "folder_name": folder_name,
                    "chunk_id": payload.get("chunk_id"),
                    "token_count": payload.get("token_count", 0),
                    "metadata": payload.get("metadata", {}),
                },
            })

        return formatted_results, {
            "embed_time": embed_time,
            "qdrant_time": qdrant_time,
        }

    def generate(self, question: str, retrieved_chunks: List[Dict]) -> Tuple[str, float]:
        """
        Generates answer from retrieved chunks using local Qwen GGUF model with safety guidelines.
        """
        # Ensure lazy loading is complete
        self.initialize()

        # Build context
        context_parts = []
        for i, chunk in enumerate(retrieved_chunks, 1):
            context_parts.append(
                f"--- SOURCE DOCUMENT #{i}: {chunk['titre']} (Fichier: {chunk['source_file']}) ---\n"
                f"{chunk['texte']}\n"
            )
        context_str = "\n".join(context_parts)

        # Build prompt incorporating anti-hallucination, structured formatting, and DIVALTO glossary rules
        system_prompt = (
            "Vous êtes Infolib, un expert technique senior spécialisé dans l'ERP DIVALTO.\n"
            "Votre mission est d'aider les utilisateurs de manière précise, professionnelle et intègre.\n\n"
            "DIRECTIVES DE GÉNÉRATION :\n"
            "1. Répondez STRICTEMENT en utilisant les documents sources fournis en contexte. Ne divaguez pas.\n"
            "2. ANTI-HALLUCINATION : Si les sources ne contiennent pas la réponse à la question, déclarez humblement "
            "que les documents actuels ne vous permettent pas de répondre, sans inventer d'informations.\n"
            "3. CITATION DES SOURCES : Citez toujours le nom du document source utilisé (ex: '[Module Devis]') pour "
            "justifier vos affirmations.\n"
            "4. GLOSSAIRE DIVALTO : Respectez rigoureusement la terminologie DIVALTO (ex: les notions de tiers, fiches articles, "
            "pièces commerciales de vente/achat, etc.).\n"
            "5. STRUCTURE : Rédigez une réponse claire avec du markdown (listes à puces, gras pour les termes clés, etc.).\n"
            "6. NIVEAU DE CONFIANCE : Indiquez à la fin de votre réponse votre niveau de confiance (Élevé/Moyen/Faible) "
            "par rapport aux sources disponibles."
        )

        user_prompt = (
            f"CONTEXTE DE RÉFÉRENCE :\n"
            f"{context_str}\n\n"
            f"QUESTION DE L'UTILISATEUR :\n"
            f"{question}\n\n"
            f"RÉPONSE D'INFOLIB :\n"
        )

        # Format prompt using Qwen Chat ML format if model supports it, or standard prompt structure
        full_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"

        rag_logger.info("Executing LLM generation with Qwen model...")
        t0 = time.time()

        # LLM thread lock for safety
        with self.generation_lock:
            response = self.llm(
                full_prompt,
                max_tokens=settings.RAG_MAX_TOKENS,
                temperature=settings.RAG_TEMPERATURE,
                stop=["<|im_end|>", "<|im_start|>", "--- SOURCE DOCUMENT"],
            )

        gen_time = time.time() - t0
        answer = response["choices"][0]["text"].strip()

        rag_logger.info("LLM generation completed in %.3fs", gen_time)
        return answer, gen_time
