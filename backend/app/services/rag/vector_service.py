import os
import logging
import requests
import scipy.sparse as sp
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class VectorService:
    """處理向量相關操作的服務類"""
    
    def __init__(self, embedding_url: Optional[str] = None):
        """初始化向量服務
        
        Args:
            embedding_url: 嵌入服務的 URL
        """
        self.embedding_url = (embedding_url or os.getenv("EMBEDDING_API_BASE")).rstrip('/')
        self.sparse_vector_dim = 262144  # 預設稀疏向量維度
    
    def get_vectors(self, texts: List[str]) -> Dict[str, Any]:
        """從嵌入服務獲取文本的密集和稀疏向量
        
        Args:
            texts: 要編碼的文本字符串列表
            
        Returns:
            包含 'dense_vectors' 和 'sparse_vectors' 的字典
            
        Raises:
            HTTPError: 當請求嵌入服務失敗時
            ValueError: 當響應格式不正確時
        """
        if not texts:
            raise ValueError("沒有提供要向量化的文本")
            
        url = f"{self.embedding_url}/hybrid-embed"
        logger.debug(f"從 {url} 請求 {len(texts)} 個文本的向量")
        
        try:
            resp = requests.post(
                url,
                json={"texts": texts},
                timeout=120
            )
            resp.raise_for_status()
            data = resp.json()
            
            if not isinstance(data, dict):
                raise ValueError(f"期望返回字典，但得到 {type(data).__name__}")
                
            if "dense_vectors" not in data or "sparse_vectors" not in data:
                raise ValueError("響應缺少必要的向量字段")
                
            if len(data["dense_vectors"]) != len(texts) or len(data["sparse_vectors"]) != len(texts):
                raise ValueError("返回的向量數量與輸入文本數量不匹配")
                
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"請求嵌入服務失敗: {e}")
            raise
        except (ValueError, KeyError) as e:
            logger.error(f"從嵌入服務收到無效響應: {e}")
            raise
    
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
