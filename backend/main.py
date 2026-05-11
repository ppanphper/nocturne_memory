from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from api import review_router, browse_router, maintenance_router
from auth import BearerTokenAuthMiddleware, get_cors_config
from namespace_middleware import NamespaceMiddleware
from db import get_db_manager, close_db
from health import router as health_router
import os
import sys
from auth import enforce_network_auth

import argparse

# 拦截暴露在公网但缺少 Token 的 ASGI 启动 (如 uvicorn main:app --host 0.0.0.0)
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--host", type=str)
_args, _ = _parser.parse_known_args()
_host = _args.host or os.environ.get("HOST", os.environ.get("UVICORN_HOST", "127.0.0.1"))
enforce_network_auth(host=_host)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("Memory API starting...")

    # Initialize Database
    try:
        db_manager = get_db_manager()
        await db_manager.init_db()
        print("Database initialized.")
    except Exception as e:
        print(f"Failed to initialize database: {e}")

    yield

    # 关闭时
    print("Closing database connections...")
    await close_db()


app = FastAPI(
    title="Knowledge Graph API",
    description="AI长期记忆知识图谱后端",
    version="2.4.1",
    lifespan=lifespan,
)

app.add_middleware(
    BearerTokenAuthMiddleware,
    excluded_paths=["/health"],
)

app.add_middleware(NamespaceMiddleware)

app.add_middleware(
    CORSMiddleware,
    **get_cors_config(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health_router)
app.include_router(review_router)
app.include_router(browse_router)
app.include_router(maintenance_router)


@app.get("/")
async def root():
    """根路径"""
    return {"message": "Knowledge Graph API", "version": "2.4.1", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8233"))
    enforce_network_auth(host=host)
    uvicorn.run(app, host=host, port=port)
