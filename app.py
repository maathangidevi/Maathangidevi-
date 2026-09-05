"""
RetailIQ – Entry Point
Starts FastAPI application on port 8000.
Usage: python app.py
"""
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    uvicorn.run(
        "backend.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
