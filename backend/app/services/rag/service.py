import os
import uuid
import logging
import tempfile
import shutil
from typing import List, Dict, Any, Optional, TypedDict, Union, Tuple
from pathlib import Path

import requests
import scipy.sparse as sp
from app.services.llm import get_llm
from pymilvus import MilvusClient, DataType, CollectionSchema, FieldSchema
from langchain_community.document_loaders import PyPDFLoader
from langchain.schema.document import Document
from langchain.text_splitter import CharacterTextSplitter

logger = logging.getLogger(__name__)

class RAGService:
    """
    Hybrid RAG over Milvus using dense and sparse vectors with RRF fusion.
    Requires embedding server exposing /hybrid-embed.
    """
    
    # Default configuration constants
    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 200
    DEFAULT_VECTOR_DIM = 1024
    DEFAULT_SPARSE_DIM = 262144
    DEFAULT_SEARCH_LIMIT = 5
    
    # Milvus index parameters
    HNSW_INDEX_PARAMS = {"M": 16, "efConstruction": 256}
    
    def __init__(
        self,
        embedding_url: Optional[str] = None,
        milvus_uri: Optional[str] = None,
    ) -> None:
        """Initialize the RAG service.
        
        Args:
            embedding_url: URL of the embedding service
            milvus_uri: URI of the Milvus server
        """
        self.embedding_url = (embedding_url or os.getenv("EMBEDDING_API_BASE")).rstrip('/')
        self.milvus_uri = milvus_uri or os.getenv("MILVUS_URI", "http://192.168.1.193:19530")
        self.milvus_client = MilvusClient(uri=self.milvus_uri)
        self.sparse_vector_dim = self.DEFAULT_SPARSE_DIM

    def get_vectors(self, texts: List[str]) -> Dict[str, Any]:
        """Get dense and sparse vectors from the embedding service.
        
        Args:
            texts: List of text strings to encode
            
        Returns:
            Dict containing 'dense_vectors' and 'sparse_vectors'
            
        Raises:
            HTTPError: If the request to the embedding service fails
            ValueError: If the response is malformed
        """
        if not texts:
            raise ValueError("No texts provided for vectorization")
            
        url = f"{self.embedding_url}/hybrid-embed"
        logger.debug(f"Requesting vectors for {len(texts)} texts from {url}")
        
        try:
            resp = requests.post(
                url,
                json={"texts": texts},
                timeout=120
            )
            resp.raise_for_status()
            data = resp.json()
            
            if not isinstance(data, dict):
                raise ValueError(f"Expected dict response, got {type(data).__name__}")
                
            if "dense_vectors" not in data or "sparse_vectors" not in data:
                raise ValueError("Response missing required vector fields")
                
            if len(data["dense_vectors"]) != len(texts) or len(data["sparse_vectors"]) != len(texts):
                raise ValueError("Number of vectors returned doesn't match number of input texts")
                
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to embedding service failed: {e}")
            raise
        except (ValueError, KeyError) as e:
            logger.error(f"Invalid response from embedding service: {e}")
            raise

    def _create_collection_schema(self, dense_vector_size: int) -> CollectionSchema:
        """Create a schema for the Milvus collection.
        
        Args:
            dense_vector_size: Dimension of the dense vectors
            
        Returns:
            Configured CollectionSchema
        """
        schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
        
        # Add fields directly to the schema with proper types and constraints
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="user_id", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=4000)
        schema.add_field(field_name="metadata", datatype=DataType.JSON)
        schema.add_field(field_name="dense_vectors", datatype=DataType.FLOAT_VECTOR, dim=dense_vector_size)
        schema.add_field(field_name="sparse_vectors", datatype=DataType.SPARSE_FLOAT_VECTOR)
            
        return schema
    
    def _create_indexes(self, collection_name: str) -> None:
        """Create necessary indexes for the collection.
        
        Args:
            collection_name: Name of the collection to create indexes for
        """
        # Dense vector index
        dense_index = self.milvus_client.prepare_index_params()
        dense_index.add_index(
            field_name="dense_vectors",
            index_type="HNSW",
            metric_type="COSINE",
            params=self.HNSW_INDEX_PARAMS
        )
        
        # Sparse vector index
        sparse_index = self.milvus_client.prepare_index_params()
        sparse_index.add_index(
            field_name="sparse_vectors",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP"
        )
        
        # Scalar index for user filtering
        user_index = self.milvus_client.prepare_index_params()
        user_index.add_index(
            field_name="user_id",
            index_type="INVERTED"
        )
        
        # Create all indexes
        self.milvus_client.create_index(collection_name, dense_index)
        self.milvus_client.create_index(collection_name, sparse_index)
        self.milvus_client.create_index(collection_name, user_index)
    
    def create_collection(self, collection_name: str, dense_vector_size: int = None) -> None:
        """Create or verify a Milvus collection with proper indexes.
        
        Args:
            collection_name: Name of the collection to create or verify
            dense_vector_size: Dimension of the dense vectors (default: DEFAULT_VECTOR_DIM)
            
        Raises:
            ValueError: If collection name is invalid or vector size is invalid
            RuntimeError: If collection creation fails
        """
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("Collection name must be a non-empty string")
            
        dense_vector_size = dense_vector_size or self.DEFAULT_VECTOR_DIM
        
        try:
            if not self.milvus_client.has_collection(collection_name):
                logger.info(f"Creating new collection: {collection_name}")
                
                # Create schema and collection
                schema = self._create_collection_schema(dense_vector_size)
                self.milvus_client.create_collection(
                    collection_name=collection_name,
                    schema=schema
                )
                
                # Create indexes
                self._create_indexes(collection_name)
                logger.info(f"Created collection and indexes for: {collection_name}")
            
            # Ensure collection is loaded
            self.milvus_client.load_collection(collection_name)
            
        except Exception as e:
            error_msg = f"Failed to create/load collection {collection_name}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

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

    def _process_documents(self, pdf_paths: List[str]) -> List[Document]:
        """Load and process PDF documents.
        
        Args:
            pdf_paths: List of paths to PDF files
            
        Returns:
            List of processed documents with metadata
        """
        documents = []
        
        for path in pdf_paths:
            try:
                if not os.path.exists(path):
                    logger.warning(f"File not found: {path}")
                    continue
                    
                loader = PyPDFLoader(path)
                docs = loader.load()
                
                # Add file metadata to each document
                for doc in docs:
                    doc.metadata.update({
                        "source": path,
                        "filename": os.path.basename(path),
                        "file_type": "pdf"
                    })
                    
                documents.extend(docs)
                
            except Exception as e:
                logger.error(f"Error processing {path}: {e}")
                continue
                
        return documents
        
    def _split_documents(self, documents: List[Document], chunk_size: int, chunk_overlap: int) -> List[Document]:
        """Split documents into chunks.
        
        Args:
            documents: List of documents to split
            chunk_size: Size of each chunk in characters
            chunk_overlap: Overlap between chunks in characters
            
        Returns:
            List of split documents
        """
        if not documents:
            return []
            
        splitter = CharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator="\n"
        )
        
        return splitter.split_documents(documents)
        
    def _prepare_documents_for_indexing(
        self, 
        documents: List[Document], 
        user_id: str
    ) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
        """Prepare documents for indexing by extracting text and metadata.
        
        Args:
            documents: List of documents to prepare
            user_id: User ID to associate with the documents
            
        Returns:
            Tuple of (entities, texts, metadatas)
        """
        if not documents:
            return [], [], []
            
        texts = [d.page_content for d in documents]
        metadatas = []
        
        # Get vectors for all texts in batch
        vecs = self.get_vectors(texts)
        dense_embeddings = vecs["dense_vectors"]
        sparse_embeddings = vecs["sparse_vectors"]
        
        # Prepare entities for batch insertion
        entities = []
        
        for i, (text, dense_vec, sparse_raw) in enumerate(zip(texts, dense_embeddings, sparse_embeddings)):
            # Convert sparse vector to CSR format
            indices = sparse_raw['indices']
            values = sparse_raw['values']
            sparse_vec = sp.csr_matrix(
                (values, ([0] * len(indices), indices)),
                shape=(1, self.sparse_vector_dim)
            )
            
            # Prepare metadata
            metadata = documents[i].metadata.copy()
            metadata["user_id"] = user_id
            
            entities.append({
                "user_id": user_id,
                "text": text,
                "metadata": metadata,
                "dense_vectors": dense_vec,
                "sparse_vectors": sparse_vec
            })
            
            metadatas.append(metadata)
            
        return entities, texts, metadatas
        
    def index_pdfs(
        self,
        pdf_paths: List[str],
        collection_name: str,
        user_id: str,
        chunk_size: int = None,
        chunk_overlap: int = None,
        dense_vector_size: int = None,
    ) -> Dict[str, Any]:
        """Index PDF documents into the Milvus collection.
        
        Args:
            pdf_paths: List of file paths to PDF documents
            collection_name: Name of the collection to index into
            user_id: ID of the user who owns these documents
            chunk_size: Size of text chunks (default: DEFAULT_CHUNK_SIZE)
            chunk_overlap: Overlap between chunks (default: DEFAULT_CHUNK_OVERLAP)
            dense_vector_size: Dimension of dense vectors (default: DEFAULT_VECTOR_DIM)
            
        Returns:
            Dictionary with indexing statistics
            
        Raises:
            ValueError: If no valid documents are found
            RuntimeError: If indexing fails
        """
        if not pdf_paths:
            raise ValueError("No PDF paths provided")
            
        chunk_size = chunk_size or self.DEFAULT_CHUNK_SIZE
        chunk_overlap = chunk_overlap or self.DEFAULT_CHUNK_OVERLAP
        dense_vector_size = dense_vector_size or self.DEFAULT_VECTOR_DIM
        
        try:
            # 1. Load and process documents
            logger.info(f"Processing {len(pdf_paths)} PDF files")
            documents = self._process_documents(pdf_paths)
            if not documents:
                raise ValueError("No valid documents found to process")
            
            # 2. Split documents into chunks
            logger.info(f"Splitting {len(documents)} documents into chunks")
            split_docs = self._split_documents(documents, chunk_size, chunk_overlap)
            
            # 3. Prepare documents for indexing (get vectors, format for Milvus)
            logger.info(f"Preparing {len(split_docs)} chunks for indexing")
            entities, texts, metadatas = self._prepare_documents_for_indexing(split_docs, user_id)
            
            # 4. Create or get collection
            self.create_collection(collection_name, dense_vector_size=dense_vector_size)
            
            # 5. Insert data into Milvus in batches
            if entities:
                self.milvus_client.insert(collection_name, entities)
                logger.info(f"Inserted {len(entities)} vectors into collection '{collection_name}'")
            
            return {
                "collection": collection_name,
                "user_id": user_id,
                "chunks_indexed": len(entities),
                "points_upserted": len(entities),
                "documents_processed": len(documents)
            }
            
        except Exception as e:
            error_msg = f"Failed to index PDFs: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

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

    def rag(self, query: str, collection_name: str, user_id: str, limit: int = 5) -> Dict[str, Any]:
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


