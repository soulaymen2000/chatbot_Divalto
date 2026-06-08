# NovaMind — Launch Guide

Quick reference for starting and managing all NovaMind services.

---

## Quick Start (Recommended)

```powershell
# From D:\pfe2026\NovaMind\
.\START_PROJECT.ps1     # Starts everything
.\STOP_PROJECT.ps1      # Stops everything
```

---

## Manual Commands (one by one)

### 1. Qdrant Vector Database

```powershell
# Start existing container (after first run)
docker start $(docker ps -aq --filter "ancestor=qdrant/qdrant")

# OR create fresh container with persistent storage
docker run -d `
    --name novamind-qdrant `
    -p 6333:6333 `
    -v "D:\pfe2026\qdrant_db_hybrid:/qdrant/storage" `
    qdrant/qdrant

# Check status
docker ps --filter "ancestor=qdrant/qdrant"

# Check Qdrant dashboard
# http://localhost:6333/dashboard

# Stop
docker stop $(docker ps -q --filter "ancestor=qdrant/qdrant")
```

### 2. Django Backend API

```powershell
cd D:\pfe2026\NovaMind\backend

# Activate venv (optional, use full path otherwise)
.\venv\Scripts\Activate.ps1

# Run server
.\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000

# Other useful Django commands
.\venv\Scripts\python.exe manage.py check          # System check
.\venv\Scripts\python.exe manage.py migrate         # Apply migrations
.\venv\Scripts\python.exe manage.py createsuperuser # Create admin user
```

**API Base URL:** `http://localhost:8000`  
**Admin Panel:** `http://localhost:8000/admin/`

### 3. React Frontend (Vite)

```powershell
cd D:\pfe2026\NovaMind\app

pnpm run dev        # Start dev server (port 5173)
pnpm install        # Install/update dependencies
pnpm run build      # Build for production
```

**Frontend URL:** `http://localhost:5173`

---

## Vectordb Setup (re-indexing documents)

```powershell
# From the vectordb_setup folder (used to populate Qdrant)
cd D:\pfe2026\data\DC\testoutput\vectordb_setup

python create_collection.py    # Create Qdrant collection (first time only)
python index_documents.py      # Index all documents into Qdrant
python search.py               # Test search works correctly
```

```powershell
# From the advanced vectordb folder
cd D:\pfe2026\data\vectordb

python vectordb_ingest.py      # Ingest with hybrid (dense + sparse BM25)
python vectordb_search.py      # Search test
```

---

## Test RAG Pipeline

```powershell
cd D:\pfe2026\NovaMind\backend
.\venv\Scripts\python.exe test_rag_pipeline.py
```

---

## Service URLs Summary

| Service          | URL                              | Notes                  |
|------------------|----------------------------------|------------------------|
| Qdrant DB        | http://localhost:6333            | Vector database        |
| Qdrant Dashboard | http://localhost:6333/dashboard  | Web UI                 |
| Django API       | http://localhost:8000            | REST API               |
| Django Admin     | http://localhost:8000/admin/     | Admin panel            |
| React Frontend   | http://localhost:5173            | Main app               |

---

## Prerequisites

- **Docker Desktop** must be running before starting Qdrant
- **Qdrant collection** `novamind_docs` must be indexed (run `index_documents.py`)
- **Qwen GGUF model** at `C:\models\qwen2.5-3b-instruct.Q4_K_M.gguf`
- **PostgreSQL** running on `localhost:5432` (DB: `infolib`)

> **Note:** First API request after startup takes ~20s to load BGE-M3 embeddings + Qwen LLM into memory.
