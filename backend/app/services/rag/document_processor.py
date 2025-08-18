import os
import logging
from typing import List, Dict, Any, Tuple
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain.schema.document import Document
from langchain.text_splitter import CharacterTextSplitter

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """處理文檔加載和預處理的服務類"""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """初始化文檔處理器
        
        Args:
            chunk_size: 文本塊大小（字符數）
            chunk_overlap: 塊之間的重疊字符數
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def process_documents(self, pdf_paths: List[str]) -> List[Document]:
        """加載並處理 PDF 文檔
        
        Args:
            pdf_paths: PDF 文件路徑列表
            
        Returns:
            處理後的文檔列表，包含元數據
        """
        documents = []
        
        for path in pdf_paths:
            try:
                if not os.path.exists(path):
                    logger.warning(f"文件不存在: {path}")
                    continue
                    
                loader = PyPDFLoader(path)
                docs = loader.load()
                
                # 為每個文檔添加文件元數據
                for doc in docs:
                    doc.metadata.update({
                        "source": path,
                        "filename": os.path.basename(path),
                        "file_type": "pdf"
                    })
                    
                documents.extend(docs)
                
            except Exception as e:
                logger.error(f"處理 {path} 時出錯: {e}")
                continue
                
        return documents
    
    def split_documents(self, documents: List[Document]) -> List[Document]:
        """將文檔分割成較小的塊
        
        Args:
            documents: 要分割的文檔列表
            
        Returns:
            分割後的文檔塊列表
        """
        if not documents:
            return []
            
        splitter = CharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separator="\n"
        )
        
        return splitter.split_documents(documents)
    
    def prepare_for_indexing(
        self, 
        documents: List[Document], 
        user_id: str,
        vector_service: Any
    ) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
        """準備文檔以進行索引
        
        Args:
            documents: 要處理的文檔列表
            user_id: 用戶 ID
            vector_service: 用於獲取向量的服務實例
            
        Returns:
            包含 (entities, texts, metadatas) 的元組
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
