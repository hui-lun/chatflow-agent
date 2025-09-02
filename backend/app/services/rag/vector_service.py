import os
import logging
import requests
import scipy.sparse as sp
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class VectorService:
    """處理向量相關操作的服務類"""
    
    def __init__(self, embedding_url: Optional[str] = None, batch_size: int = 32):
        """初始化向量服務
        
        Args:
            embedding_url: 嵌入服務的 URL
            batch_size: 請求嵌入服務時的批次大小
        """
        self.embedding_url = (embedding_url or os.getenv("EMBEDDING_API_BASE")).rstrip('/')
        self.sparse_vector_dim = 262144  # 預設稀疏向量維度
        self.batch_size = batch_size
    
    def get_vectors(self, texts: List[str], batch_size: Optional[int] = None) -> Dict[str, Any]:
        """從嵌入服務獲取文本的密集和稀疏向量，並使用批次處理
        
        Args:
            texts: 要編碼的文本字符串列表
            batch_size: 可選，覆蓋默認的批次大小
            
        Returns:
            包含 'dense_vectors' 和 'sparse_vectors' 的字典
            
        Raises:
            HTTPError: 當請求嵌入服務失敗時
            ValueError: 當響應格式不正確時
        """
        if not texts:
            raise ValueError("沒有提供要向量化的文本")

        effective_batch_size = batch_size or self.batch_size    
        url = f"{self.embedding_url}/hybrid-embed"
        logger.info(f"開始從 {url} 請求 {len(texts)} 個文本的向量，批次大小為 {effective_batch_size}")
        
        all_dense_vectors = []
        all_sparse_vectors = []

        for i in range(0, len(texts), effective_batch_size):
            batch_texts = texts[i:i + effective_batch_size]
            num_batches = (len(texts) + effective_batch_size - 1) // effective_batch_size
            logger.debug(f"正在處理批次 {i // effective_batch_size + 1}/{num_batches}，包含 {len(batch_texts)} 個文本")

            try:
                resp = requests.post(
                    url,
                    json={"texts": batch_texts},
                    timeout=120
                )
                resp.raise_for_status()
                data = resp.json()

                if not isinstance(data, dict) or "dense_vectors" not in data or "sparse_vectors" not in data:
                    raise ValueError("批次響應缺少必要的向量字段")
                
                if len(data["dense_vectors"]) != len(batch_texts) or len(data["sparse_vectors"]) != len(batch_texts):
                    raise ValueError("批次返回的向量數量與輸入文本數量不匹配")

                all_dense_vectors.extend(data["dense_vectors"])
                all_sparse_vectors.extend(data["sparse_vectors"])

            except requests.exceptions.RequestException as e:
                logger.error(f"請求嵌入服務批次時失敗: {e}")
                raise
            except (ValueError, KeyError) as e:
                logger.error(f"從嵌入服務收到無效的批次響應: {e}")
                raise
        
        logger.info(f"成功獲取所有 {len(all_dense_vectors) + len(all_sparse_vectors)} 個向量")
        
        if len(all_dense_vectors) != len(texts):
             raise ValueError(f"最終向量數量 ({len(all_dense_vectors)}) 與輸入文本總數 ({len(texts)}) 不匹配")

        return {
            "dense_vectors": all_dense_vectors,
            "sparse_vectors": all_sparse_vectors
        }
    
    def create_sparse_vector(self, indices: List[int], values: List[float]) -> sp.csr_matrix:
        """創建稀疏向量
        
        Args:
            indices: 非零元素的索引列表
            values: 對應索引的值列表
            
        Returns:
            壓縮稀疏行矩陣格式的稀疏向量
        """
        return sp.csr_matrix(
            (values, ([0] * len(indices), indices)),
            shape=(1, self.sparse_vector_dim)
        )
    
    def prepare_query_vectors(self, query: str) -> Dict[str, Any]:
        """準備查詢向量
        
        Args:
            query: 查詢文本
            
        Returns:
            包含密集和稀疏向量的字典
        """
        data = self.get_vectors([query])
        
        if not data or 'dense_vectors' not in data or 'sparse_vectors' not in data:
            raise ValueError("無法生成查詢向量")
        
        dense_vector = data['dense_vectors'][0]
        sparse_raw = data['sparse_vectors'][0]
        
        # 轉換稀疏向量格式
        sparse_vector = self.create_sparse_vector(
            sparse_raw['indices'], 
            sparse_raw['values']
        )
        
        return {
            'dense_vector': dense_vector,
            'sparse_vector': sparse_vector
        }