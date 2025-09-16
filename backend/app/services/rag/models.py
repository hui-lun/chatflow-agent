from typing import Dict, Any, List, Optional, TypedDict, Union
from pydantic import BaseModel
from langchain.schema.document import Document

class SearchResult(TypedDict):
    """搜索結果類型定義"""
    text: str
    metadata: Dict[str, Any]
    score: float

class RAGResponse(TypedDict):
    """RAG 響應類型定義"""
    response: str
    retrieved_docs: List[SearchResult]

class DocumentChunk(BaseModel):
    """文檔分塊模型"""
    text: str
    metadata: Dict[str, Any]
    dense_vector: List[float]
    sparse_vector: Dict[str, float]  # 稀疏向量表示為 {index: value} 的字典

class IndexingResult(BaseModel):
    """索引結果模型"""
    collection: str
    user_id: str
    chunks_indexed: int
    points_upserted: int
    documents_processed: int

class SearchRequest(BaseModel):
    """搜索請求模型"""
    query: str
    collection_name: str
    user_id: str
    limit: int = 5
    score_threshold: float = 0.0
    metadata_filter: Optional[Dict[str, Any]] = None # 新增元數據過濾條件


class IndexingRequest(BaseModel):
    """索引請求模型"""
    pdf_paths: List[str]
    collection_name: str
    user_id: str
    chunk_size: int = 1000
    chunk_overlap: int = 200
    dense_vector_size: int = 1024