import os
from pymilvus import MilvusClient

# Milvus 連接配置
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
# COLLECTION_NAME = "lightrag_shared_collection"
# COLLECTION_NAME = "kb_user1"
COLLECTION_NAME = ["entities","relationships","chunks"]
def delete_milvus_collection():
    print(f"正在連接到 Milvus: {MILVUS_URI}")
    client = MilvusClient(uri=MILVUS_URI)
    for t in COLLECTION_NAME:
        if not client.has_collection(collection_name=t):
            print(f"Collection '{t}' 不存在，無需刪除。")
            return

        print(f"Collection '{t}' 存在。正在刪除...")
        try:
            client.drop_collection(collection_name=t)
            print(f"Collection '{t}' 已成功刪除。")
        except Exception as e:
            print(f"刪除 Collection '{t}' 時發生錯誤: {e}")            
    # # 檢查 collection 是否存在
    # if not client.has_collection(collection_name=COLLECTION_NAME):
    #     print(f"Collection '{COLLECTION_NAME}' 不存在，無需刪除。")
    #     return

    # print(f"Collection '{COLLECTION_NAME}' 存在。正在刪除...")
    # try:
    #     client.drop_collection(collection_name=COLLECTION_NAME)
    #     print(f"Collection '{COLLECTION_NAME}' 已成功刪除。")
    # except Exception as e:
    #     print(f"刪除 Collection '{COLLECTION_NAME}' 時發生錯誤: {e}")

if __name__ == "__main__":
    delete_milvus_collection()
