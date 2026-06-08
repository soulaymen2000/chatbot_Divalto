"""
Configuration settings for the Qdrant Vector Database and Embedding model.
"""

import os
from pathlib import Path

# --- Paths ---
# The base directory where the generated files are. Adjust if running from a different location.
BASE_DIR = Path(__file__).resolve().parent

# The directory containing the chunked data
# Assuming this script is in `d:\pfe2026\data\DC\testoutput\vectordb_setup`
DATA_DIR = BASE_DIR.parent

# --- Qdrant Settings ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "novamind_docs"

# --- Embedding Settings ---
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
# BGE-M3 vector dimension size
VECTOR_SIZE = 1024 

# --- Processing Settings ---
BATCH_SIZE = 64
