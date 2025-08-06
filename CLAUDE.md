# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Architecture

This is a full-stack chatbot application with persistent chat storage using FastAPI backend, Vue.js frontend, and MongoDB database. The application supports multi-session chat conversations with authentication.

### Tech Stack
- **Backend**: FastAPI with LangChain integration for vLLM API
- **Frontend**: Vue.js 3 with Vite build system
- **Database**: MongoDB with PyMongo driver
- **Authentication**: JWT tokens with bcrypt password hashing
- **Deployment**: Docker Compose with multi-container setup

### Key Components
- `backend/app/main.py`: FastAPI application with CORS, authentication, and chat endpoints
- `backend/app/services/llm.py`: LangChain ChatOpenAI wrapper for vLLM integration
- `backend/app/services/database.py`: MongoDB service for chat persistence
- `backend/app/auth.py`: JWT authentication service
- `frontend/src/App.vue`: Main Vue.js chat interface
- `frontend/src/api/`: API client modules for backend communication

## Development Commands

### Full Stack Development
```bash
# Start all services (recommended for development)
docker compose up --build

# Start in background
docker compose up --build -d

# View logs
docker compose logs backend
docker compose logs frontend
docker compose logs mongodb
```

### Backend Development
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development
```bash
cd frontend
npm install
npm run dev          # Development server
npm run build        # Production build
npm run preview      # Preview production build
```

### Testing
```bash
# API testing script
python test_chat_api.py

# Prerequisites: ensure services are running first
docker compose up -d
```

## Environment Configuration

Required environment variables (create `.env` file):
```bash
VLLM_API_BASE=http://your-vllm-server:8001/v1
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=password123
MONGO_INITDB_DATABASE=chatflow
```

## Service URLs
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (docs at /docs)
- MongoDB Admin: http://localhost:8081
- MongoDB: localhost:27017

## Database Schema

### chat_messages collection
```javascript
{
  "user_message": "string",
  "bot_response": "string", 
  "session_id": "string",
  "timestamp": "datetime",
  "created_at": "datetime"
}
```

### users collection (for authentication)
```javascript
{
  "username": "string",
  "hashed_password": "string",
  "created_at": "datetime"
}
```

## Authentication Flow

The application uses JWT token authentication:
1. Users authenticate via POST `/auth/login` with username/password
2. Receive JWT access token (30min expiry)
3. Include token in Authorization header for protected endpoints
4. All chat endpoints require authentication

## API Endpoints

### Authentication
- `POST /auth/login` - User login
- `GET /auth/me` - Get current user info

### Chat (Protected)
- `POST /chat` - Send message and get response
- `GET /chat/history` - Get chat history for session
- `GET /chat/sessions` - Get all session IDs
- `GET /health` - Health check

## Development Notes

- The vLLM integration uses model "gemma-3-27b-it" - modify in `backend/app/services/llm.py` if needed
- Frontend proxies `/chat` requests to backend container via Vite config
- MongoDB connection includes auto-retry logic and graceful error handling
- Chat history is limited to 50 messages by default to prevent performance issues
- CORS is configured for localhost:3000 and container networking