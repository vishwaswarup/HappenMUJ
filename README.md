# HappenMUJ

Campus event discovery and community platform for Manipal University Jaipur. NoSQL course project: MongoDB backend + REST API
(frontend comes last). Full README with a viva demo script arrives in M7.

## Quick start
```bash
docker compose up -d                 # or ./scripts/local_mongo.sh if Docker is unavailable
cd backend && uv sync --python 3.12
cp ../.env.example .env              # adjust MONGO_URI if using local_mongo.sh (port 27018)
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000/docs
.venv/bin/pytest -q
```
