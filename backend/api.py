#!/usr/bin/env python3
"""
HeatMap FastAPI Backend
Main API server that serves blockchain wallet analysis data
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yaml
from pathlib import Path
from dotenv import load_dotenv

from src.api.routes import router

# Load environment variables
load_dotenv()

# Load config
config_path = Path("config/base.yaml")
with open(config_path) as f:
    config = yaml.safe_load(f)

# Create FastAPI app
app = FastAPI(
    title=config['api']['title'],
    version=config['api']['version'],
    description="API for blockchain wallet analysis and ML insights"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config['api']['cors_origins'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "API is running"}


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))
    
    print(f"\n🚀 Starting HeatMap API server...")
    print(f"   URL: http://{host}:{port}")
    print(f"   Docs: http://{host}:{port}/docs")
    print(f"   Health: http://{host}:{port}/health\n")
    
    uvicorn.run(app, host=host, port=port)