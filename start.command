#!/bin/bash

# Navigate to the exact directory where this script lives
cd "$(dirname "$0")"

echo "==========================================="
echo "🚀 Digital DNA - Mac Initializer"
echo "==========================================="

echo "🔄 Syncing latest changes from repository..."
if [ -d ".git" ]; then
    CURRENT_BRANCH=$(git branch --show-current)
    if [ -z "$CURRENT_BRANCH" ]; then
        CURRENT_BRANCH="main"
    fi
    git fetch origin
    git reset --hard origin/$CURRENT_BRANCH
else
    echo "⚠️ Not a git repository... Skipping git sync."
fi

echo "🐍 Setting up Python Virtual Environment..."
# Check if python3 exists
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed or not in your PATH. Please install Python 3."
    echo "Press any key to exit..."
    read -n 1
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "📦 Creating new virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

echo "⬇️ Installing Python dependencies..."
pip install -e .

echo "📦 Setting up Frontend React App..."
cd webapp-react
if [ ! -d "node_modules" ]; then
    echo "⬇️ Installing NPM dependencies..."
    npm install
fi
cd ..

echo "==========================================="
echo "⚡ Starting Services..."
echo "==========================================="

# Define cleanup function to kill both backend and frontend on exit
cleanup() {
    echo "🛑 Shutting down services..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}

# Trap INT and TERM signals when the user hits Ctrl+C or closes the terminal
trap cleanup SIGINT SIGTERM EXIT

# Start FastAPI Backend
echo "🚀 Starting Python Backend..."
python webapp/server.py &
BACKEND_PID=$!

# Start React Frontend
echo "🚀 Starting React Frontend..."
cd webapp-react
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait briefly for ports to bind
sleep 3

echo "🌐 Opening Browser..."
open "http://localhost:5173" || echo "Please go to http://localhost:5173 manually."

echo "✅ App is running! Keep this terminal window open."
echo "Press Ctrl+C or simply close this window to stop the servers."

# Wait indefinitely, keeps the script alive until interrupted
wait $BACKEND_PID
wait $FRONTEND_PID
