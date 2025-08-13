from __future__ import annotations

import os
import uuid
from typing import List, Dict, Any, Optional, Union
import logging
import requests
import scipy.sparse as sp
from pymilvus import MilvusClient, DataType
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter

from ..llm import get_llm

logger = logging.getLogger(__name__)


class RAGService:
    """
    Hybrid RAG over Milvus using dense and sparse vectors with RRF fusion.
    Requires embedding server exposing /hybrid-embed.
    """

    def __init__(
        self,
        embedding_url: Optional[str] = None,
        milvus_uri: Optional[str] = None,
    ) -> None:
        self.embedding_url = embedding_url or os.getenv("EMBEDDING_API_BASE")
        self.milvus_client = MilvusClient(uri=milvus_uri or os.getenv("MILVUS_URI", "http://192.168.1.193:19530"))
        self.sparse_vector_dim = 262144  # Default dimension for sparse vectors

    def get_vectors(self, texts: List[str]) -> Dict[str, Any]:
        """Get dense and sparse vectors from the embedding service."""
        try:
            resp = requests.post(
                f"{self.embedding_url}/hybrid-embed",
                json={"texts": texts},
                timeout=120
            )
            resp.raise_for_status()
            data = resp.json()
            if not data or "dense_vectors" not in data or "sparse_vectors" not in data:
                raise RuntimeError("Embedding server did not return both dense_vectors and sparse_vectors")
            return data
        except Exception as e:
            logger.error(f"Failed to get vectors: {e}")
            raise

    def create_collection(self, collection_name: str, dense_vector_size: int = 1024) -> None:
        """Create or verify a Milvus collection with proper indexes."""
        try:
            # Define index parameters
            dense_index_params = self.milvus_client.prepare_index_params()
            dense_index_params.add_index(
                field_name="dense_vectors",
                index_type="HNSW",
                metric_type="COSINE",
                params={"M": 16, "efConstruction": 256}
            )
            
            sparse_index_params = self.milvus_client.prepare_index_params()
            sparse_index_params.add_index(
                field_name="sparse_vectors",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP"
            )
            
            scalar_index_params = self.milvus_client.prepare_index_params()
            scalar_index_params.add_index(
                field_name="user_id",
                index_type="INVERTED"
            )
            
            # Check if collection exists
            if not self.milvus_client.has_collection(collection_name):
                # Define schema
                schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
                schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
                schema.add_field(field_name="user_id", datatype=DataType.VARCHAR, max_length=256)
                schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=4000)
                schema.add_field(field_name="metadata", datatype=DataType.JSON)
                schema.add_field(field_name="dense_vectors", datatype=DataType.FLOAT_VECTOR, dim=dense_vector_size)
                schema.add_field(field_name="sparse_vectors", datatype=DataType.SPARSE_FLOAT_VECTOR)
                
                # Create collection
                self.milvus_client.create_collection(
                    collection_name=collection_name,
                    schema=schema
                )
                
                # Create indexes
                self.milvus_client.create_index(collection_name, dense_index_params)
                self.milvus_client.create_index(collection_name, sparse_index_params)
                self.milvus_client.create_index(collection_name, scalar_index_params)
            
            # Load collection to memory
            self.milvus_client.load_collection(collection_name)
            
        except Exception as e:
            logger.error(f"Failed to create or load collection: {e}")
            raise

    def _rerank_rrf(self, results_list: List[List[Dict]], k: int = 60) -> List[Dict]:
        """Rerank multiple search results using Reciprocal Rank Fusion (RRF)."""
        ranked_lists = []
        for res in results_list:
            ranked_lists.append({hit['id']: rank + 1 for rank, hit in enumerate(res)})

        rrf_scores = {}
        all_doc_ids = set()
        for rlist in ranked_lists:
            all_doc_ids.update(rlist.keys())

        for doc_id in all_doc_ids:
            score = 0.0
            for rlist in ranked_lists:
                if doc_id in rlist:
                    score += 1.0 / (k + rlist[doc_id])
            rrf_scores[doc_id] = score

        sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda id: rrf_scores[id], reverse=True)
        all_hits_map = {}
        for res in results_list:
            for hit in res:
                if hit['id'] not in all_hits_map:
                    all_hits_map[hit['id']] = hit

        final_results = []
        for doc_id in sorted_doc_ids:
            hit = all_hits_map[doc_id]
            final_results.append({
                "text": hit['entity']['text'],
                "metadata": hit['entity']['metadata'],
                "score": rrf_scores[doc_id]
            })

        return final_results

    def index_pdfs(
        self,
        pdf_paths: List[str],
        collection_name: str,
        user_id: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        dense_vector_size: int = 1024,
    ) -> Dict[str, Any]:
        """Index PDF documents into the Milvus collection."""
        documents = []
        for path in pdf_paths:
            loader = PyPDFLoader(path)
            docs = loader.load()
            for d in docs:
                d.metadata.update({
                    "source": path,
                    "filename": os.path.basename(path),
                    "file_type": "pdf"
                })
            documents.extend(docs)

        if not documents:
            return {
                "collection": collection_name,
                "user_id": user_id,
                "chunks_indexed": 0,
                "points_upserted": 0
            }

        self.create_collection(collection_name, dense_vector_size=dense_vector_size)
        splitter = CharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator="\n"
        )
        split_docs = splitter.split_documents(documents)
        texts = [d.page_content for d in split_docs]
        metadatas = [d.metadata for d in split_docs]

        vecs = self.get_vectors(texts)
        dense_embeddings = vecs["dense_vectors"]
        sparse_embeddings = vecs["sparse_vectors"]

        data_to_insert = []
        for text, dense_vec, sparse_raw, meta in zip(texts, dense_embeddings, sparse_embeddings, metadatas):
            indices = sparse_raw['indices']
            values = sparse_raw['values']
            sparse_vec = sp.csr_matrix(
                (values, ([0] * len(indices), indices)),
                shape=(1, self.sparse_vector_dim)
            )
            
            entity = {
                "user_id": user_id,
                "text": text,
                "metadata": {**meta, "user_id": user_id},
                "dense_vectors": dense_vec,
                "sparse_vectors": sparse_vec
            }
            data_to_insert.append(entity)

        res = self.milvus_client.insert(
            collection_name=collection_name,
            data=data_to_insert
        )
        self.milvus_client.flush(collection_name=collection_name)
        
        return {
            "collection": collection_name,
            "user_id": user_id,
            "chunks_indexed": len(split_docs),
            "points_upserted": res['insert_count']
        }

    def search(self, query: str, collection_name: str, user_id: str, limit: int = 5, score_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """Search for similar documents using hybrid search with RRF reranking."""
        try:
            # Get query vectors
            data = self.get_vectors([query])
            if not data or 'dense_vectors' not in data or 'sparse_vectors' not in data:
                logger.error("Failed to generate query vectors")
                return []

            dense_vector = data['dense_vectors'][0]
            sparse_raw_vector = data['sparse_vectors'][0]
            
            # Convert sparse vector to CSR format
            sparse_vector = sp.csr_matrix(
                (sparse_raw_vector['values'], ([0] * len(sparse_raw_vector['indices']), sparse_raw_vector['indices'])),
                shape=(1, self.sparse_vector_dim)
            )

            # Create user filter
            user_filter = f'user_id == "{user_id}"'

            # Perform dense vector search
            dense_results = self.milvus_client.search(
                collection_name=collection_name,
                data=[dense_vector],
                filter=user_filter,
                limit=limit,
                anns_field="dense_vectors",
                output_fields=["text", "metadata", "user_id"]
            )[0]

            # Perform sparse vector search
            sparse_results = self.milvus_client.search(
                collection_name=collection_name,
                data=sparse_vector,
                filter=user_filter,
                limit=limit,
                anns_field="sparse_vectors",
                output_fields=["text", "metadata", "user_id"]
            )[0]

            # Rerank results using RRF
            final_results = self._rerank_rrf([dense_results, sparse_results])
            
            # Format results to match expected output
            return [{
                "text": res["text"],
                "metadata": res["metadata"],
                "score": res["score"]
            } for res in final_results[:limit]]
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def generate(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Generate a response using the language model."""
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
            # Return a fallback response
            return "（提示：目前無法連線至文字生成服務，僅返回檢索到的內容摘要。）\n\n" + context[:800]

    def rag(self, query: str, collection_name: str, user_id: str, limit: int = 3) -> Dict[str, Any]:
        """Complete RAG pipeline: retrieve and generate."""
        try:
            retrieved = self.search(query, collection_name, user_id, limit=limit)
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return {"response": f"檢索發生錯誤：{e}", "retrieved_docs": []}

        if not retrieved:
            return {"response": "抱歉，沒有找到相關的文檔。", "retrieved_docs": []}

        # Generate response (with fallback on failure)
        answer = self.generate(query, retrieved)
        return {"response": answer, "retrieved_docs": retrieved}


