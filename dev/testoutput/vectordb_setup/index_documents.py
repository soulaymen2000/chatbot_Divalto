import os
import re
import json
import uuid
import logging
from pathlib import Path
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models

from config import (
    QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, 
    EMBEDDING_MODEL_NAME, BATCH_SIZE, DATA_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class DocumentIndexer:
    def __init__(self):
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        # BGE-M3 handles multiple languages and long contexts well
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        
        logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
        self.qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, check_compatibility=False)
        
        if not self.qdrant.collection_exists(collection_name=COLLECTION_NAME):
            raise ValueError(f"Collection '{COLLECTION_NAME}' does not exist. Run create_collection.py first.")

    def find_file_pairs(self, directory: Path):
        """
        Recursively find all *_meta.json files and their corresponding text files.
        """
        pairs = []
        # Find all JSON metadata files
        for json_path in directory.rglob("*_meta.json"):
            # Determine the base prefix
            base_prefix = json_path.name.replace("_meta.json", "")
            
            # Possible text file endings based on observation
            possible_txt_names = [
                f"{base_prefix}_chunks.txt",  # Observed in data
                f"{base_prefix}.txt"          # Fallback
            ]
            
            txt_path = None
            for txt_name in possible_txt_names:
                potential_path = json_path.parent / txt_name
                if potential_path.exists():
                    txt_path = potential_path
                    break
            
            if txt_path:
                pairs.append((json_path, txt_path))
            else:
                logger.warning(f"Missing pair for {json_path.name}. Skipping.")
                
        return pairs

    def parse_txt_chunks(self, txt_content: str):
        """
        Parses text files that might contain multiple chunks separated by '--- Chunk N ---'
        Returns a dictionary mapping chunk_id to text.
        """
        # Regex to find chunk headers like: --- Chunk 5 [status=original_untouched] [score=1.00] ---
        # or just --- Chunk 5 ---
        chunk_pattern = re.compile(r"^---\s*Chunk\s+(\d+).*?---$", re.MULTILINE)
        
        chunks = {}
        matches = list(chunk_pattern.finditer(txt_content))
        
        if not matches:
            # No delimiters found, assume the entire file is one chunk.
            # We'll use a special key or just return it as list of 1.
            return {None: txt_content.strip()}
            
        for i, match in enumerate(matches):
            chunk_id = int(match.group(1))
            start_pos = match.end()
            
            # Find the end of this chunk
            # It ends at the next separator '---' or end of file
            end_pos = matches[i+1].start() if i + 1 < len(matches) else len(txt_content)
            
            chunk_text = txt_content[start_pos:end_pos].strip()
            # Remove trailing '---' if it exists before the next chunk header
            if chunk_text.endswith("---"):
                chunk_text = chunk_text[:-3].strip()
                
            chunks[chunk_id] = chunk_text
            
        return chunks

    def process_pair(self, json_path: Path, txt_path: Path):
        """
        Process a single pair of files and return a list of payload objects.
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            try:
                metadata_array = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {json_path}")
                return []
                
        with open(txt_path, 'r', encoding='utf-8') as f:
            txt_content = f.read()
            
        parsed_chunks = self.parse_txt_chunks(txt_content)
        
        # In case the JSON isn't an array but a single object, wrap it
        if isinstance(metadata_array, dict):
            metadata_array = [metadata_array]
            
        points = []
        for meta in metadata_array:
            chunk_id = meta.get("chunk_id")
            
            # Match text to metadata
            if chunk_id in parsed_chunks:
                text = parsed_chunks[chunk_id]
            elif None in parsed_chunks and len(metadata_array) == 1:
                # File had no chunk delimiters and there's only 1 metadata object
                text = parsed_chunks[None]
            else:
                logger.warning(f"Could not find text for chunk_id {chunk_id} in {txt_path.name}")
                continue
                
            # Construct payload
            payload = {
                "text": text,
                "metadata": meta,
                "source_file": meta.get("source_file", ""),
                "folder_name": meta.get("folder_name", ""),
                "relative_path": meta.get("relative_path", ""),
                "chunk_id": chunk_id,
                "token_count": meta.get("token_count", 0),
                "txt_path": str(txt_path.absolute()),
                "json_path": str(json_path.absolute())
            }
            points.append(payload)
            
        return points

    def run(self):
        logger.info(f"Scanning for file pairs in {DATA_DIR}...")
        pairs = self.find_file_pairs(DATA_DIR)
        logger.info(f"Found {len(pairs)} matched pairs.")
        
        all_payloads = []
        for json_path, txt_path in pairs:
            payloads = self.process_pair(json_path, txt_path)
            all_payloads.extend(payloads)
            
        logger.info(f"Extracted {len(all_payloads)} total chunks to embed and index.")
        
        if not all_payloads:
            logger.warning("No payloads to index. Exiting.")
            return

        # Batch insert
        for i in tqdm(range(0, len(all_payloads), BATCH_SIZE), desc="Indexing Batches"):
            batch = all_payloads[i:i+BATCH_SIZE]
            texts = [p["text"] for p in batch]
            
            # Generate embeddings
            embeddings = self.model.encode(texts, show_progress_bar=False).tolist()
            
            # Prepare Qdrant points
            points = []
            for j, (embedding, payload) in enumerate(zip(embeddings, batch)):
                # Generate a unique deterministic ID or random UUID
                # Using UUID4 for simplicity, or we could hash the text/paths
                point_id = str(uuid.uuid4())
                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                )
                
            # Upsert
            try:
                self.qdrant.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points
                )
            except Exception as e:
                logger.error(f"Failed to upsert batch starting at index {i}: {e}")
            
        logger.info("Indexing complete! Vector DB is ready for NovaMind RAG.")

if __name__ == "__main__":
    try:
        indexer = DocumentIndexer()
        indexer.run()
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
