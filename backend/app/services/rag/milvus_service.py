import logging
from typing import Dict, List, Any, Optional, Tuple

from pymilvus import MilvusClient, DataType, CollectionSchema
import scipy.sparse as sp

logger = logging.getLogger(__name__)

class MilvusService:
    """處理 Milvus 數據庫操作的服務類"""
    
    # Milvus 索引參數
    HNSW_INDEX_PARAMS = {"M": 16, "efConstruction": 256}
    
    def __init__(self, milvus_uri: Optional[str] = None):
        """初始化 Milvus 服務
        
        Args:
            milvus_uri: Milvus 服務器 URI
        """
        self.milvus_uri = milvus_uri or "http://milvus-standalone:19530"
        self.milvus_client = MilvusClient(uri=self.milvus_uri)
    
    def _create_collection_schema(self, dense_vector_size: int) -> CollectionSchema:
        """創建 Milvus 集合的 schema
        
        Args:
            dense_vector_size: 密集向量的維度
            
        Returns:
            配置好的 CollectionSchema 對象
        """
        schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
        
        # 添加字段到 schema
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="user_id", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=4000)
        schema.add_field(field_name="metadata", datatype=DataType.JSON)
        schema.add_field(
            field_name="dense_vectors", 
            datatype=DataType.FLOAT_VECTOR, 
            dim=dense_vector_size
        )
        schema.add_field(
            field_name="sparse_vectors", 
            datatype=DataType.SPARSE_FLOAT_VECTOR
        )
            
        return schema
    
    def _create_indexes(self, collection_name: str) -> None:
        """為集合創建必要的索引
        
        Args:
            collection_name: 要創建索引的集合名稱
        """
        # 密集向量索引
        dense_index = self.milvus_client.prepare_index_params()
        dense_index.add_index(
            field_name="dense_vectors",
            index_type="HNSW",
            metric_type="COSINE",
            params=self.HNSW_INDEX_PARAMS
        )
        
        # 稀疏向量索引
        sparse_index = self.milvus_client.prepare_index_params()
        sparse_index.add_index(
            field_name="sparse_vectors",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP"
        )
        
        # 用戶過濾的標量索引
        user_index = self.milvus_client.prepare_index_params()
        user_index.add_index(
            field_name="user_id",
            index_type="INVERTED"
        )
        
        # 創建所有索引
        self.milvus_client.create_index(collection_name, dense_index)
        self.milvus_client.create_index(collection_name, sparse_index)
        self.milvus_client.create_index(collection_name, user_index)
    
    def has_collection(self, collection_name: str) -> bool:
        """檢查集合是否存在
        
        Args:
            collection_name: 要檢查的集合名稱
            
        Returns:
            bool: 如果集合存在返回 True，否則返回 False
        """
        return self.milvus_client.has_collection(collection_name)
        
    def create_collection(self, collection_name: str, dense_vector_size: int = 768) -> None:
        """創建或驗證 Milvus 集合
        
        Args:
            collection_name: 要創建或驗證的集合名稱
            dense_vector_size: 密集向量的維度
            
        Raises:
            ValueError: 當集合名稱無效或向量大小無效時
            RuntimeError: 當集合創建失敗時
        """
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("集合名稱必須是非空字符串")
            
        try:
            if not self.milvus_client.has_collection(collection_name):
                logger.info(f"創建新集合: {collection_name}")
                
                # 創建 schema 和集合
                schema = self._create_collection_schema(dense_vector_size)
                self.milvus_client.create_collection(
                    collection_name=collection_name,
                    schema=schema
                )
                
                # 創建索引
                self._create_indexes(collection_name)
                logger.info(f"已為 {collection_name} 創建集合和索引")
            
            # 確保集合已加載
            self.milvus_client.load_collection(collection_name)
            
        except Exception as e:
            error_msg = f"創建/加載集合 {collection_name} 失敗: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def insert_documents(
        self, 
        collection_name: str, 
        entities: List[Dict[str, Any]]
    ) -> int:
        """將文檔插入到集合中
        
        Args:
            collection_name: 目標集合名稱
            entities: 要插入的實體列表
            
        Returns:
            插入的文檔數量
        """
        if not entities:
            return 0
            
        try:
            result = self.milvus_client.insert(collection_name, entities)
            self.milvus_client.flush(collection_name=collection_name)
            return result['insert_count']
        except Exception as e:
            logger.error(f"插入文檔到 {collection_name} 失敗: {e}")
            raise
    
    def hybrid_search(
        self,
        collection_name: str,
        dense_vector: List[float],
        sparse_vector: sp.csr_matrix,
        user_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """執行混合搜索（密集+稀疏向量）
        
        Args:
            collection_name: 集合名稱
            dense_vector: 密集查詢向量
            sparse_vector: 稀疏查詢向量 (CSR 格式)
            user_id: 用戶 ID 用於過濾
            limit: 返回的最大結果數
            
        Returns:
            搜索結果列表，按相關性排序
        """
        user_filter = f'user_id == "{user_id}"'
        
        # 密集向量搜索
        dense_results = self.milvus_client.search(
            collection_name=collection_name,
            data=[dense_vector],
            filter=user_filter,
            limit=limit,
            anns_field="dense_vectors",
            output_fields=["text", "metadata", "user_id"]
        )[0]
        
        # 稀疏向量搜索
        sparse_results = self.milvus_client.search(
            collection_name=collection_name,
            data=sparse_vector,
            filter=user_filter,
            limit=limit,
            anns_field="sparse_vectors",
            output_fields=["text", "metadata", "user_id"]
        )[0]
        
        # 使用 RRF 重新排序結果
        return self._rerank_rrf([dense_results, sparse_results], limit=limit)
    
    def _rerank_rrf(
        self, 
        results_list: List[List[Dict]], 
        k: int = 60,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """使用 Reciprocal Rank Fusion (RRF) 對多個搜索結果進行重新排序
        
        Args:
            results_list: 多個搜索結果的列表
            k: RRF 常數
            limit: 返回的最大結果數
            
        Returns:
            重新排序後的結果列表
        """
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
        for doc_id in sorted_doc_ids[:limit]:
            hit = all_hits_map[doc_id]
            final_results.append({
                "text": hit['entity']['text'],
                "metadata": hit['entity']['metadata'],
                "score": rrf_scores[doc_id]
            })

        return final_results