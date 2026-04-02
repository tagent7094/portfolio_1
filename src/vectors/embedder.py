"""Embedding model wrapper using SentenceTransformers."""

from __future__ import annotations


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts."""
        return self.model.encode(texts).tolist()

    def similarity(self, text1: str, text2: str) -> float:
        """Compute cosine similarity between two texts."""
        from sklearn.metrics.pairwise import cosine_similarity

        emb1, emb2 = self.embed([text1, text2])
        return float(cosine_similarity([emb1], [emb2])[0][0])
