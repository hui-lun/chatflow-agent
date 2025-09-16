import os
import logging
from typing import List, Dict, Any, Tuple
from io import StringIO
import pandas as pd

from langchain.schema.document import Document
from unstructured.partition.pdf import partition_pdf
from unstructured.chunking.title import chunk_by_title
from unstructured.documents.elements import Table, NarrativeText, Title

logger = logging.getLogger(__name__) 

class DocumentProcessor:
    """
    處理文檔加載和語義分塊的服務類。
    採用先進的表格處理策略，將每一行表格數據轉換為獨立的語義單元。
    """
    
    def __init__(self, chunk_size: int = 4000, chunk_overlap: int = 500):
        """初始化文檔處理器"""
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _create_document(self, page_content: str, source_path: str, metadata_extra: dict = None) -> Document:
        """輔助函式：創建一個標準化的 Document 物件"""
        metadata = {
            "source": source_path,
            "filename": os.path.basename(source_path),
            "file_type": "pdf",
            **(metadata_extra or {})
        }
        metadata = {k: str(v) for k, v in metadata.items() if v is not None}
        return Document(page_content=page_content.strip(), metadata=metadata)

    def _process_table_element(self, table_element: Table, source_path: str, context_title: str) -> List[Document]:
        """
        核心函式：將單個 Table 元素按行轉換為多個 Document 物件。
        """
        docs = []
        html_table = table_element.metadata.text_as_html
        if not html_table:
            return []

        try:
            dfs = pd.read_html(StringIO(html_table), flavor='lxml')
            if not dfs:
                return []
            
            df = dfs[0]
            
            # 清理和扁平化多級標頭
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = ['_'.join(map(str, col)).strip() for col in df.columns.values]
            else:
                df.columns = [str(c).strip() for c in df.columns]

            # 將 DataFrame 轉換為字典列表，每一項代表一行
            records = df.to_dict('records')
            
            # 為整個表格創建一個摘要文檔
            table_summary_content = f"Table context: {context_title}\n" if context_title else ""
            table_summary_content += "This table contains data about: "
            table_summary_content += ", ".join(df.columns)
            
            summary_doc = self._create_document(
                table_summary_content, 
                source_path, 
                {'section_title': context_title, 'is_summary': 'true'}
            )
            docs.append(summary_doc)
            
            for record in records:
                # 建立更自然的 page_content
                page_content = f"From table '{context_title}', here is a record: " if context_title else "Here is a data record: "
                
                row_kv_pairs = []
                for key, value in record.items():
                    if pd.notna(value) and str(value).strip():
                        row_kv_pairs.append(f"'{key}' is '{value}'")
                
                page_content += ", ".join(row_kv_pairs)
                page_content += "."
                
                # 建立包含結構化數據的 metadata
                metadata = record.copy()
                if context_title:
                    metadata['section_title'] = context_title
                
                docs.append(self._create_document(page_content, source_path, metadata))
            
            logger.info(f"成功將一個表格分解為 {len(docs)} 個文檔 (包括1個摘要).")
            return docs

        except Exception as e:
            logger.warning(f"解析表格失敗，將其作為單一文本塊處理: {e}")
            # Fallback: 嘗試將整個表格作為一個 HTML 塊的文檔
            try:
                html_table = table_element.metadata.text_as_html
                if not html_table:
                    return []

                context_prefix = f"Context: {context_title}\n" if context_title else ""
                page_content = f"{context_prefix}A table failed to parse into structured rows. Here is its raw HTML content:\n\n{html_table}"
                
                fallback_doc = self._create_document(
                    page_content, 
                    source_path, 
                    {'section_title': context_title, 'parsing_failed': 'true', 'format': 'html'}
                )
                logger.info("成功創建了一個回退 HTML 表格文檔。")
                return [fallback_doc]
            except Exception as fallback_e:
                logger.error(f"在創建回退表格文檔時也失敗了: {fallback_e}")
                return []

    def process_and_chunk_pdfs(self, pdf_paths: List[str]) -> List[Document]:
        """
        使用基於行數據的語義結構重組策略來處理 PDF。
        """
        all_docs = []
        for path in pdf_paths:
            if not os.path.exists(path):
                logger.warning(f"文件不存在: {path}")
                continue
            
            try:
                logger.info(f"開始使用 hi_res 策略處理: {path}")
                elements = partition_pdf(
                    filename=path,
                    strategy="hi_res",
                    extract_image_block_types=["Table"],
                    pdf_infer_table_structure=True,
                    include_page_breaks=True
                )
                
                non_table_elements = []
                last_title_text = ""
                
                for element in elements:
                    if isinstance(element, Title):
                        last_title_text = element.text.strip()
                        non_table_elements.append(element)
                    
                    elif isinstance(element, Table):
                        # 優先嘗試按行進行結構化處理
                        row_docs = self._process_table_element(element, path, last_title_text)
                        if row_docs:
                            all_docs.extend(row_docs)
                        else:
                            # 如果處理失敗，則將表格作為普通文本進行回退處理
                            non_table_elements.append(element)
                    
                    else: # 其他類型的元素
                        non_table_elements.append(element)

                # 對所有非表格內容和處理失敗的表格，使用傳統方法分塊
                if non_table_elements:
                    chunks = chunk_by_title(
                        non_table_elements,
                        max_characters=self.chunk_size,
                        new_after_n_chars=self.chunk_size - self.chunk_overlap,
                        combine_text_under_n_chars=self.chunk_overlap
                    )
                    for chunk in chunks:
                        doc = self._create_document(chunk.text, path, chunk.metadata.to_dict())
                        all_docs.append(doc)
                
                logger.info(f"文件 {path} 處理完成，共生成 {len(all_docs)} 個文檔塊。")

            except Exception as e:
                logger.error(f"處理 {path} 時發生嚴重錯誤: {e}", exc_info=True)
                continue
                
        return all_docs

    def prepare_for_indexing(
        self, 
        documents: List[Document], 
        user_id: str,
        vector_service: Any,
        file_id: str = None
    ) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
        """準備文檔以進行索引 (此方法保持不變)"""
        if not documents:
            return [], [], []
            
        texts = [d.page_content for d in documents]
        metadatas = [d.metadata for d in documents]
        
        vecs = vector_service.get_vectors(texts)
        
        entities = []
        for i, (text, dense_vec, sparse_raw) in enumerate(zip(texts, vecs["dense_vectors"], vecs["sparse_vectors"])):
            metadata = metadatas[i]
            metadata["user_id"] = user_id
            if file_id:
                metadata["file_id"] = file_id
            
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
            
        return entities, texts, metadatas
