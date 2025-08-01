# ChatFlow Agent - 聊天記錄持久化功能

## 🎯 功能概述

本次更新為 ChatFlow Agent 新增了完整的聊天記錄持久化功能，所有聊天記錄現在都會儲存到 MongoDB 資料庫中。

## ✨ 新增功能

### 1. 資料庫整合
- **MongoDB 連接服務**: 自動連接和斷開資料庫
- **聊天記錄儲存**: 每條聊天記錄包含用戶訊息、機器人回應、時間戳和會話 ID
- **會話管理**: 支援多個會話，每個會話有獨立的聊天歷史

### 2. 後端 API 增強

#### 新增 API 端點：
- `GET /health` - 健康檢查端點
- `GET /chat/history` - 獲取聊天歷史
- `GET /chat/sessions` - 獲取所有會話列表

#### 更新的 API 端點：
- `POST /chat` - 現在支援 `session_id` 參數並自動儲存聊天記錄

### 3. 前端介面升級

#### 新增 UI 元素：
- **聊天標題**: 顯示 "ChatFlow Agent"
- **會話選擇器**: 下拉選單選擇不同會話
- **新會話按鈕**: 創建新的聊天會話
- **訊息時間戳**: 顯示每條訊息的發送時間
- **載入狀態**: 顯示 "Thinking..." 狀態

#### 改進的用戶體驗：
- 自動滾動到最新訊息
- 響應式設計支援手機和平板
- 更好的錯誤處理和載入狀態

## 🗄️ 資料庫結構

### 聊天記錄集合 (`chat_messages`)
```javascript
{
  "user_message": "用戶訊息",
  "bot_response": "機器人回應", 
  "session_id": "會話ID",
  "timestamp": "2024-01-01T12:00:00Z",
  "created_at": "2024-01-01T12:00:00Z"
}
```

## 🚀 部署說明

### 1. 環境變數配置
確保 `.env` 文件包含以下變數：
```bash
VLLM_API_BASE=your_vllm_api_url
MONGO_INITDB_ROOT_USERNAME=your_mongo_username
MONGO_INITDB_ROOT_PASSWORD=your_mongo_password
MONGO_INITDB_DATABASE=chatflow
```

### 2. 啟動服務
```bash
# 構建並啟動所有服務
docker compose up --build

# 僅啟動服務（如果已經構建過）
docker compose up
```

### 3. 訪問應用
- **前端**: http://localhost:3000
- **MongoDB 管理介面**: http://localhost:8081
- **後端 API 文檔**: http://localhost:8000/docs

## 🧪 測試功能

### 使用測試腳本
```bash
# 安裝依賴
pip install requests

# 運行測試
python test_chat_api.py
```

### 手動測試
1. 訪問 http://localhost:3000
2. 發送一些測試訊息
3. 創建新會話並測試會話切換
4. 檢查聊天歷史是否正確載入

## 📊 API 使用範例

### 發送聊天訊息
```bash
curl -X POST http://localhost:3000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, how are you?",
    "session_id": "my_session"
  }'
```

### 獲取聊天歷史
```bash
curl "http://localhost:3000/chat/history?session_id=my_session&limit=10"
```

### 獲取所有會話
```bash
curl http://localhost:3000/chat/sessions
```

### 健康檢查
```bash
curl http://localhost:3000/health
```

## 🔧 故障排除

### 常見問題

1. **MongoDB 連接失敗**
   - 檢查環境變數是否正確設置
   - 確保 MongoDB 容器正在運行
   - 檢查網路連接

2. **前端無法載入聊天歷史**
   - 檢查瀏覽器控制台錯誤
   - 確認後端 API 正常運行
   - 檢查 nginx 代理配置

3. **聊天記錄未儲存**
   - 檢查後端日誌
   - 確認資料庫連接正常
   - 檢查 API 回應狀態

### 日誌查看
```bash
# 查看後端日誌
docker compose logs backend

# 查看前端日誌
docker compose logs frontend

# 查看 MongoDB 日誌
docker compose logs mongodb
```

## 🎨 自定義配置

### 修改聊天記錄限制
在 `backend/app/services/database.py` 中修改 `get_chat_history` 的預設 limit 值。

### 自定義會話 ID 格式
在 `frontend/src/App.vue` 中修改 `createNewSession` 函數的會話 ID 生成邏輯。

### 調整 UI 樣式
修改 `frontend/src/assets/styles/main.scss` 來自定義介面外觀。

## 📈 效能考量

- 聊天歷史預設限制為 50 條記錄
- 使用 MongoDB 索引優化查詢效能
- 前端實作虛擬滾動以處理大量訊息
- 支援分頁載入聊天歷史

## 🔮 未來改進

- [ ] 實作訊息搜尋功能
- [ ] 新增訊息編輯和刪除功能
- [ ] 支援檔案上傳和圖片分享
- [ ] 實作用戶認證和權限管理
- [ ] 新增聊天統計和分析功能
- [ ] 支援多語言介面 