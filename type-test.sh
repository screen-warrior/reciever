curl -X POST http://127.0.0.1:8765/type \
  -H "x-token: change-me-local-token" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello from the Mac receiver!\n","start_delay":4}'
