import os
import logging
from typing import List, Dict, Any, Optional

from .models import RAGResponse, SearchResult
from .vector_service import VectorService
from .milvus_service import MilvusService
from .document_processor import DocumentProcessor
from app.services.llm import get_llm

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
    DEFAULT_SEARCH_LIMIT = 5
    
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
        self.vector_service = VectorService(embedding_url)
        self.milvus_service = MilvusService(milvus_uri)
        self.document_processor = DocumentProcessor(
            chunk_size=self.DEFAULT_CHUNK_SIZE,
            chunk_overlap=self.DEFAULT_CHUNK_OVERLAP
        )

    def create_collection(self, collection_name: str, dense_vector_size: int = None) -> None:
        """創建或驗證 Milvus 集合
        
        Args:
            collection_name: 要創建或驗證的集合名稱
            dense_vector_size: 密集向量的維度 (預設: DEFAULT_VECTOR_DIM)
            
        Raises:
            ValueError: 當集合名稱無效或向量大小無效時
            RuntimeError: 當集合創建失敗時
        """
        self.milvus_service.create_collection(
            collection_name,
            dense_vector_size or self.DEFAULT_VECTOR_DIM
        )
        
    def index_pdfs(
        self,
        pdf_paths: List[str],
        collection_name: str,
        user_id: str,
        chunk_size: int = None,
        chunk_overlap: int = None,
        dense_vector_size: int = None,
    ) -> Dict[str, Any]:
        """將 PDF 文檔索引到 Milvus 集合中
        
        Args:
            pdf_paths: PDF 文件路徑列表
            collection_name: 目標集合名稱
            user_id: 文檔所屬用戶的 ID
            chunk_size: 文本塊大小 (預設: DEFAULT_CHUNK_SIZE)
            chunk_overlap: 塊之間的重疊字符數 (預設: DEFAULT_CHUNK_OVERLAP)
            dense_vector_size: 密集向量的維度 (預設: DEFAULT_VECTOR_DIM)
            
        Returns:
            包含索引統計信息的字典
            
        Raises:
            ValueError: 當沒有找到有效文檔時
            RuntimeError: 當索引過程失敗時
        """
        if not pdf_paths:
            raise ValueError("未提供 PDF 文件路徑")
            
        # 更新文檔處理器的配置
        self.document_processor.chunk_size = chunk_size or self.DEFAULT_CHUNK_SIZE
        self.document_processor.chunk_overlap = chunk_overlap or self.DEFAULT_CHUNK_OVERLAP
        dense_vector_size = dense_vector_size or self.DEFAULT_VECTOR_DIM
        
        try:
            # 1. 加載並處理文檔
            logger.info(f"正在處理 {len(pdf_paths)} 個 PDF 文件")
            documents = self.document_processor.process_documents(pdf_paths)
            if not documents:
                raise ValueError("未找到有效文檔進行處理")
            
            # 2. 分割文檔為塊
            logger.info(f"將 {len(documents)} 個文檔分割成塊")
            split_docs = self.document_processor.split_documents(documents)
            
            # 3. 準備文檔以進行索引（獲取向量，格式化為 Milvus 格式）
            logger.info(f"準備 {len(split_docs)} 個塊進行索引")
            entities, texts, metadatas = self.document_processor.prepare_for_indexing(
                split_docs, 
                user_id,
                self.vector_service
            )
            
            # 4. 創建或獲取集合
            self.create_collection(collection_name, dense_vector_size)
            
            # 5. 批量插入數據到 Milvus
            if entities:
                points_upserted = self.milvus_service.insert_documents(collection_name, entities)
                logger.info(f"已將 {points_upserted} 個向量插入到集合 '{collection_name}'")
            
            return {
                "collection": collection_name,
                "user_id": user_id,
                "chunks_indexed": len(entities),
                "points_upserted": points_upserted,
                "documents_processed": len(documents)
            }
            
        except Exception as e:
            error_msg = f"PDF 索引失敗: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def search(self, query: str, collection_name: str, user_id: str, limit: int = 5, score_threshold: float = 0.0) -> List[SearchResult]:
        """使用混合搜索（密集+稀疏向量）和 RRF 重新排序搜索相似文檔
        
        Args:
            query: 查詢文本
            collection_name: 集合名稱
            user_id: 用戶 ID 用於過濾
            limit: 返回的最大結果數
            score_threshold: 分數閾值 (未使用，保持向後兼容)
            
        Returns:
            搜索結果列表，按相關性排序
        """
        try:
            # 獲取查詢向量
            vectors = self.vector_service.prepare_query_vectors(query)
            
            # 執行混合搜索
            results = self.milvus_service.hybrid_search(
                collection_name=collection_name,
                dense_vector=vectors['dense_vector'],
                sparse_vector=vectors['sparse_vector'],
                user_id=user_id,
                limit=limit
            )
            
            # 過濾低分結果
            if score_threshold > 0:
                results = [r for r in results if r['score'] >= score_threshold]
            
            return results
            
        except Exception as e:
            logger.error(f"搜索失敗: {e}")
            raise

    def generate(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """使用語言模型生成回應
        
        Args:
            query: 用戶查詢
            context_chunks: 相關文檔塊列表
            
        Returns:
            生成的回應文本
        """
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
            logger.error(f"LLM 生成失敗: {e}")
            # 返回後備回應
            return "（提示：目前無法連線至文字生成服務，僅返回檢索到的內容摘要。）\n\n" + context[:800]

    def has_collection(self, collection_name: str) -> bool:
        """檢查集合是否存在
        
        Args:
            collection_name: 要檢查的集合名稱
            
        Returns:
            bool: 如果集合存在返回 True，否則返回 False
        """
        return self.milvus_service.has_collection(collection_name)
        
    def rag(self, query: str, collection_name: str, user_id: str, limit: int = 5) -> RAGResponse:
        """完整的 RAG 流程：檢索並生成
        
        Args:
            query: 用戶查詢
            collection_name: 集合名稱
            user_id: 用戶 ID 用於過濾
            limit: 返回的最大結果數
            
        Returns:
            包含生成回應和檢索到的文檔的字典
        """
        try:
            # 1. 檢索相關文檔
            retrieved = self.search(query, collection_name, user_id, limit=limit)
        except Exception as e:
            logger.error(f"混合搜索失敗: {e}")
            return {"response": f"檢索發生錯誤：{e}", "retrieved_docs": []}

        if not retrieved:
            return {"response": "抱歉，沒有找到相關的文檔。", "retrieved_docs": []}

        # 2. 生成回應（失敗時有後備方案）
        answer = self.generate(query, retrieved)
        return {"response": answer, "retrieved_docs": retrieved}
