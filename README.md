# telegramm_ai_service

uvicorn main:app --host 0.0.0.0 --port 8001

docker run -d -p 80:8080 -e bootstrapServers="kafka1:9092" -e kouncil.auth.active-provider="inmemory" consdata/kouncil:latest