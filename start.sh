#!/bin/bash

# Start the FastAPI backend in the background
echo "Starting backend on 127.0.0.1:8000..."
cd /app/backend
uvicorn src.api.routes:app --host 127.0.0.1 --port 8000 &

# Wait for the backend to be ready
echo "Waiting for backend to be ready on port 8000..."
python -c "
import socket, time
for i in range(60):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(('127.0.0.1', 8000))
            print('Backend is ready!')
            break
    except Exception:
        time.sleep(0.5)
"

# Start the Next.js frontend in the background
echo "Starting frontend on 0.0.0.0:${PORT:-3000}..."
cd /app/frontend
npm run start -- -p ${PORT:-3000} &
FRONTEND_PID=$!

# Wait for any of the processes to exit
wait -n

# Exit the container
exit 1
