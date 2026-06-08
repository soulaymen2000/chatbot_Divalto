"""
Standalone Test Script for RAG Pipeline.
Asserts correct embedding, retrieval, late BM25 reranking, and LLM text generation.
"""
import os
import sys
import django

# Add backend root to python path and initialize Django settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "novamind.settings.base")
django.setup()

from apps.chat.services.rag import RAGPipeline


def test_standalone_rag():
    print("=====================================================================")
    print("🚀 STARTING STANDALONE RAG PIPELINE TEST")
    print("=====================================================================")
    
    try:
        pipeline = RAGPipeline()
        print("1. Initializing RAG Pipeline Models and FAISS Index...")
        pipeline.initialize()
        print("✅ Models and FAISS Index loaded successfully!")
        print(f"   Device: {pipeline.device}")
        print(f"   FAISS Index Size: {pipeline.faiss_index.ntotal} vectors")
        
        # Test Query
        query = "Comment installer et configurer l'accès à Divalto Weavy ?"
        print(f"\n2. Retrieving context for query: '{query}'...")
        chunks, timings = pipeline.retrieve(query, k=3)
        print("✅ Retrieval complete!")
        print(f"   Embed Time: {timings['embed_time']:.3f}s")
        print(f"   FAISS Time: {timings['faiss_time']:.3f}s")
        print(f"   BM25 Time:  {timings['rerank_time']:.3f}s")
        
        print("\n--- RETRIEVED CHUNKS ---")
        for i, chunk in enumerate(chunks, 1):
            print(f"[{i}] {chunk['titre']} (Score: {chunk['score']:.4f})")
            print(f"    Source: {chunk['source_file']}")
            print(f"    Text Preview: {chunk['texte'][:200]}...")
            print("-" * 50)
            
        print("\n3. Generating response with local Qwen2.5 GGUF model...")
        answer, gen_time = pipeline.generate(query, chunks)
        print("✅ Generation complete!")
        print(f"   Generation Time: {gen_time:.3f}s")
        
        print("\n--- GENERATED ANSWER ---")
        print(answer)
        print("=====================================================================")
        print("✅ STANDALONE RAG PIPELINE TEST SUCCESSFUL!")
        print("=====================================================================")
        
    except Exception as e:
        print(f"\n❌ STANDALONE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_standalone_rag()
