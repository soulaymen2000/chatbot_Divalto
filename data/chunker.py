"""
chunker.py — Merged Pipeline v8
================================
Integrates:
  - Hierarchical recursive traversal + JSON companion parsing
  - Thread-safe dual-level cache  (file-hash + chunk-score-hash)
  - Recursive rechunking with depth tracking (no fake scores policy)
  - 5 chunking strategies, including LangChain RecursiveCharacterTextSplitter
  - NLTK sent_tokenize for sentence-aware splitting
  - ThreadPoolExecutor for parallel I/O (LLM calls remain serialised)
  - tqdm progress bar
  - Per-file output mirroring input hierarchy  +  unified output

v4 fixes:
  - LLM_MAX_TOKENS raised 256 → 512  (eliminates JSON truncation)
  - Prompt now sends both original source + chunk so fidelity is meaningful
  - Cache key updated to hash(original_prefix + chunk) for correct fidelity caching
  - Chunk char limit to LLM raised 600 → 1000, original limit 0 → 1200
  - original_text threaded through _process_segment recursion

v5 fixes:
  - LLM_MAX_TOKENS raised 512 → 768  (prompt is larger now; 512 still truncated)
  - score=0.0 chunks are DROPPED at max rechunk depth instead of accepted
  - Pure IMAGE/TABLE marker chunks are skipped before entering LLM loop
  - Source text is pre-cleaned: \\xa0 → space, \\x92 → apostrophe, NFC normalised

v6 fixes:
  - LLM_MAX_TOKENS raised 768 → 1024  (768 still truncated fidelity field)
  - LLM prompt end seeded with '{\"completeness\":' to force JSON-first output,
    eliminating preamble tokens that consumed output budget
  - Smart encoding detection: tries UTF-8, falls back to Windows-1252 when >1%
    of chars are replacement chars — fixes mojibake (modle→modèle, dfaut→défaut)
  - Boundary issue flag: chunks starting mid-sentence get boundary_issue:true
    in metadata so downstream consumers can filter or flag them

v7 fixes:
  - _parse() now rescues truncated JSON via per-field regex extraction when
    the closing brace is missing — recovers chunks that had good scores (0.8+)
    but were dropped because fidelity/final_score got cut off
  - _PURE_MARKER_PAT broadened to also match hex-hash IMAGE format:
    [IMAGE: d186ac4eaaea...] — prevents those chunks from wasting 3 LLM retries
  - _read_text_smart() now normalises CRLF (\\r\\n) and bare \\r to \\n before
    returning — fixes Windows line-ending artifacts seen in chunk fragments

v8 fixes:
  - SCORE_WEIGHTS added to Config — fidelity is the dominant criterion (0.40),
    followed by completeness (0.20), coherence (0.15), relevance (0.15),
    boundary (0.10)
  - final_score is now ALWAYS recomputed from SCORE_WEIGHTS after LLM parsing,
    overriding whatever the LLM returned — the LLM's own final_score value is
    stored as llm_final_score for reference but never used for accept/reject
  - Same weighted formula applied in the rescue path (Path B of _parse)
"""

# ── Standard library ─────────────────────────────────────────────────────────
import hashlib
import json
import logging
import os
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

# ── Load .env if python-dotenv is available (ignored in prod Docker) ──────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Third-party ───────────────────────────────────────────────────────────────
import nltk
from nltk.tokenize import sent_tokenize
import tiktoken
from tqdm import tqdm

# ── LangChain (optional — graceful degradation) ───────────────────────────────
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

class Config:
    # ── Paths (all driven by environment variables) ───────────────────────────
    # HOST paths are mounted into the container; workspace paths are written
    # inside the container's /app/workspace volume.
    MODEL_PATH  = os.environ["MODEL_PATH"]          # required — must be set
    INPUT_DIR   = os.environ["INPUT_DIR"]           # required — must be set
    OUTPUT_DIR  = os.getenv("OUTPUT_DIR",  "/app/workspace/output")
    CACHE_FILE  = os.getenv("CACHE_FILE",  "/app/workspace/.chunker_cache.json")
    LOG_FILE    = os.getenv("LOG_FILE",    "/app/workspace/chunker.log")

    # Parallelism (LLM calls are still serialised through one lock)
    MAX_IO_WORKERS = int(os.getenv("MAX_IO_WORKERS", "4"))

    # Token thresholds
    THRESHOLD             = int(os.getenv("THRESHOLD",             "400"))
    LOW_CONTENT_THRESHOLD = int(os.getenv("LOW_CONTENT_THRESHOLD", "20"))
    MIN_TOKENS            = int(os.getenv("MIN_TOKENS",            "150"))
    MAX_TOKENS            = int(os.getenv("MAX_TOKENS",            "300"))

    # Hardcoded scores for untouched files (under THRESHOLD)
    PASSTHROUGH_SCORES = {
        "completeness": 1.0,
        "coherence":    1.0,
        "relevance":    1.0,
        "boundary":     1.0,
        "fidelity":     1.0,
        "final_score":  1.0,
    }

    # Validation
    ACCEPT_SCORE      = float(os.getenv("ACCEPT_SCORE",   "0.7"))
    LLM_MAX_TOKENS    = int(os.getenv("LLM_MAX_TOKENS",   "1024"))
    LLM_N_CTX         = int(os.getenv("LLM_N_CTX",        "4096"))
    LLM_RETRIES       = int(os.getenv("LLM_RETRIES",      "3"))
    MAX_RECHUNK_DEPTH = int(os.getenv("MAX_RECHUNK_DEPTH", "3"))

    # FIX v8: weighted final_score formula — fidelity is the dominant criterion.
    # These weights always override the LLM's own final_score value.
    # Must sum to 1.0.
    SCORE_WEIGHTS = {
        "fidelity":     0.40,
        "completeness": 0.20,
        "coherence":    0.15,
        "relevance":    0.15,
        "boundary":     0.10,
    }

    # Final unified outputs (workspace-relative paths)
    OUTPUT_CHUNKS   = os.getenv("OUTPUT_CHUNKS",   "/app/workspace/chunks.txt")
    OUTPUT_METADATA = os.getenv("OUTPUT_METADATA", "/app/workspace/metadata.json")
    PARTIAL_FILE    = os.getenv("PARTIAL_FILE",    "/app/workspace/.metadata_partial.json")


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

def setup_logging() -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

logger = logging.getLogger("chunker")


# ═══════════════════════════════════════════════════════════════════════════════
# TOKENIZER  (LLM-aligned, module-level singleton)
# ═══════════════════════════════════════════════════════════════════════════════

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _posix(p: Path, root: Path) -> str:
    """Return a forward-slash relative path (platform-safe)."""
    return str(PurePosixPath(p.relative_to(root)))


# ═══════════════════════════════════════════════════════════════════════════════
# CACHE MANAGER — thread-safe, dual-level
# ═══════════════════════════════════════════════════════════════════════════════

