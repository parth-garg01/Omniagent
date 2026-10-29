import hashlib
import math
import re
from typing import Protocol

DIM = 256
_STOP = {"the", "a", "an", "is", "are", "of", "to", "and", "or", "in", "on", "for", "what", "how",
         "do", "does", "i", "my", "can", "we", "our", "it", "this", "that", "with", "be", "me",
         "you", "your", "about", "tell", "please", "was", "were", "at", "by", "as"}


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in _STOP:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


class HashingEmbedder:
    """Deterministic offline embedder (hashed bag-of-words, L2 normalised).

    A stand-in for a real embedding model: it captures lexical overlap only, not semantics.
    Swap in a real adapter implementing `Embedder` for production-quality retrieval.
    """

    name = "hashing-256"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for t in texts:
            v = [0.0] * DIM
            for tok in tokens(t):
                h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:4], "big")
                v[h % DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vecs.append([x / norm for x in v])
        return vecs


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


_embedder: Embedder = HashingEmbedder()


def get_embedder() -> Embedder:
    return _embedder
