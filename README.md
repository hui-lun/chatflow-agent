# ChatFlow Agent

一個基於 FastAPI + Vue.js 的現代化聊天機器人應用程式，具備完整的聊天記錄持久化功能。

## 🚀 功能特色

- **智能聊天**: 整合 vLLM API 提供高品質的 AI 對話體驗
- **資料持久化**: 所有聊天記錄自動儲存到 MongoDB 資料庫
- **會話管理**: 支援多個聊天會話，可獨立管理不同對話
- **聊天歷史**: 完整的聊天記錄查詢和瀏覽功能
- **現代化 UI**: 響應式設計，支援桌面和移動設備
- **容器化部署**: 使用 Docker Compose 一鍵部署

## 🏗️ 技術架構

### 後端技術棧
- **FastAPI**: 現代化 Python Web 框架
- **LangChain**: LLM 應用開發框架
- **MongoDB**: NoSQL 資料庫
- **Uvicorn**: ASGI 伺服器

### 前端技術棧
- **Vue.js 3**: 響應式前端框架
- **Vite**: 現代化建構工具
- **SCSS**: CSS 預處理器
- **Nginx**: Web 伺服器和反向代理

### 部署技術
- **Docker**: 容器化技術
- **Docker Compose**: 容器編排
- **MongoDB**: 資料持久化

## 📋 系統需求

- Docker 20.10+
- Docker Compose 2.0+
- 至少 2GB 可用記憶體
- 網路連接（用於下載 Docker 映像）

## 🛠️ 快速開始

### 1. 克隆專案

```bash
git clone <repository-url>
cd chatflow-agent
```

### 2. 配置環境變數

創建 `.env` 文件並配置以下變數：

```bash
# vLLM API 配置
VLLM_API_BASE=http://your-vllm-server:8001/v1

# MongoDB 配置
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=password123
MONGO_INITDB_DATABASE=chatflow
```

### 3. 啟動服務

```bash
# 構建並啟動所有服務
docker compose up --build

# 或使用後台模式
docker compose up --build -d
```

### 4. 訪問應用

- **前端介面**: http://localhost:3000
- **MongoDB 管理介面**: http://localhost:8081
- **後端 API 文檔**: http://localhost:8000/docs

## 📖 使用指南

### 基本聊天功能

1. 訪問 http://localhost:3000
2. 在輸入框中輸入您的訊息
3. 點擊「Send」按鈕或按 Enter 發送
4. 等待 AI 回應

### 會話管理

- **切換會話**: 使用下拉選單選擇不同的聊天會話
- **創建新會話**: 點擊「New Session」按鈕創建新的會話
- **查看歷史**: 聊天記錄會自動載入並顯示

### API 使用

#### 發送聊天訊息
```bash
curl -X POST http://localhost:3000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, how are you?",
    "session_id": "my_session"
  }'
```

#### 獲取聊天歷史
```bash
curl "http://localhost:3000/chat/history?session_id=my_session&limit=10"
```

#### 獲取所有會話
```bash
curl http://localhost:3000/chat/sessions
```

#### 健康檢查
```bash
curl http://localhost:3000/health
```

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

## 🔧 開發指南

### 本地開發環境

#### 後端開發
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 前端開發
```bash
cd frontend
npm install
npm run dev
```

### 專案結構

```
chatflow-agent/
├── backend/                 # 後端服務
│   ├── app/
│   │   ├── main.py         # FastAPI 主應用
│   │   └── services/
│   │       ├── llm.py      # LLM 服務整合
│   │       └── database.py # 資料庫服務
│   ├── requirements.txt     # Python 依賴
│   └── Dockerfile          # 後端容器化
├── frontend/               # 前端應用
│   ├── src/
│   │   ├── App.vue         # 主要 Vue 組件
│   │   ├── api/
│   │   │   └── chat.js     # API 調用模組
│   │   └── assets/
│   │       └── styles/
│   │           └── main.scss # 樣式文件
│   ├── package.json        # Node.js 依賴
│   ├── Dockerfile          # 前端容器化
│   └── nginx.conf          # Nginx 配置
├── docker-compose.yml      # 容器編排配置
└── README.md              # 專案說明
```

## 🧪 測試

### 運行測試腳本
```bash
# 安裝依賴
pip install requests

# 運行測試
python test_chat_api.py
```

### 手動測試
1. 訪問前端介面
2. 發送測試訊息
3. 創建新會話並測試會話切換
4. 檢查聊天歷史是否正確載入

## 🚨 故障排除

### 常見問題

#### 1. 服務無法啟動
```bash
# 檢查容器狀態
docker compose ps

# 查看日誌
docker compose logs backend
docker compose logs frontend
```

#### 2. MongoDB 連接失敗
- 檢查環境變數是否正確設置
- 確保 MongoDB 容器正在運行
- 檢查網路連接

#### 3. 前端無法載入聊天歷史
- 檢查瀏覽器控制台錯誤
- 確認後端 API 正常運行
- 檢查 nginx 代理配置

#### 4. 聊天記錄未儲存
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

## 📊 效能考量

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
- [ ] 實作 WebSocket 即時通訊
- [ ] 添加聊天機器人個性化設定