class CacheManager:
    """
    Two caching levels in a single JSON file:

    file_cache   : { relative_path -> {file_hash, processed_at, chunk_count} }
                   Skip files that haven't changed since the last run.

    score_cache  : { md5(original_prefix + "|||" + chunk_text) -> scores_dict }
                   Skip LLM scoring for identical (original, chunk) pairs seen before.
                   Key includes the original source prefix so fidelity is always
                   evaluated in the correct context.

    next_chunk_id: monotonically increasing global counter.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data = self._load()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load(self) -> Dict:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                n = len(d.get("file_cache", {}))
                s = len(d.get("score_cache", {}))
                if n or s:
                    logger.info("Cache loaded — %d file(s) done, %d score(s) cached.", n, s)
                return d
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Cache unreadable, starting fresh: %s", exc)
        return {
            "version": "1.8",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_cache":  {},
            "score_cache": {},
            "next_chunk_id": 1,
        }

    def save(self) -> None:
        with self._lock:
            try:
                with open(self._path, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=2, ensure_ascii=False)
            except OSError as exc:
                logger.error("Cannot save cache: %s", exc)

    # ── file-level API ────────────────────────────────────────────────────────

    @staticmethod
    def hash_file(path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()

    def file_is_done(self, rel: str) -> bool:
        with self._lock:
            return rel in self._data["file_cache"]

    def file_hash_matches(self, rel: str, current_hash: str) -> bool:
        with self._lock:
            return self._data["file_cache"].get(rel, {}).get("file_hash") == current_hash

    def mark_file_done(self, rel: str, fhash: str, chunk_count: int) -> None:
        with self._lock:
            self._data["file_cache"][rel] = {
                "file_hash":    fhash,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "chunk_count":  chunk_count,
            }

    def unmark_file(self, rel: str) -> None:
        with self._lock:
            self._data["file_cache"].pop(rel, None)

    # ── chunk-score-level API ─────────────────────────────────────────────────

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def get_score(self, chunk_hash: str) -> Optional[Dict]:
        with self._lock:
            return self._data["score_cache"].get(chunk_hash)

    def set_score(self, chunk_hash: str, scores: Dict) -> None:
        with self._lock:
            self._data["score_cache"][chunk_hash] = scores

    # ── chunk-id API ──────────────────────────────────────────────────────────

    @property
    def next_chunk_id(self) -> int:
        with self._lock:
            return self._data["next_chunk_id"]

    def advance_id(self, count: int) -> None:
        with self._lock:
            self._data["next_chunk_id"] += count

    def clear(self) -> None:
        if os.path.exists(self._path):
            os.remove(self._path)


# ═══════════════════════════════════════════════════════════════════════════════
# METADATA STORE — incremental, interruption-safe (main-thread only)
# ═══════════════════════════════════════════════════════════════════════════════

class MetadataStore:
    """
    Accumulates chunk metadata across runs.
    Written to PARTIAL_FILE after every completed file so a crash never
    loses already-processed data.
    """

    def __init__(self, partial_path: str) -> None:
        self.path    = Path(partial_path)
        self.entries: List[Dict] = self._load()

    def _load(self) -> List[Dict]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _flush(self) -> None:
        self.path.write_text(
            json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def add(self, new_entries: List[Dict]) -> None:
        self.entries.extend(new_entries)
        self._flush()

    def remove_by_rel(self, rel: str) -> int:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.get("relative_path") != rel]
        removed = before - len(self.entries)
        if removed:
            self._flush()
        return removed

    def finalize(self, output_path: str) -> None:
        Path(output_path).write_text(
            json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if self.path.exists():
            self.path.unlink()


# ═══════════════════════════════════════════════════════════════════════════════
# LLM JUDGE — thread-safe, retries, chunk-level cache, NO FAKE SCORES
# ═══════════════════════════════════════════════════════════════════════════════

class LLMJudge:
    """
    Strict policy: evaluate() returns None if ALL LLM_RETRIES attempts fail.
    A None score means the chunk is dropped — scores are never invented.

    v4 changes:
      - Prompt includes both original source text and the chunk so that
        'fidelity' (meaning preserved) can be assessed with a real reference.
      - Cache key = md5(original_prefix + "|||" + chunk) so the same chunk
        from two different sources gets independent fidelity scores.
      - LLM_MAX_TOKENS raised to 512 to prevent JSON truncation.
      - Char limits raised: original → 1200, chunk → 1000.
    """

    SCORE_FIELDS = [
        "completeness", "coherence", "relevance",
        "boundary", "fidelity", "final_score",
        # llm_final_score is added by _apply_weights() — stored for reference only
        # It is NOT used for accept/reject decisions; final_score (weighted) is.
    ]
    # Fields that must be present in a valid parsed result (excludes llm_final_score)
    _REQUIRED_FIELDS = ["completeness", "coherence", "relevance", "boundary", "fidelity", "final_score"]

    # FIX v6: The prompt ends with the opening of the JSON object.
    # This seeds the model's first output token as a number, preventing it from
    # generating any preamble text (e.g. "Here is my evaluation:\n") that would
    # consume output token budget and cause the JSON to be truncated.
    # evaluate() prepends '{"completeness":' back before parsing.
    _PROMPT = (
        "You are a strict text chunk quality evaluator.\n\n"
        "ORIGINAL SOURCE TEXT (reference):\n\"\"\"{original}\"\"\"\n\n"
        "CHUNK TO EVALUATE:\n\"\"\"{chunk}\"\"\"\n\n"
        "Score each criterion from 0.0 to 1.0:\n"
        "1. completeness — does the chunk express a complete idea?\n"
        "2. coherence    — is the chunk internally consistent and readable?\n"
        "3. relevance    — is the chunk topically focused?\n"
        "4. boundary     — does the chunk have a natural start and end?\n"
        "5. fidelity     — does the chunk faithfully preserve the meaning of "
                           "the corresponding part of the original text?\n"
        "6. final_score  — your overall quality rating\n\n"
        "Output ONLY valid JSON. Do NOT write any explanation or preamble.\n"
        '{{"completeness":'
    )
    # Prefix re-attached in evaluate() before JSON parsing
    _JSON_PREFIX = '{"completeness":'

    def __init__(self, cache: CacheManager) -> None:
        self._lock  = threading.Lock()
        self._cache = cache
        logger.info("Loading LLM judge: %s", Config.MODEL_PATH)
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError("pip install llama-cpp-python")
        self._llm = Llama(
            model_path=Config.MODEL_PATH,
            n_gpu_layers=-1,
            n_ctx=Config.LLM_N_CTX,
            verbose=False,
        )
        logger.info("LLM judge ready.")

    def evaluate(
        self,
        chunk: str,
        original_text: str = "",   # FIX v4: added — reference for fidelity scoring
    ) -> Optional[Dict[str, float]]:
        """
        Score a chunk via LLM with up to LLM_RETRIES attempts on parse failure.
        Returns the scores dict, or None if all attempts fail.

        The cache key is derived from both the original source prefix and the
        chunk text so that fidelity is always evaluated in the correct context.
        """
        if not chunk.strip():
            return None

        # FIX v4: cache key includes original so fidelity is context-specific
        cache_key = CacheManager.hash_text(
            original_text[:500] + "|||" + chunk
        )
        cached = self._cache.get_score(cache_key)
        if cached:
            return cached

        # FIX v4: send up to 1200 chars of original + 1000 chars of chunk
        prompt = self._PROMPT.format(
            original=original_text[:1200].strip(),
            chunk=chunk[:1000].strip(),
        )

        for attempt in range(1, Config.LLM_RETRIES + 1):
            with self._lock:
                try:
                    out = self._llm(
                        prompt,
                        max_tokens=Config.LLM_MAX_TOKENS,  # now 1024
                        temperature=0.05,
                        stop=["</s>", "<|im_end|>"],
                    )
                    # FIX v6: re-attach the seeded prefix the model was forced to continue
                    raw = self._JSON_PREFIX + out["choices"][0]["text"].strip()
                except Exception as exc:
                    logger.error("LLM call failed (attempt %d/%d): %s", attempt, Config.LLM_RETRIES, exc)
                    continue

            scores = self._parse(raw)
            if scores is not None:
                self._cache.set_score(cache_key, scores)
                return scores

            logger.warning(
                "JSON parse failed (attempt %d/%d) — raw: %.80s", attempt, Config.LLM_RETRIES, raw
            )

        logger.error(
            "LLM could not score chunk after %d attempts. Dropping: %.60r",
            Config.LLM_RETRIES, chunk,
        )
        return None  # Never return invented scores

    def _parse(self, raw: str) -> Optional[Dict[str, float]]:
        """
        Parse a JSON scoring response from the LLM.

        FIX v7: Two-path parser:
          Path A — full JSON present (closing brace found) → standard json.loads
          Path B — JSON truncated (no closing brace, always at fidelity/final_score)
                   → extract all available fields via per-field regex, then fill
                   any missing fields by averaging the ones we have.
                   Requires at least 4 of 6 fields to be present to rescue.

        FIX v8: After either path succeeds, final_score is ALWAYS recomputed
          using Config.SCORE_WEIGHTS so that fidelity dominates.
          The LLM's original final_score value is preserved as llm_final_score.
        """
        import re as _r

        start = raw.find("{")
        if start == -1:
            return None

        end = raw.rfind("}") + 1

        criteria = [
            "completeness", "coherence", "relevance", "boundary", "fidelity"
        ]  # the 5 scored fields — excludes final_score and llm_final_score

        def _apply_weights(scores: Dict[str, float]) -> Dict[str, float]:
            """
            FIX v8: recompute final_score using Config.SCORE_WEIGHTS.
            Saves the LLM's original value as llm_final_score for debugging.
            Fidelity weight = 0.40, so a chunk with fidelity=0.0 can never
            exceed final_score=0.60 no matter how good the other criteria are.
            """
            scores["llm_final_score"] = scores.get("final_score", 0.0)
            scores["final_score"] = round(
                sum(
                    scores.get(criterion, 0.0) * weight
                    for criterion, weight in Config.SCORE_WEIGHTS.items()
                ),
                4,
            )
            return scores

        # ── Path A: complete JSON ─────────────────────────────────────────────
        if end > 0:
            try:
                data = json.loads(raw[start:end])
                scores = {
                    f: max(0.0, min(1.0, float(data[f])))
                    for f in self.SCORE_FIELDS
                    if f in data
                }
                # Ensure all criteria are present before applying weights
                if all(c in scores for c in criteria):
                    return _apply_weights(scores)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass  # fall through to regex rescue

        # ── Path B: truncated JSON — rescue via regex ─────────────────────────
        partial = raw[start:]
        found: Dict[str, float] = {}
        for field in ["completeness", "coherence", "relevance", "boundary", "fidelity", "final_score"]:
            m = _r.search(
                rf'"{field}"\s*:\s*([0-9]*\.?[0-9]+)', partial
            )
            if m:
                found[field] = max(0.0, min(1.0, float(m.group(1))))

        # Need at least 4 scored criteria to produce a meaningful result
        found_criteria = [f for f in criteria if f in found]

        if len(found_criteria) < 4:
            return None   # too incomplete to rescue

        # Fill missing fidelity with average of available criteria
        if "fidelity" not in found:
            found["fidelity"] = round(
                sum(found[f] for f in found_criteria) / len(found_criteria), 3
            )
            logger.debug(
                "Rescued truncated JSON — fidelity imputed from %d criteria", len(found_criteria)
            )

        # Fill any remaining missing criteria with 0.0
        for c in criteria:
            if c not in found:
                found[c] = 0.0

        # Seed final_score so _apply_weights can save it as llm_final_score
        found["final_score"] = found.get("final_score", 0.0)

        logger.debug(
            "Rescued truncated JSON — recovered %d/%d fields", len(found_criteria), len(criteria)
        )
        return _apply_weights(found)


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNKING STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

_SENT_FALLBACK_RE = __import__("re").compile(r"(?<=[.!?])\s+")


class ChunkingStrategies:
    """
    Five strategies in escalation order (least → most aggressive):

      1. sentence   — NLTK sent_tokenize, target=MAX_TOKENS
      2. langchain  — LangChain RecursiveCharacterTextSplitter (tiktoken)
      3. smaller    — NLTK sent_tokenize, target=220 (shorter chunks)
      4. paragraph  — paragraph boundary first, then sentence fallback
      5. force_split — mechanical word-level split, last resort

    All strategies pass their output through enforce_bounds() to guarantee
    every returned chunk is within [MIN_TOKENS, MAX_TOKENS].
    """

    STRATEGY_NAMES = ["sentence", "langchain", "smaller", "paragraph", "force_split"]

    # ── bounds enforcement ────────────────────────────────────────────────────

    @classmethod
    def enforce_bounds(cls, chunks: List[str]) -> List[str]:
        """
        Guarantee every chunk is within [MIN_TOKENS, MAX_TOKENS].
        Phase 1: merge undersized chunks with left neighbour.
        Phase 2: token-split oversized chunks.
        """
        # Phase 1 — merge too-small
        merged: List[str] = []
        buf = ""
        for ch in chunks:
            combined = (buf + " " + ch).strip() if buf else ch
            if count_tokens(combined) < Config.MIN_TOKENS:
                buf = combined
            else:
                merged.append(combined)
                buf = ""
        if buf:
            if merged:
                merged[-1] = (merged[-1] + " " + buf).strip()
            else:
                merged.append(buf)

        # Phase 2 — split too-large
        result: List[str] = []
        for ch in merged:
            if count_tokens(ch) <= Config.MAX_TOKENS:
                result.append(ch)
            else:
                tokens = _enc.encode(ch)
                i = 0
                while i < len(tokens):
                    piece_tokens = tokens[i: i + Config.MAX_TOKENS]
                    try:
                        piece = _enc.decode(piece_tokens)
                    except Exception:
                        # Fallback: word-level
                        words = ch.split()
                        for j in range(0, len(words), Config.MAX_TOKENS):
                            result.append(" ".join(words[j: j + Config.MAX_TOKENS]))
                        break
                    if piece.strip():
                        result.append(piece)
                    i += Config.MAX_TOKENS

        return [c for c in result if c.strip()]

    # ── strategy 1: NLTK sentence-aware ──────────────────────────────────────

    @classmethod
    def strategy_sentence(cls, text: str, target: int = Config.MAX_TOKENS) -> List[str]:
        """Accumulate NLTK sentences up to *target* tokens per chunk."""
        try:
            sentences = sent_tokenize(text)
        except Exception:
            parts = _SENT_FALLBACK_RE.split(text.strip())
            sentences = [s for s in parts if s.strip()]

        chunks: List[str] = []
        current = ""
        cur_tok = 0

        for s in sentences:
            s_tok = count_tokens(s)
            if cur_tok + s_tok <= target:
                current = (current + " " + s).strip()
                cur_tok += s_tok
            else:
                if current:
                    chunks.append(current)
                current, cur_tok = s, s_tok

        if current:
            chunks.append(current)

        return cls.enforce_bounds(chunks)

    # ── strategy 2: LangChain RecursiveCharacterTextSplitter ─────────────────

    @classmethod
    def strategy_langchain(cls, text: str) -> List[str]:
        """
        LangChain RecursiveCharacterTextSplitter with tiktoken encoder.
        Tries separators in order: paragraph → line → sentence → word → char.
        Falls back to strategy_sentence if langchain-text-splitters is absent.
        """
        if not _LANGCHAIN_AVAILABLE:
            logger.warning(
                "langchain-text-splitters not installed — "
                "falling back to sentence strategy. "
                "Install with: pip install langchain-text-splitters"
            )
            return cls.strategy_sentence(text)

        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=Config.MAX_TOKENS,
            chunk_overlap=20,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""],
        )
        chunks = splitter.split_text(text)
        return cls.enforce_bounds(chunks)

    # ── strategy 3: NLTK smaller (conservative 220-token target) ─────────────

    @classmethod
    def strategy_smaller(cls, text: str) -> List[str]:
        """Sentence accumulation with tighter 220-token target."""
        return cls.strategy_sentence(text, target=220)

    # ── strategy 4: paragraph-first ──────────────────────────────────────────

    @classmethod
    def strategy_paragraph(cls, text: str) -> List[str]:
        """Split by paragraph boundaries, then sentence within large paragraphs."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) <= 1:
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

        chunks: List[str] = []
        for para in paragraphs:
            if count_tokens(para) <= Config.MAX_TOKENS:
                chunks.append(para)
            else:
                chunks.extend(cls.strategy_sentence(para))

        return cls.enforce_bounds(chunks)

    # ── strategy 5: force split (last resort) ─────────────────────────────────

    @classmethod
    def strategy_force_split(cls, text: str) -> List[str]:
        """Mechanical word-level split at the midpoint of [MIN, MAX]."""
        target = (Config.MIN_TOKENS + Config.MAX_TOKENS) // 2  # 225
        words  = text.split()
        chunks = []
        for i in range(0, len(words), target):
            piece = " ".join(words[i: i + target])
            if piece.strip():
                chunks.append(piece)
        return cls.enforce_bounds(chunks)

    # ── dispatch ──────────────────────────────────────────────────────────────

    @classmethod
    def apply(cls, text: str, name: str) -> List[str]:
        dispatch = {
            "sentence":    cls.strategy_sentence,
            "langchain":   cls.strategy_langchain,
            "smaller":     cls.strategy_smaller,
            "paragraph":   cls.strategy_paragraph,
            "force_split": cls.strategy_force_split,
        }
        fn = dispatch.get(name, cls.strategy_sentence)
        return fn(text)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTENT FEATURE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

