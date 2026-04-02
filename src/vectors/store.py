"""ChromaDB vector store operations."""

from __future__ import annotations


class VectorStore:
    def __init__(self, persist_dir: str = "data/knowledge-graph/chroma"):
        import chromadb

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection("founder_content")

    def add(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ):
        """Add documents with embeddings to the store."""
        self.collection.add(
            ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings
        )

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        where: dict = None,
    ) -> dict:
        """Search for similar documents."""
        kwargs = {"query_embeddings": [query_embedding], "n_results": n_results}
        if where:
            kwargs["where"] = where
        return self.collection.query(**kwargs)

    def count(self) -> int:
        """Return the number of documents in the store."""
        return self.collection.count()
