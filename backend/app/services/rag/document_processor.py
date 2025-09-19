import os
import logging
from typing import List, Dict, Any, Tuple

from langchain.schema.document import Document
from unstructured.partition.pdf import partition_pdf
from unstructured.chunking.title import chunk_by_title

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """
    處理文檔加載和語義分塊的服務類。
    使用 unstructured 庫的高級功能來確保表格等結構的完整性。
    """
    
    def __init__(self, chunk_size: int = 4000, chunk_overlap: int = 500):
        """
        初始化文檔處理器。
        注意：chunk_size 和 chunk_overlap 在此處主要作為 chunk_by_title 的參數參考。
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
    def process_and_chunk_pdfs(self, pdf_paths: List[str]) -> List[Document]:
        """
        加載、解析並按語義分塊 PDF 文檔。
        這個方法取代了舊的 process_documents 和 split_documents。
        """
        all_docs = []
        for path in pdf_paths:
            if not os.path.exists(path):
                logger.warning(f"文件不存在: {path}")
                continue
            
            try:
                logger.info(f"開始使用 hi_res 策略處理: {path}")
                # 1. 使用高精度策略解析 PDF，並推斷表格結構
                elements = partition_pdf(
                    filename=path,
                    strategy="hi_res",
                    extract_image_block_types=["Table"]
                )
                
                # 2. 使用按標題分塊的策略，這對技術手冊等結構化文檔非常有效
                chunks = chunk_by_title(
                    elements,
                    max_characters=self.chunk_size,
                    new_after_n_chars=self.chunk_size - self.chunk_overlap,
                    combine_text_under_n_chars=self.chunk_overlap
                )
                
                logger.info(f"文件 {path} 被分割成 {len(chunks)} 個語義塊。")
                
                # 3. 將 unstructured 的塊轉換為 LangChain 的 Document 格式
                for chunk in chunks:
                    # 使用純文本內容，以優化向量搜索的相似度
                    text = chunk.text.strip()

                    new_doc = Document(
                        page_content=text,
                        metadata={
                            "source": path,
                            "filename": os.path.basename(path),
                            "file_type": "pdf",
                            **chunk.metadata.to_dict()
                        }
                    )
                    all_docs.append(new_doc)
                    
            except Exception as e:
                logger.error(f"處理 {path} 時出錯: {e}", exc_info=True)
                continue
                
        return all_docs

    def prepare_for_indexing(
        self, 
        documents: List[Document], 
        user_id: str,
        vector_service: Any,
        file_id: str = None
    ) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
        """
        準備文檔以進行索引 (此方法保持不變)。
        """
        if not documents:
            return [], [], []
            
        texts = [d.page_content for d in documents]
        metadatas = []
        
        # 獲取所有文本的向量
        vecs = vector_service.get_vectors(texts)
        
        # 準備批量插入的實體
        entities = []
        
        for i, (text, dense_vec, sparse_raw) in enumerate(zip(
            texts, 
            vecs["dense_vectors"], 
            vecs["sparse_vectors"]
        )):
            # 準備元數據
            metadata = documents[i].metadata.copy()
            metadata["user_id"] = user_id
            if file_id:
                metadata["file_id"] = file_id
            
            # 創建稀疏向量
            sparse_vec = vector_service.create_sparse_vector(
                sparse_raw['indices'],
                sparse_raw['values']
            )
            
            entities.append({
                "user_id": user_id,
                "text": text,
                "metadata": metadata,
                "dense_vectors": dense_vec,
                "sparse_vectors": sparse_vec
            })
            
            metadatas.append(metadata)
            
        return entities, texts, metadatas