import re as _re

_IMG_PAT = _re.compile(
    r"!\[.*?\]\(.*?\)|<img[^>]*>|\[IMAGE[_\d]*\]|\[IMG[_\d]*\]|<IMAGE[^>]*>",
    _re.IGNORECASE,
)
_TBL_PAT = _re.compile(r"\|.+\|.+\|")
_COD_PAT = _re.compile(r"```[\s\S]*?```|`[^`\n]+`")

# FIX v5: chunks that are ONLY a marker placeholder have no text for the LLM to score
# FIX v7: pattern extended to also match hex-hash format: [IMAGE: d186ac4eaaea...]
#          which was not caught by the original pattern and wasted 3 LLM retries each
_PURE_MARKER_PAT = _re.compile(
    r"^\s*("
    r"\[IMAGE[^\]]*\]"           # [IMAGE_1], [IMAGE: abc123...]
    r"|\[TABLE[^\]]*\]"          # [TABLE_1], [TABLE: ...]
    r"|\[IMG[^\]]*\]"            # [IMG_1]
    r"|<IMAGE[^>]*>"             # <IMAGE ...>
    r"|\[IMAGE:\s*[a-f0-9]{8,}\]"  # [IMAGE: hexhash] — v7 addition
    r")\s*$",
    _re.IGNORECASE,
)


