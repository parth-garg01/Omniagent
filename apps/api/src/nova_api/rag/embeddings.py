import hashlib
import math
import re
from typing import Protocol

SPACE = 1 << 20  # sparse hashing space; collisions between distinct tokens are ~1e-6
_STOP = {"the", "a", "an", "is", "are", "of", "to", "and", "or", "in", "on", "for", "what", "how",
         "do", "does", "i", "my", "can", "we", "our", "it", "this", "that", "with", "be", "me",
         "you", "your", "about", "tell", "please", "was", "were", "at", "by", "as"}


Vector = dict[str, float]  # sparse {bucket: weight}; JSON-serialisable


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[Vector]: ...


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
    """Deterministic offline embedder (sparse hashed bag-of-words, L2 normalised).

    A stand-in for a real embedding model: it captures lexical overlap only, not semantics.
    Swap in a real adapter implementing `Embedder` for production-quality retrieval.
    """

    name = "hashing-sparse-1m"

    def embed(self, texts: list[str]) -> list[Vector]:
        vecs: list[Vector] = []
        for t in texts:
            v: dict[str, float] = {}
            for tok in tokens(t):
                h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:8], "big") % SPACE
                v[str(h)] = v.get(str(h), 0.0) + 1.0
            norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
            vecs.append({k: x / norm for k, x in v.items()})
        return vecs


def cosine(a: Vector, b: Vector) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(k, 0.0) for k, w in a.items())


_embedder: Embedder = HashingEmbedder()


def get_embedder() -> Embedder:
    return _embedder
