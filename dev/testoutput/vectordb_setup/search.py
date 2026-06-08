"""
NovaMind RAG - Search Module
Uses BAAI/bge-m3 embeddings + Qdrant vector search.
Compatible with qdrant-client >= 1.14 (query_points API).
"""

import logging
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, EMBEDDING_MODEL_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class NovaMindSearcher:
    def __init__(self):
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        self.qdrant = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            check_compatibility=False,  # Suppress client/server version mismatch warning
        )

    def search(self, query: str, top_k: int = 5):
        """
        Embeds the query and searches Qdrant.
        Returns score, original text, metadata, and source file.
        """
        logger.info(f"Embedding query: '{query}'")
        query_vector = self.model.encode(query).tolist()

        logger.info("Searching Qdrant...")
        # query_points is the modern API (replaces deprecated .search())
        results = self.qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )

        formatted_results = []
        # query_points returns a QueryResponse; iterate over .points
        for point in results.points:
            payload = point.payload
            formatted_results.append({
                "score": point.score,
                "text": payload.get("text", ""),
                "source_file": payload.get("source_file", ""),
                "folder_name": payload.get("folder_name", ""),
                "chunk_id": payload.get("chunk_id"),
                "full_metadata": payload.get("metadata", {}),
            })

        return formatted_results


if __name__ == "__main__":
    try:
        searcher = NovaMindSearcher()

        # Test query
        sample_query = "Comment faire une demande de prépaiement via PayZen ?"
        print(f"\n--- Testing Search: '{sample_query}' ---\n")

        results = searcher.search(sample_query, top_k=3)

        if not results:
            print("No results found. Make sure you ran index_documents.py first.")
        else:
            for i, r in enumerate(results, 1):
                print(f"Result {i}:")
                print(f"  Score:   {r['score']:.4f}")
                print(f"  Source:  {r['source_file']} (Chunk {r['chunk_id']})")
                print(f"  Folder:  {r['folder_name']}")
                print(f"  Text:    {r['text'][:200]}...")
                print("-" * 60)

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)