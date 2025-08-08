from __future__ import annotations

import os
import uuid
from typing import List, Dict, Any, Optional
import logging

import requests
from qdrant_client import QdrantClient, models
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter

from ..llm import get_llm

logger = logging.getLogger(__name__)


class RAGService:
    """
    Hybrid RAG over Qdrant using named vectors (dense + sparse) with RRF fusion.
    Requires embedding server exposing /hybrid-embed.
    """

    def __init__(
        self,
        embedding_url: Optional[str] = None,
        qdrant_url: Optional[str] = None,
    ) -> None:
        self.embedding_url = embedding_url or os.getenv("EMBEDDING_API_BASE")
        self.qdrant_client = QdrantClient(url=(qdrant_url or os.getenv("QDRANT_URL")))

    def get_vectors(self, texts: List[str]) -> Dict[str, Any]:
        resp = requests.post(f"{self.embedding_url}/hybrid-embed", json={"texts": texts}, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        if not data or "dense_vectors" not in data or "sparse_vectors" not in data:
            raise RuntimeError("Embedding server did not return both dense_vectors and sparse_vectors")
        return data

    def create_collection(self, collection_name: str, dense_vector_size: int = 1024) -> None:
        if not self.qdrant_client.collection_exists(collection_name):
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense_vectors": models.VectorParams(size=dense_vector_size, distance=models.Distance.COSINE)
                },
                sparse_vectors_config={
                    "sparse_vectors": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))
                },
            )

    def index_pdfs(
        self,
        pdf_paths: List[str],
        collection_name: str,
        user_id: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        dense_vector_size: int = 1024,
    ) -> Dict[str, Any]:
        documents = []
        for path in pdf_paths:
            loader = PyPDFLoader(path)
            docs = loader.load()
            for d in docs:
                d.metadata.update({"source": path, "filename": os.path.basename(path), "file_type": "pdf"})
            documents.extend(docs)

        if not documents:
            return {"collection": collection_name, "user_id": user_id, "chunks_indexed": 0, "points_upserted": 0}

        self.create_collection(collection_name, dense_vector_size=dense_vector_size)

        splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, separator="\n")
        split_docs = splitter.split_documents(documents)
        texts = [d.page_content for d in split_docs]
        metadatas = [d.metadata for d in split_docs]

        vecs = self.get_vectors(texts)
        dense_list = vecs["dense_vectors"]
        sparse_list = vecs["sparse_vectors"]

        points: List[models.PointStruct] = []
        for text, dense_vec, sparse_raw, meta in zip(texts, dense_list, sparse_list, metadatas):
            sparse_obj = models.SparseVector(indices=sparse_raw["indices"], values=sparse_raw["values"])
            payload = {"text": text, "metadata": {**meta, "user_id": user_id}}
            points.append(models.PointStruct(id=str(uuid.uuid4()), vector={"dense_vectors": dense_vec, "sparse_vectors": sparse_obj}, payload=payload))

        self.qdrant_client.upsert(collection_name=collection_name, points=points)
        return {"collection": collection_name, "user_id": user_id, "chunks_indexed": len(split_docs), "points_upserted": len(points)}

    def search(self, query: str, collection_name: str, user_id: str, limit: int = 5, score_threshold: float = 0.0) -> List[Dict[str, Any]]:
        vecs = self.get_vectors([query])
        dense = vecs["dense_vectors"][0]
        sparse_raw = vecs["sparse_vectors"][0]
        sparse_obj = models.SparseVector(indices=sparse_raw["indices"], values=sparse_raw["values"])
        user_filter = models.Filter(must=[models.FieldCondition(key="metadata.user_id", match=models.MatchValue(value=user_id))])
        hits = self.qdrant_client.query_points(
            collection_name=collection_name,
            prefetch=[
                models.Prefetch(query=dense, using="dense_vectors", limit=limit, score_threshold=score_threshold),
                models.Prefetch(query=sparse_obj, using="sparse_vectors", limit=limit, score_threshold=score_threshold),
            ],
            query_filter=user_filter,
            limit=limit,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
        )
        pts = hits.points if hasattr(hits, "points") else hits
        return [{"text": p.payload["text"], "metadata": p.payload.get("metadata", {}), "score": p.score} for p in pts]

    def generate(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        context = "\n".join(c["text"] for c in context_chunks)
        prompt = (
            "基於以下上下文，回答用戶的問題。請提供準確、有用的回答。\n\n"
            f"上下文：\n{context}\n\n用戶問題：{query}\n\n回答："
        )
        try:
            llm = get_llm()
            result = llm.invoke(prompt)
            return result.content if hasattr(result, "content") else str(result)
        except Exception as e:
            logger.error(f"LLM generate failed: {e}")
            # 回傳簡易 fallback，避免整體 500
            return "（提示：目前無法連線至文字生成服務，僅返回檢索到的內容摘要。）\n\n" + context[:800]

    def rag(self, query: str, collection_name: str, user_id: str, limit: int = 3) -> Dict[str, Any]:
        try:
            retrieved = self.search(query, collection_name, user_id, limit=limit)
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return {"response": f"檢索發生錯誤：{e}", "retrieved_docs": []}

        if not retrieved:
            return {"response": "抱歉，沒有找到相關的文檔。", "retrieved_docs": []}

        # 生成階段失敗時不要丟 500，回傳 fallback
        answer = self.generate(query, retrieved)
        return {"response": answer, "retrieved_docs": retrieved}