def detect_features(text: str, json_data: Optional[Dict] = None) -> Dict[str, Any]:
    img_markers = _IMG_PAT.findall(text)
    table_rows  = _TBL_PAT.findall(text)
    code_blocks = _COD_PAT.findall(text)

    json_img_map: Dict[str, Dict] = {}
    json_tbl_map: Dict[str, Dict] = {}
    if json_data:
        for img in json_data.get("images", []):
            json_img_map[img.get("marker", "")] = img
        for tbl in json_data.get("tables", []):
            json_tbl_map[tbl.get("marker", "")] = tbl

    images_detailed: List[Dict] = []
    for i, marker in enumerate(img_markers):
        pos = text.find(marker)
        detail: Dict[str, Any] = {
            "image_id":      f"img_{i + 1}",
            "marker":        marker,
            "position": {
                "char_in_chunk": pos,
                "char_absolute": pos,
                "line_number":   text[:pos].count("\n") + 1,
            },
            "context": {
                "before": text[max(0, pos - 60): pos],
                "after":  text[pos + len(marker): pos + len(marker) + 60],
            },
            "marker_length": len(marker),
        }
        if marker in json_img_map:
            detail["json_data"] = json_img_map[marker]
        images_detailed.append(detail)

    tables_detailed: List[Dict] = []
    for i, row in enumerate(table_rows[:20]):
        detail: Dict[str, Any] = {"row_index": i, "content": row}
        for marker, tbl_data in json_tbl_map.items():
            if marker in text:
                detail["marker"]    = marker
                detail["json_data"] = tbl_data
                break
        tables_detailed.append(detail)

    return {
        "total_images":      len(img_markers),
        "total_tables":      len(table_rows),
        "total_code_blocks": len(code_blocks),
        "has_media":         bool(img_markers or table_rows),
        "image_summary":     img_markers[:20],
        "table_summary":     table_rows[:10],
        "images_detailed":   images_detailed,
        "tables_detailed":   tables_detailed,
        "markdown_tables":   table_rows[:10],
        "code_blocks":       [cb[:200] for cb in code_blocks],
    }


def infer_content_type(features: Dict[str, Any]) -> str:
    if features["total_code_blocks"] > 0: return "code"
    if features["total_tables"]      > 0: return "table"
    if features["total_images"]      > 0: return "image_section"
    return "text"


