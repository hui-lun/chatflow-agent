import os
from pymilvus import MilvusClient, DataType, CollectionSchema, FieldSchema

# Milvus 連接配置
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
COLLECTION_NAME = "entities"

def inspect_milvus_collection():
    print(f"正在連接到 Milvus: {MILVUS_URI}")
    client = MilvusClient(uri=MILVUS_URI)

    # 檢查 collection 是否存在
    if not client.has_collection(collection_name=COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' 不存在。")
        return

    print(f"Collection '{COLLECTION_NAME}' 存在。正在加載...")
    # 加載 collection (如果尚未加載)
    # client.load_collection(collection_name=COLLECTION_NAME) # MilvusClient v2.2.x 及更高版本會自動加載

    # 獲取 collection 的 schema
    schema_dict = client.describe_collection(collection_name=COLLECTION_NAME)
    print(f"\nCollection '{COLLECTION_NAME}' 的 Schema:")
    
    # 檢查 schema_dict 是否包含 'fields' 鍵
    if 'fields' in schema_dict and isinstance(schema_dict['fields'], list):
        for field_info in schema_dict['fields']:
            name = field_info.get('name', 'N/A')
            dtype = field_info.get('type', 'N/A') # 注意這裡可能是 'type' 而不是 'dtype'
            is_primary = field_info.get('is_primary', False)
            dim = field_info.get('dim', 'N/A')
            print(f"  - {name}: {dtype} (is_primary: {is_primary}, dim: {dim})")
    else:
        print("  無法解析 Schema 字段信息。原始 Schema 字典:")
        print(schema_dict)

    # 獲取 collection 的統計資訊
    stats = client.get_collection_stats(collection_name=COLLECTION_NAME)
    print(f"\nCollection '{COLLECTION_NAME}' 的統計資訊:")
    print(f"  總實體數: {stats['row_count']}")

    # 執行一個簡單的查詢來檢索資料
    # 注意：這裡需要一個向量來執行向量相似度搜索。
    # 如果您只是想查看資料，可以使用 query 方法。
    # 為了簡單起見，我們將嘗試使用 query 方法來獲取一些資料。

    # 假設我們想獲取前 10 條資料，並且包含 'user_id' 欄位
    # 這裡需要知道 collection 中有哪些欄位可以查詢。
    # 根據您提供的 multi_user_rag_cli.py，應該有 'id', 'vector', 'created_at', 'user_id' 等。
    # 如果有 'entity_name' 或 'file_path' 等，也可以包含。
    
    # 為了避免錯誤，我們只查詢已知的通用欄位
    output_fields = ["id", "created_at", "user_id"]
    
    # 嘗試從 schema 中獲取所有非向量欄位作為 output_fields
    output_fields_from_schema = []
    if 'fields' in schema_dict and isinstance(schema_dict['fields'], list):
        for field_info in schema_dict['fields']:
            if field_info.get('type') != 'FloatVector': # 假設向量字段類型是 'FloatVector'
                output_fields_from_schema.append(field_info.get('name'))
    output_fields = list(set(output_fields + output_fields_from_schema))


    print(f"\n正在查詢 Collection '{COLLECTION_NAME}' 的前 10 條資料...")
    try:
        # 使用 query 方法來獲取資料，不進行向量搜索
        # 這裡我們不提供 expr，或者提供一個簡單的 expr 來獲取所有資料
        # limit 參數用於限制返回的資料數量
        results = client.query(
            collection_name=COLLECTION_NAME,
            filter="", # 空字符串表示不過濾，獲取所有資料
            output_fields=output_fields,
            limit=2
        )
        
        if results:
            print(f"檢索到 {len(results)} 條資料:")
            for i, item in enumerate(results):
                print(f"--- 資料 {i+1} ---")
                for field, value in item.items():
                    print(f"  {field}: {value}")
        else:
            print("沒有檢索到任何資料。")

    except Exception as e:
        print(f"查詢資料時發生錯誤: {e}")

    # 斷開連接 (MilvusClient 會自動管理連接，但顯式關閉是個好習慣)
    # client.close() # MilvusClient v2.2.x 及更高版本不需要顯式關閉

if __name__ == "__main__":
    inspect_milvus_collection()
