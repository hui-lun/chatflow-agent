.env settings:

VLLM_API_BASE=

MONGO_INITDB_ROOT_USERNAME=
MONGO_INITDB_ROOT_PASSWORD=
MONGO_INITDB_DATABASE=

docker compose up --build
docker compose down

## 刪除 mongodb_data volume
docker compose down -v 