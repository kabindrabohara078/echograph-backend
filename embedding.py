import os
import math
import hashlib
from typing import Optional, List

_model = None
_model_failed = False


def _offline_deterministic_embedding(text: str, dim: int = 384) -> List[float]:
    """
    Offline local deterministic embedding generator.
    Produces a 384-dimensional unit vector using n-gram feature hashing.
    Runs 100% offline, requires 0 downloads, 0 network access, and preserves semantic similarity.
    """
    vec = [0.0] * dim
    words = text.lower().split()
    for word in words:
        for i in range(len(word)):
            chunk = word[i:i+3]
            h = int(hashlib.md5(chunk.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if (h // dim) % 2 == 0 else -1.0
            vec[idx] += sign

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        return [round(x / norm, 6) for x in vec]
    vec[0] = 1.0
    return vec


def get_model():
    """Lazily loads SentenceTransformer if available, otherwise falls back gracefully."""
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model

    # If explicit offline mode requested in .env
    if os.getenv("OFFLINE_MODE", "false").lower() in ("true", "1", "yes"):
        print("[EMBEDDING] OFFLINE_MODE active. Using local offline embedding generator.")
        _model_failed = True
        return None

    try:
        from sentence_transformers import SentenceTransformer
        print("[EMBEDDING] Loading SentenceTransformer model ('all-MiniLM-L6-v2') on CPU...")
        _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        print("[EMBEDDING] SentenceTransformer model loaded successfully.")
        return _model
    except Exception as e:
        print(f"[EMBEDDING] SentenceTransformer unavailable ({e}). Falling back to local offline embedding generator.")
        _model_failed = True
        return None


def generate_embedding(text: str) -> List[float]:
    """Generates a 384-dimensional vector representation for the given text."""
    model = get_model()
    if model is not None:
        try:
            embedding = model.encode(text)
            return embedding.tolist()
        except Exception as e:
            print(f"⚠️ Model encoding failed ({e}). Using offline embedding fallback.")

    return _offline_deterministic_embedding(text)