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
    DEFAULT_VECTOR_DIM = 1024
    
    @staticmethod
    def get_user_collection_name(username: str) -> str:
        """根據使用者名稱生成專屬的 collection 名稱"""
        if not username:
            raise ValueError("使用者名稱不能為空")
        return f"kb_{username}"
    
    def __init__(
        self,
        embedding_url: Optional[str] = None,
        milvus_uri: Optional[str] = None,
    ) -> None:
        """Initialize the RAG service."""
        self.vector_service = VectorService(embedding_url)
        self.milvus_service = MilvusService(milvus_uri)
        self.document_processor = DocumentProcessor()

    def create_collection(self, collection_name: str, dense_vector_size: int = None) -> None:
        """創建或驗證 Milvus 集合"""
        self.milvus_service.create_collection(
            collection_name,
            dense_vector_size or self.DEFAULT_VECTOR_DIM
        )
        
    def index_pdfs(
        self,
        pdf_paths: List[str],
        collection_name: str,
        user_id: str,
        dense_vector_size: int = None,
        file_id: str = None
    ) -> Dict[str, Any]:
        """使用語義分塊策略將 PDF 文檔索引到 Milvus 集合中。"""
        if not pdf_paths:
            raise ValueError("未提供 PDF 文件路徑")
            
        self.create_collection(collection_name, dense_vector_size)
        
        all_chunks = self.document_processor.process_and_chunk_pdfs(pdf_paths)
        if not all_chunks:
            raise ValueError("沒有從 PDF 中提取到任何有效的文本塊。")

        entities, _, _ = self.document_processor.prepare_for_indexing(
            all_chunks, user_id, self.vector_service, file_id
        )
        
        if not entities:
            raise RuntimeError("未能為文本塊生成有效的嵌入向量。")
        
        points_upserted = self.milvus_service.insert_documents(collection_name, entities)
        
        results = {
            "collection": collection_name,
            "user_id": user_id,
            "documents_processed": len(pdf_paths),
            "chunks_indexed": len(entities),
            "points_upserted": points_upserted,
            "files": [os.path.basename(p) for p in pdf_paths]
        }
        
        logger.info(f"索引完成: {results}")
        return results

    def search(self, query: str, collection_name: str, user_id: str, limit: int = 20, score_threshold: float = 0.0, metadata_filter: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
        """使用混合搜索（密集+稀疏向量）和 RRF 重新排序搜索相似文檔"""
        try:
            vectors = self.vector_service.prepare_query_vectors(query)
            logger.info('='*60)
            logger.info(f'test: {metadata_filter}')
            logger.info('='*60)
            results = self.milvus_service.hybrid_search(
                collection_name=collection_name,
                dense_vector=vectors['dense_vector'],
                sparse_vector=vectors['sparse_vector'],
                user_id=user_id,
                limit=limit,
                metadata_filter=metadata_filter
            )
            
            if score_threshold > 0.0:
                results = [r for r in results if r['score'] >= score_threshold]
            
            return results
            
        except Exception as e:
            logger.error(f"搜索失敗: {e}", exc_info=True)
            raise

    def generate(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """使用語言模型生成回應"""
        context = "\n---\n".join(c["text"] for c in context_chunks)
        prompt = (
            "基於以下上下文，請詳細並準確地回答用戶的問題。請整合所有相關資訊，不要遺漏細節。\n\n"
            f"上下文：\n{context}\n\n用戶問題：{query}\n\n回答："
        )

        try:
            llm = get_llm()
            result = llm.invoke(prompt)
            return result.content if hasattr(result, "content") else str(result)
        except Exception as e:
            logger.error(f"LLM 生成失敗: {e}")
            return "（提示：目前無法連線至文字生成服務，僅返回檢索到的內容摘要。）\n\n" + context[:800]

    def has_collection(self, collection_name: str) -> bool:
        """檢查集合是否存在"""
        return self.milvus_service.has_collection(collection_name)
        
    def rag(self, query: str, collection_name: str, user_id: str, limit: int = 20, metadata_filter: Optional[Dict[str, Any]] = None) -> RAGResponse:
        """完整的 RAG 流程：檢索並生成。"""
        try:
            retrieved = self.search(query, collection_name, user_id, limit=limit, metadata_filter=metadata_filter)
        except Exception as e:
            logger.error(f"搜索失敗: {e}", exc_info=True)
            return {"response": f"檢索發生錯誤：{e}", "retrieved_docs": []}

        if not retrieved:
            return {"response": "抱歉，沒有找到相關的文檔。", "retrieved_docs": []}

        answer = self.generate(query, retrieved)
        return {"response": answer, "retrieved_docs": retrieved}