# ═══════════════════════════════════════════════════════════════════════════════
# FILE DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def discover_files(root: Path) -> List[Dict[str, Any]]:
    """
    Recursively discover all .txt and .json files under *root*.
    Pairs name.txt with name.json companions (same stem, same directory).
    Returns descriptors sorted by (folder_path, filename).
    """
    txt_paths: List[Path] = []
    json_by_dir: Dict[Path, List[Path]] = defaultdict(list)

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf == ".txt":
            txt_paths.append(p)
        elif suf == ".json":
            json_by_dir[p.parent].append(p)

    descriptors: List[Dict[str, Any]] = []
    paired_jsons: set = set()

    for tp in sorted(txt_paths):
        folder_rel = _posix(tp.parent, root) if tp.parent != root else ""
        depth      = len(tp.relative_to(root).parts) - 1

        companion: Optional[Path] = None
        for jp in json_by_dir.get(tp.parent, []):
            if jp.stem == tp.stem:
                companion = jp
                paired_jsons.add(jp)
                break

        descriptors.append({
            "type":           "txt",
            "path":           tp,
            "relative_path":  _posix(tp, root),
            "folder_path":    folder_rel,
            "folder_name":    tp.parent.name if tp.parent != root else "",
            "folder_depth":   depth,
            "companion_json": companion,
        })

    # Standalone .json files
    for parent_dir in sorted(json_by_dir):
        for jp in sorted(json_by_dir[parent_dir]):
            if jp in paired_jsons:
                continue
            folder_rel = _posix(jp.parent, root) if jp.parent != root else ""
            depth      = len(jp.relative_to(root).parts) - 1
            descriptors.append({
                "type":           "json_standalone",
                "path":           jp,
                "relative_path":  _posix(jp, root),
                "folder_path":    folder_rel,
                "folder_name":    jp.parent.name if jp.parent != root else "",
                "folder_depth":   depth,
                "companion_json": None,
            })

    descriptors.sort(key=lambda d: (d["folder_path"], d["relative_path"]))
    return descriptors


# ═══════════════════════════════════════════════════════════════════════════════
# JSON COMPANION PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def parse_json_file(json_path: Path) -> Dict[str, Any]:
    """
    Parse a .json file and extract images, tables, code blocks.
    Normalises every item to have a 'marker' field.
    Handles multiple real-world schemas.
    """
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        logger.warning("Cannot parse JSON '%s': %s", json_path.name, exc)
        return {"images": [], "tables": [], "code_blocks": [], "raw": {}}

    images:      List[Dict] = []
    tables:      List[Dict] = []
    code_blocks: List[Dict] = []

    _IMG_KEYS = {"images", "image_list", "imgs", "figures", "image_data", "img_list"}
    _TBL_KEYS = {"tables", "table_list", "tbls", "table_data", "tbl_list"}
    _COD_KEYS = {"code_blocks", "codes", "snippets", "code_list"}
    _IMG_ITEM = {"marker", "image_id", "img_id", "src", "image_path", "figure_id"}
    _TBL_ITEM = {"marker", "table_id", "headers", "rows", "columns", "tbl_id"}

    def _scan(d: Dict) -> None:
        for key, val in d.items():
            if not isinstance(val, list):
                continue
            lk = key.lower()
            if lk in _IMG_KEYS:
                images.extend(val)
            elif lk in _TBL_KEYS:
                tables.extend(val)
            elif lk in _COD_KEYS:
                code_blocks.extend(val)
            elif val and isinstance(val[0], dict):
                sample = set(val[0].keys())
                if sample & _IMG_ITEM:
                    images.extend(val)
                elif sample & _TBL_ITEM:
                    tables.extend(val)

    if isinstance(raw, dict):
        _scan(raw)
        for v in raw.values():
            if isinstance(v, dict):
                _scan(v)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                sample = set(item.keys())
                if sample & _IMG_ITEM:
                    images.append(item)
                elif sample & _TBL_ITEM:
                    tables.append(item)

    # Normalise: guarantee 'marker' field
    for i, img in enumerate(images):
        if "marker" not in img:
            img_id = img.get("image_id") or img.get("img_id") or img.get("id") or str(i + 1)
            img["marker"] = f"[IMAGE_{img_id}]"
    for i, tbl in enumerate(tables):
        if "marker" not in tbl:
            tbl_id = tbl.get("table_id") or tbl.get("tbl_id") or tbl.get("id") or str(i + 1)
            tbl["marker"] = f"[TABLE_{tbl_id}]"

    return {"images": images, "tables": tables, "code_blocks": code_blocks, "raw": raw}


# ═══════════════════════════════════════════════════════════════════════════════
# SMART ENCODING READER  (FIX v6)
# ═══════════════════════════════════════════════════════════════════════════════

def _read_text_smart(fp: Path) -> str:
    """
    Read a text file with automatic encoding detection.

    Strategy:
      1. Try UTF-8. If the replacement-character ratio is > 1%, the file is
         likely Windows-1252 that happened to have valid-but-wrong UTF-8 bytes.
      2. Fall back to Windows-1252 (covers the full Latin-1 supplement range
         used by French, German, etc.).
      3. Last resort: UTF-8 with errors='replace'.

    After decoding, normalise common Windows encoding artifacts:
      \\xa0  non-breaking space   → regular space
      \\x91  Windows left  '      → Unicode '
      \\x92  Windows right '      → Unicode '
      \\x93  Windows left  "      → Unicode "
      \\x94  Windows right "      → Unicode "
      \\x96  Windows en-dash      → Unicode –
      \\x97  Windows em-dash      → Unicode —
    Then NFC-normalise to collapse composed/decomposed Unicode variants.
    """
    import unicodedata as _ud

    raw_bytes = fp.read_bytes()

    # Step 1 — try UTF-8
    try:
        text = raw_bytes.decode("utf-8")
        replacement_ratio = text.count("\ufffd") / max(len(text), 1)
        if replacement_ratio > 0.01:
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "too many replacement chars")
    except UnicodeDecodeError:
        # Step 2 — try Windows-1252
        try:
            text = raw_bytes.decode("windows-1252")
            logger.debug("Re-decoded '%s' as windows-1252 (UTF-8 had too many errors)", fp.name)
        except UnicodeDecodeError:
            # Step 3 — last resort
            text = raw_bytes.decode("utf-8", errors="replace")
            logger.warning("Could not decode '%s' cleanly; using UTF-8 with replacement", fp.name)

    # Normalise Windows-1252 control-range artifacts that survive decoding
    _WIN_MAP = {
        "\xa0": " ",   # non-breaking space
        "\x91": "\u2018",  # left single quote
        "\x92": "\u2019",  # right single quote / apostrophe
        "\x93": "\u201c",  # left double quote
        "\x94": "\u201d",  # right double quote
        "\x96": "\u2013",  # en-dash
        "\x97": "\u2014",  # em-dash
    }
    for bad, good in _WIN_MAP.items():
        text = text.replace(bad, good)

    # FIX v7: normalise Windows CRLF (\r\n) and bare CR (\r) to Unix LF (\n).
    # CRLF survived in many source files even after encoding fixes and caused
    # chunk fragments like 'Pour ce faire, Harmony affecte\r\nchaque utilisateur'
    # to be treated as two logical lines, breaking sentence boundary detection.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return _ud.normalize("NFC", text)


# ═══════════════════════════════════════════════════════════════════════════════
# FILE PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════

