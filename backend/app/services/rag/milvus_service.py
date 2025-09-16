import logging
import concurrent.futures
from typing import Dict, List, Any, Optional

from pymilvus import MilvusClient, DataType, CollectionSchema, Collection
import scipy.sparse as sp

logger = logging.getLogger(__name__)

class MilvusService:
    """處理 Milvus 數據庫操作的服務類"""
    
    # Milvus 索引參數
    HNSW_INDEX_PARAMS = {"M": 16, "efConstruction": 256}
    # 定義新的 Schema 版本和文本最大長度
    SCHEMA_VERSION = "v2"
    TEXT_MAX_LENGTH = 32768

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
        schema = MilvusClient.create_schema(
            auto_id=True, 
            enable_dynamic_field=False,
            description=f"Schema {self.SCHEMA_VERSION}" # 添加版本描述
        )
        
        # 添加字段到 schema
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="user_id", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=self.TEXT_MAX_LENGTH) # 使用新的最大長度
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
        """
        創建或驗證/升級 Milvus 集合。
        如果集合存在但 schema 過期，會自動刪除並重建。
        """
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("集合名稱必須是非空字符串")
            
        try:
            needs_recreation = False
            if self.milvus_client.has_collection(collection_name):
                logger.info(f"集合 {collection_name} 已存在，正在檢查 schema 版本。")
                collection_info = self.milvus_client.describe_collection(collection_name)
                
                # 檢查 schema 版本是否匹配
                current_description = collection_info.get("description", "")
                if self.SCHEMA_VERSION not in current_description:
                    logger.warning(
                        f"Schema 版本不匹配 (需要: {self.SCHEMA_VERSION}, 現有: {current_description})。"
                        f"將刪除並重建集合 {collection_name}。"
                    )
                    needs_recreation = True
                    self.milvus_client.drop_collection(collection_name)
            
            if needs_recreation or not self.milvus_client.has_collection(collection_name):
                logger.info(f"創建新集合: {collection_name} (Schema: {self.SCHEMA_VERSION})" )
                
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
        limit: int = 30,
        rerank_k: int = 60,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        通過並行發送密集和稀疏向量的搜索請求來執行混合搜索，並在客戶端使用 RRF 進行重新排序。
        支持基於 user_id 和可選的 metadata 進行過濾。
        """
        # 基礎過濾條件：必須匹配 user_id
        filter_conditions = [f'user_id == "{user_id}"']

        # 動態添加 metadata 過濾條件
        if metadata_filter:
            for key, value in metadata_filter.items():
                if isinstance(value, str):
                    filter_conditions.append(f'metadata["{key}"] == "{value}"')
                else:
                    filter_conditions.append(f'metadata["{key}"] == {value}')
        
        # 將所有條件用 "&&" 連接起來
        final_filter = " && ".join(filter_conditions)
        logger.info(f"Executing hybrid search with filter: {final_filter}")

        candidate_limit = max(limit * 4, 20)

        def search_dense():
            """執行密集向量搜索"""
            try:
                return self.milvus_client.search(
                    collection_name=collection_name,
                    data=[dense_vector],
                    filter=final_filter,
                    limit=candidate_limit,
                    anns_field="dense_vectors",
                    output_fields=["text", "metadata", "user_id"]
                )[0]
            except Exception as e:
                logger.error(f"並行密集搜索失敗: {e}")
                return []

        def search_sparse():
            """執行稀疏向量搜索"""
            try:
                return self.milvus_client.search(
                    collection_name=collection_name,
                    data=sparse_vector,
                    filter=final_filter,
                    limit=candidate_limit,
                    anns_field="sparse_vectors",
                    output_fields=["text", "metadata", "user_id"]
                )[0]
            except Exception as e:
                logger.error(f"並行稀疏搜索失敗: {e}")
                return []

        # 使用線程池並行執行兩個搜索任務
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_dense = executor.submit(search_dense)
            future_sparse = executor.submit(search_sparse)
            
            dense_results = future_dense.result()
            sparse_results = future_sparse.result()

        # 在客戶端執行 RRF 重新排序
        results_list = [dense_results, sparse_results]
        
        ranked_lists = []
        for res in results_list:
            if not res: continue
            ranked_lists.append({hit['id']: rank + 1 for rank, hit in enumerate(res)})

        rrf_scores = {}
        all_doc_ids = set()
        for rlist in ranked_lists:
            all_doc_ids.update(rlist.keys())

        for doc_id in all_doc_ids:
            score = 0.0
            for rlist in ranked_lists:
                if doc_id in rlist:
                    score += 1.0 / (rerank_k + rlist[doc_id])
            rrf_scores[doc_id] = score

        sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda id: rrf_scores[id], reverse=True)
        
        all_hits_map = {}
        for res in results_list:
            if not res: continue
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

    def delete_by_file_id(self, collection_name: str, file_id: str, user_id: str) -> int:
        """根據文件 ID 刪除 Milvus 中的所有相關向量數據
        
        Args:
            collection_name: 集合名稱
            file_id: 要刪除的文件 ID
            user_id: 用戶 ID 用於過濾
            
        Returns:
            刪除的向量數量
            
        Raises:
            RuntimeError: 當刪除操作失敗時
        """
        if not collection_name or not file_id or not user_id:
            raise ValueError("集合名稱、文件 ID 和用戶 ID 都不能為空")
        
        try:
            # 檢查集合是否存在
            if not self.has_collection(collection_name):
                logger.warning(f"集合 {collection_name} 不存在，跳過刪除操作")
                return 0
            
            # 構建過濾條件：根據 metadata 中的 file_id 和 user_id 進行過濾
            filter_expr = f'user_id == "{user_id}" && metadata["file_id"] == "{file_id}"'
            logger.info(f"使用過濾條件: {filter_expr}")
            
            # 先查詢匹配的記錄數量
            try:
                query_result = self.milvus_client.query(
                    collection_name=collection_name,
                    filter=filter_expr,
                    output_fields=["id", "metadata"],
                    limit=10
                )
                logger.info(f"找到 {len(query_result)} 個匹配的記錄")
                if query_result:
                    logger.debug(f"第一個匹配記錄的 metadata: {query_result[0].get('metadata', {})}")
            except Exception as e:
                logger.warning(f"查詢匹配記錄時出錯: {e}")
            
            # 執行刪除操作
            delete_result = self.milvus_client.delete(
                collection_name=collection_name,
                filter=filter_expr
            )
            
            # 刷新集合以確保刪除操作生效
            self.milvus_client.flush(collection_name=collection_name)
            
            deleted_count = delete_result.get('delete_count', 0)
            logger.info(f"從 {collection_name} 集合中刪除了 {deleted_count} 個向量 (file_id: {file_id}, user_id: {user_id})")
            
            return deleted_count
            
        except Exception as e:
            error_msg = f"從 {collection_name} 刪除文件 {file_id} 的向量數據失敗: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e