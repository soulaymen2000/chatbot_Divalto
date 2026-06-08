"""
End-to-end test for the Qdrant-based RAG Pipeline.
Tests: Qdrant connectivity, embedding, vector search, and LLM generation.
Run from the backend directory with the venv activated.
"""
import os
import sys
import django
import time

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "novamind.settings.base")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from apps.chat.services.rag import RAGPipeline


def test_pipeline():
    print("=" * 70)
    print("  NovaMind RAG Pipeline -- End-to-End Test")
    print("=" * 70)

    # 1. Initialize
    print("\n[1/3] Initializing RAG Pipeline...")
    t0 = time.time()
    try:
        pipeline = RAGPipeline()
        pipeline.initialize()
        print(f"  [PASS] Pipeline initialized in {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"  [FAIL] Initialization failed: {e}")
        return

    # 2. Test Retrieval
    test_query = "Comment faire une demande de prepaiement via PayZen ?"
    print(f"\n[2/3] Testing retrieval:")
    print(f"      Query: '{test_query}'")
    try:
        chunks, timings = pipeline.retrieve(test_query, k=3)
        print(f"  [PASS] Retrieved {len(chunks)} chunks")
        print(f"         Embed: {timings['embed_time']:.3f}s | Qdrant: {timings['qdrant_time']:.3f}s")
        for i, chunk in enumerate(chunks, 1):
            print(f"         #{i} Score={chunk['score']:.4f} | {chunk['titre'][:60]}")
            print(f"              Text: {chunk['texte'][:120]}...")
    except Exception as e:
        print(f"  [FAIL] Retrieval failed: {e}")
        import traceback; traceback.print_exc()
        return

    # 3. Test Generation
    print(f"\n[3/3] Testing LLM generation...")
    try:
        answer, gen_time = pipeline.generate(test_query, chunks)
        print(f"  [PASS] Answer generated in {gen_time:.2f}s ({len(answer)} chars)")
        print(f"\n  --- Answer ---")
        print(f"  {answer[:600]}")
        if len(answer) > 600:
            print(f"  ... ({len(answer)} chars total)")
    except Exception as e:
        print(f"  [FAIL] Generation failed: {e}")
        import traceback; traceback.print_exc()
        return

    print("\n" + "=" * 70)
    print("  [ALL PASS] Pipeline is fully operational!")
    print("=" * 70)


if __name__ == "__main__":
    test_pipeline()
