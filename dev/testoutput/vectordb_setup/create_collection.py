import logging
from qdrant_client import QdrantClient
from qdrant_client.http import models
from config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, VECTOR_SIZE

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def create_qdrant_collection():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, check_compatibility=False)
    
    # Check if collection exists
    if client.collection_exists(collection_name=COLLECTION_NAME):
        logger.warning(f"Collection '{COLLECTION_NAME}' already exists. Skipping creation.")
        return

    logger.info(f"Creating collection '{COLLECTION_NAME}' with vector size {VECTOR_SIZE}...")
    
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE
        ),
        # Optimizations for hybrid search and payload filtering
        optimizers_config=models.OptimizersConfigDiff(
            default_segment_number=2
        )
    )
    
    # Create payload indexes for faster filtering
    logger.info("Creating payload indexes for hybrid search readiness...")
    fields_to_index = ["folder_name", "source_file", "chunk_id", "content_type", "validation_status"]
    
    for field in fields_to_index:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD
            )
            logger.info(f"Created index on field: {field}")
        except Exception as e:
            logger.error(f"Failed to create index on {field}: {e}")
            
    logger.info(f"Collection '{COLLECTION_NAME}' successfully created and optimized!")

if __name__ == "__main__":
    try:
        create_qdrant_collection()
    except Exception as e:
        logger.error(f"Error connecting to Qdrant: {e}")
        logger.info("Make sure Qdrant is running (e.g., via Docker: docker run -p 6333:6333 qdrant/qdrant)")