# Internal result from _process_segment
_SegResult = Dict[str, Any]  # {text, scores, status, method, retry_depth}


class FileProcessor:
    """
    Recursively chunks and validates a single text segment.
    Uses *judge* for LLM scoring.
    Never returns a chunk without a real LLM score.
    """

    def __init__(self, judge: LLMJudge) -> None:
        self._judge = judge

    # ── recursive rechunking ──────────────────────────────────────────────────

    def _process_segment(
        self,
        text: str,
        original_text: str,   # FIX v4: threaded through all recursion levels
        depth: int = 0,
    ) -> List[_SegResult]:
        """
        Chunk *text* with the strategy at *depth*, validate via LLM.

        original_text is the full source document and is passed to the LLM
        judge at every recursion depth so fidelity is always measured against
        the same reference, even when rechunking a sub-chunk.

        For each chunk:
          - score >= ACCEPT_SCORE  →  accepted
          - score <  ACCEPT_SCORE and depth < MAX_RECHUNK_DEPTH
                                   →  rechunk the chunk with next strategy
          - depth == MAX_RECHUNK_DEPTH →  force-accept with real LLM score
          - score is None (LLM failure)  →  drop chunk (logged)

        Returns list of _SegResult dicts (only non-dropped chunks).
        """
        strategy = ChunkingStrategies.STRATEGY_NAMES[
            min(depth, len(ChunkingStrategies.STRATEGY_NAMES) - 1)
        ]
        raw_chunks = ChunkingStrategies.apply(text, strategy)
        results: List[_SegResult] = []

        for chunk in raw_chunks:
            # Enforce bounds one more time for safety
            bounded = ChunkingStrategies.enforce_bounds([chunk])
            if not bounded:
                continue
            chunk = bounded[0]

            # FIX v5: skip chunks that are only an image/table marker — the LLM
            # has no text to evaluate and will always return 0 for every criterion
            if _PURE_MARKER_PAT.match(chunk):
                logger.debug("Skipping pure marker chunk (no scorable text): %.60r", chunk)
                continue

            # FIX v4: pass original_text so fidelity has a reference
            scores = self._judge.evaluate(chunk, original_text=original_text)

            if scores is None:
                logger.error(
                    "Chunk unscored after %d LLM retries — dropping: %.60r",
                    Config.LLM_RETRIES, chunk,
                )
                continue

            if scores["final_score"] >= Config.ACCEPT_SCORE:
                status = "accepted" if depth == 0 else f"accepted_retry_depth_{depth}"
                results.append({
                    "text":        chunk,
                    "scores":      scores,
                    "status":      status,
                    "method":      strategy,
                    "retry_depth": depth,
                })

            elif depth < Config.MAX_RECHUNK_DEPTH:
                next_strategy = ChunkingStrategies.STRATEGY_NAMES[
                    min(depth + 1, len(ChunkingStrategies.STRATEGY_NAMES) - 1)
                ]
                logger.debug(
                    "Chunk rejected (score=%.2f, depth=%d) → rechunking with '%s'",
                    scores["final_score"], depth, next_strategy,
                )
                # FIX v4: pass original_text into recursive call
                sub = self._process_segment(chunk, original_text=original_text, depth=depth + 1)
                if sub:
                    results.extend(sub)
                else:
                    # Rechunking produced nothing → keep with real score
                    results.append({
                        "text":        chunk,
                        "scores":      scores,
                        "status":      "accepted_empty_sub",
                        "method":      strategy,
                        "retry_depth": depth,
                    })
            else:
                # FIX v5: max depth reached — only accept if score > 0.
                # A confirmed 0.0 score means the chunk is genuinely bad;
                # accepting it would pollute the RAG index.
                if scores["final_score"] == 0.0:
                    logger.warning(
                        "Max rechunk depth reached but score=0.0 — dropping: %.60r", chunk
                    )
                    # Do not append — discard silently
                else:
                    logger.warning(
                        "Max rechunk depth reached (score=%.2f) — accepting: %.60r",
                        scores["final_score"], chunk,
                    )
                    results.append({
                        "text":        chunk,
                        "scores":      scores,
                        "status":      "accepted_max_depth",
                        "method":      strategy,
                        "retry_depth": depth,
                    })

        return results

    # ── public: process a .txt file ───────────────────────────────────────────

    def process_txt_file(
        self,
        desc:           Dict[str, Any],
        chunk_id_start: int,
        root:           Path,
        json_data:      Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        fp   = desc["path"]

        # FIX v6: smart encoding detection (UTF-8 → Windows-1252 fallback)
        # replaces the manual replace() calls from v5
        text = _read_text_smart(fp)

        if not text.strip():
            logger.warning("Empty file: %s", fp)
            return []

        token_count = count_tokens(text)

        # ── Small file → pass-through, NO LLM call, hardcoded 1.0 scores ─────
        if token_count < Config.THRESHOLD:
            logger.info(
                "Under threshold (%d < %d) — pass-through: %s",
                token_count, Config.THRESHOLD, fp.name,
            )
            raw_results: List[_SegResult] = [{
                "text":        text,
                "scores":      dict(Config.PASSTHROUGH_SCORES),  # copy
                "status":      "original_untouched",
                "method":      "none",
                "retry_depth": 0,
            }]
        else:
            # FIX v4: pass text as original_text reference for fidelity scoring
            raw_results = self._process_segment(text, original_text=text, depth=0)

        if not raw_results:
            logger.warning("No chunks produced for: %s", fp.name)
            return []

        # Log per-file stats
        n_pass   = sum(1 for r in raw_results if r["status"] == "original_untouched")
        n_clean  = sum(1 for r in raw_results if r["status"] == "accepted")
        n_retry  = sum(1 for r in raw_results if "retry" in r["status"])
        n_maxd   = sum(1 for r in raw_results if "max_depth" in r["status"])
        logger.debug(
            "%s → %d chunks  (%d passthrough / %d clean / %d retry / %d max_depth)",
            fp.name, len(raw_results), n_pass, n_clean, n_retry, n_maxd,
        )

        # Build full metadata entries
        total_chunks  = len(raw_results)
        now           = datetime.now(timezone.utc).isoformat()
        companion_rel = (
            _posix(desc["companion_json"], root) if desc.get("companion_json") else None
        )

        entries: List[Dict[str, Any]] = []
        for i, item in enumerate(raw_results):
            chunk      = item["text"]
            chunk_toks = count_tokens(chunk)
            features   = detect_features(chunk, json_data)
            start_pos  = (
                text.find(chunk[:60]) if len(chunk) >= 60 else text.find(chunk)
            )

            # FIX v6: detect chunks that start mid-sentence (upstream split artifact).
            # A chunk starting with a lowercase letter, closing punctuation, or a
            # continuation word strongly suggests the split happened inside a sentence.
            _first_char = chunk.lstrip()[:1]
            _boundary_issue = bool(
                _first_char and (
                    _first_char.islower()
                    or _first_char in (')', ']', '}', '.', ',', ';', ':', '!', '?', '"', "'")
                )
            )
            if _boundary_issue:
                logger.debug("Boundary issue detected (starts mid-sentence): %.60r", chunk)

            # Map internal status → canonical validation_status
            val_status = (
                "accepted_max_depth"
                if item["status"] == "accepted_max_depth"
                else "accepted"
            )

            # ── Merge media metadata from companion JSON when available ───────
            if json_data and item["status"] == "original_untouched":
                # For untouched files, prefer the companion's media data
                media_images_detailed = json_data.get("images", features["images_detailed"])
                media_tables_detailed = json_data.get("tables", features["tables_detailed"])
                media_image_summary   = (
                    [img.get("marker", "") for img in json_data.get("images", [])]
                    or features["image_summary"]
                )
                media_table_summary   = (
                    [tbl.get("marker", "") for tbl in json_data.get("tables", [])]
                    or features["table_summary"]
                )
                media_code_blocks     = json_data.get("code_blocks", features["code_blocks"])
                media_total_images    = len(json_data.get("images", [])) or features["total_images"]
                media_total_tables    = len(json_data.get("tables", [])) or features["total_tables"]
                media_total_code      = len(json_data.get("code_blocks", [])) or features["total_code_blocks"]
                media_has_media       = bool(media_total_images or media_total_tables)
                media_markdown_tables = features["markdown_tables"]
            else:
                # For chunked files, use per-chunk detection, supplemented by JSON
                media_images_detailed = features["images_detailed"]
                media_tables_detailed = features["tables_detailed"]
                media_image_summary   = features["image_summary"]
                media_table_summary   = features["table_summary"]
                media_code_blocks     = features["code_blocks"]
                media_total_images    = features["total_images"]
                media_total_tables    = features["total_tables"]
                media_total_code      = features["total_code_blocks"]
                media_has_media       = features["has_media"]
                media_markdown_tables = features["markdown_tables"]

            entry: Dict[str, Any] = {
                # ── text ──────────────────────────────────────────────────────
                "text": chunk,

                # ── hierarchy ─────────────────────────────────────────────────
                "source_file":    fp.name,
                "original_path":  str(fp),
                "relative_path":  desc["relative_path"],
                "folder_path":    desc["folder_path"],
                "folder_name":    desc["folder_name"],
                "folder_depth":   desc["folder_depth"],

                # ── chunk position ────────────────────────────────────────────
                "chunk_id":             chunk_id_start + i,
                "total_chunks":         total_chunks,
                "token_count":          chunk_toks,
                "char_count":           len(chunk),
                "chunk_start_position": max(0, start_pos),

                # ── classification ────────────────────────────────────────────
                "section_title":   "",
                "content_type":    infer_content_type(features),
                "chunking_method": item["method"],
                "chunking_status": item["status"],
                "retry_depth":     item["retry_depth"],
                "low_content":     chunk_toks < Config.LOW_CONTENT_THRESHOLD,
                "boundary_issue":  _boundary_issue,   # FIX v6: mid-sentence start flag

                # ── validation ────────────────────────────────────────────────
                "validation_status": val_status,
                "validation_score":  item["scores"],

                # ── media (preserved from companion JSON when available) ──────
                "total_images":      media_total_images,
                "total_tables":      media_total_tables,
                "total_code_blocks": media_total_code,
                "has_media":         media_has_media,
                "image_summary":     media_image_summary,
                "table_summary":     media_table_summary,
                "images_detailed":   media_images_detailed,
                "tables_detailed":   media_tables_detailed,
                "markdown_tables":   media_markdown_tables,
                "code_blocks":       media_code_blocks,

                # ── companion JSON ────────────────────────────────────────────
                "json_companion": companion_rel,

                # ── timestamps ────────────────────────────────────────────────
                "timestamp":  now,
                "chunked_at": now,
            }
            entries.append(entry)

        return entries

    # ── public: process a standalone .json file ───────────────────────────────

    @staticmethod
    def process_standalone_json(
        desc:           Dict[str, Any],
        chunk_id_start: int,
        root:           Path,
    ) -> List[Dict[str, Any]]:
        fp   = desc["path"]
        data = parse_json_file(fp)
        now  = datetime.now(timezone.utc).isoformat()

        raw_text   = json.dumps(data["raw"], ensure_ascii=False)
        token_cnt  = count_tokens(raw_text)
        scores     = dict(Config.PASSTHROUGH_SCORES)

        return [{
            "text": raw_text,  # full text, no truncation

            "source_file":    fp.name,
            "original_path":  str(fp),
            "relative_path":  desc["relative_path"],
            "folder_path":    desc["folder_path"],
            "folder_name":    desc["folder_name"],
            "folder_depth":   desc["folder_depth"],

            "chunk_id":             chunk_id_start,
            "total_chunks":         1,
            "token_count":          token_cnt,
            "char_count":           len(raw_text),
            "chunk_start_position": 0,

            "section_title":   "",
            "content_type":    "structured_json",
            "chunking_method": "none",
            "chunking_status": "original_untouched",
            "retry_depth":     0,
            "low_content":     token_cnt < Config.LOW_CONTENT_THRESHOLD,

            "validation_status": "accepted",
            "validation_score":  scores,

            "total_images":      len(data["images"]),
            "total_tables":      len(data["tables"]),
            "total_code_blocks": len(data["code_blocks"]),
            "has_media":         bool(data["images"] or data["tables"]),
            "image_summary":     [img.get("marker", "") for img in data["images"]],
            "table_summary":     [tbl.get("marker", "") for tbl in data["tables"]],
            "images_detailed":   data["images"],
            "tables_detailed":   data["tables"],
            "markdown_tables":   [],
            "code_blocks":       data["code_blocks"],

            "json_companion": None,
            "timestamp":      now,
            "chunked_at":     now,
        }]


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT WRITERS
# ═══════════════════════════════════════════════════════════════════════════════

def write_chunks_txt(entries: List[Dict], output_path: str) -> None:
    """
    Unified chunks.txt — accepted chunks grouped under folder banners
    that mirror the input hierarchy.
    """
    accepted = [e for e in entries if e.get("validation_status") in ("accepted", "accepted_max_depth")]

    folders: Dict[str, List[Dict]] = defaultdict(list)
    for e in accepted:
        folders[e.get("folder_path", "")].append(e)

    with open(output_path, "w", encoding="utf-8") as fh:
        for folder_path in sorted(folders.keys()):
            label  = folder_path if folder_path else "[ROOT]"
            chunks = folders[folder_path]

            fh.write("=" * 72 + "\n")
            fh.write(f"FOLDER: {label}\n")
            fh.write("=" * 72 + "\n\n")

            for e in chunks:
                score  = e["validation_score"].get("final_score", 0.0)
                status = e.get("chunking_status", "")
                depth  = e.get("retry_depth", 0)
                low    = "  [LOW_CONTENT]" if e.get("low_content") else ""
                fh.write(
                    f"--- Chunk {e['chunk_id']}  [{e['source_file']}]"
                    f"  [{e['content_type']}]  [status={status}]"
                    f"  [score={score:.2f}]  [depth={depth}]{low} ---\n"
                )
                fh.write(e["text"])
                fh.write("\n\n")


def write_per_file_outputs(entries: List[Dict], desc: Dict[str, Any]) -> None:
    """
    Write per-file mirrored output:
      {OUTPUT_DIR}/{folder_path}/{stem}_chunks.txt  — accepted chunks
      {OUTPUT_DIR}/{folder_path}/{stem}_meta.json   — all chunk metadata
    """
    fp   = desc["path"]
    stem = fp.stem

    out_folder = Path(Config.OUTPUT_DIR)
    if desc["folder_path"]:
        out_folder = out_folder / desc["folder_path"]
    out_folder.mkdir(parents=True, exist_ok=True)

    # _chunks.txt
    chunks_path = out_folder / f"{stem}_chunks.txt"
    accepted = [e for e in entries if e.get("validation_status") in ("accepted", "accepted_max_depth")]
    with open(chunks_path, "w", encoding="utf-8") as fh:
        for e in accepted:
            score  = e["validation_score"].get("final_score", 0.0)
            status = e.get("chunking_status", "")
            low    = "  [LOW_CONTENT]" if e.get("low_content") else ""
            fh.write(f"--- Chunk {e['chunk_id']} [status={status}] [score={score:.2f}]{low} ---\n")
            fh.write(e["text"])
            fh.write("\n---\n")

    # _meta.json
    meta_path = out_folder / f"{stem}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# WORKER  (runs in ThreadPoolExecutor)
# ═══════════════════════════════════════════════════════════════════════════════

def _worker(
    desc:      Dict[str, Any],
    processor: FileProcessor,
    chunk_id:  int,
    root:      Path,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Process one file descriptor and return (desc, entries).
    Runs inside a thread — only LLM calls are serialised (via LLMJudge._lock).
    """
    try:
        if desc["type"] == "txt":
            json_data = parse_json_file(desc["companion_json"]) if desc["companion_json"] else None
            entries   = processor.process_txt_file(desc, chunk_id, root, json_data)
        else:
            entries = FileProcessor.process_standalone_json(desc, chunk_id, root)
    except Exception as exc:
        logger.error("Worker error on '%s': %s", desc["relative_path"], exc, exc_info=True)
        entries = []

    return desc, entries


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    setup_logging()
    nltk.download("punkt",     quiet=True)
    nltk.download("punkt_tab", quiet=True)

    root = Path(Config.INPUT_DIR)
    if not root.exists():
        logger.error("Input directory '%s' not found.", Config.INPUT_DIR)
        return

    all_files = discover_files(root)
    if not all_files:
        logger.warning("No .txt or .json files found under '%s'.", Config.INPUT_DIR)
        return

    logger.info(
        "Discovered %d file(s) across %d folder(s).",
        len(all_files), len({d["folder_path"] for d in all_files}),
    )

    cache = CacheManager(Config.CACHE_FILE)
    store = MetadataStore(Config.PARTIAL_FILE)

    # ── determine which files need processing ─────────────────────────────────
    pending: List[Dict] = []
    skipped = 0

    for desc in all_files:
        rel          = desc["relative_path"]
        current_hash = CacheManager.hash_file(desc["path"])

        if cache.file_is_done(rel) and cache.file_hash_matches(rel, current_hash):
            skipped += 1
            continue

        if cache.file_is_done(rel) and not cache.file_hash_matches(rel, current_hash):
            removed = store.remove_by_rel(rel)
            cache.unmark_file(rel)
            logger.info("File changed — reprocessing: %s  (%d old entry/entries removed)", rel, removed)

        pending.append(desc)

    logger.info(
        "%d file(s) to process  |  %d skipped (cached + unchanged).",
        len(pending), skipped,
    )

    if not pending:
        logger.info("Nothing to do — finalising outputs.")
    else:
        # Only load LLM if there are .txt files that might exceed THRESHOLD
        # (under-threshold files get hardcoded scores, no LLM needed)
        has_txt   = any(d["type"] == "txt" for d in pending)
        judge     = LLMJudge(cache) if has_txt else None
        processor = FileProcessor(judge) if judge else None

        # Assign stable chunk IDs up-front (serial, deterministic)
        id_map: Dict[str, int] = {}
        cid = cache.next_chunk_id
        for desc in pending:
            id_map[desc["relative_path"]] = cid
            cid += 10_000  # reserve generous space per file; updated after processing

        completed_results: List[Tuple[Dict, List[Dict]]] = []

        with ThreadPoolExecutor(max_workers=Config.MAX_IO_WORKERS) as executor:
            futures = {
                executor.submit(
                    _worker,
                    desc,
                    processor,
                    id_map[desc["relative_path"]],
                    root,
                ): desc
                for desc in pending
            }

            with tqdm(
                total=len(pending),
                desc="Chunking & validating",
                unit="file",
                dynamic_ncols=True,
            ) as pbar:
                for future in as_completed(futures):
                    src_desc = futures[future]
                    pbar.set_postfix(
                        folder=src_desc["folder_path"] or "[root]",
                        file=src_desc["path"].name,
                        refresh=False,
                    )
                    try:
                        result_desc, entries = future.result()
                        completed_results.append((result_desc, entries))
                    except Exception as exc:
                        logger.error("Future error for '%s': %s", src_desc["relative_path"], exc)
                    finally:
                        pbar.update(1)

        # ── re-number chunk IDs sequentially (post-parallel) ─────────────────
        # Sort completed results to match discovery order for deterministic IDs
        order_map = {d["relative_path"]: i for i, d in enumerate(pending)}
        completed_results.sort(key=lambda x: order_map.get(x[0]["relative_path"], 9999))

        global_chunk_id = cache.next_chunk_id
        for result_desc, entries in completed_results:
            rel = result_desc["relative_path"]
            # Re-assign sequential IDs
            for i, entry in enumerate(entries):
                entry["chunk_id"] = global_chunk_id + i
            if entries:
                total = len(entries)
                for entry in entries:
                    entry["total_chunks"] = total

            store.add(entries)
            cache.mark_file_done(rel, CacheManager.hash_file(result_desc["path"]), len(entries))
            cache.advance_id(len(entries))
            global_chunk_id += len(entries)

            write_per_file_outputs(entries, result_desc)

            accepted_n = sum(1 for e in entries if e.get("validation_status") in ("accepted", "accepted_max_depth"))
            logger.info(
                "Done: %-45s  chunks=%d  accepted=%d", rel, len(entries), accepted_n
            )

    cache.save()

    # ── finalise unified outputs ──────────────────────────────────────────────
    store.finalize(Config.OUTPUT_METADATA)
    write_chunks_txt(store.entries, Config.OUTPUT_CHUNKS)

    total       = len(store.entries)
    accepted    = sum(1 for e in store.entries if e.get("validation_status") in ("accepted", "accepted_max_depth"))
    passthrough = sum(1 for e in store.entries if e.get("chunking_status") == "original_untouched")
    low_content = sum(1 for e in store.entries if e.get("low_content"))
    logger.info(
        "Pipeline complete.  Total=%d  Accepted=%d  Passthrough=%d  LowContent=%d",
        total, accepted, passthrough, low_content,
    )
    logger.info(
        "Outputs: '%s'  '%s'  per-file → '%s/'",
        Config.OUTPUT_CHUNKS, Config.OUTPUT_METADATA, Config.OUTPUT_DIR,
    )


if __name__ == "__main__":
    main()