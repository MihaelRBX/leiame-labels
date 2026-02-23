from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.routers.me import router as me_router
from app.clients.melhor_envio import init_http_client, close_http_client
from app.tokens import _exchange_code_for_token, _calc_expires_at, upsert_token

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_http_client()
    yield
    await close_http_client()

app = FastAPI(title="Loja + Melhor Envio", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Rotas da API
app.include_router(me_router)     # /api/v1/me/*

# Front
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.get("/health")
async def health():
    return {"ok": True}

# OAuth callback
@app.get("/oauth/callback")
async def oauth_callback(code: str, account_id: str | None = "default"):
    try:
        tk = await _exchange_code_for_token(code)
        row = {
            "account_id": account_id or "default",
            "access_token": tk["access_token"],
            "refresh_token": tk["refresh_token"],
            "token_type": tk.get("token_type", "Bearer"),
            "scope": tk.get("scope"),
            "expires_at": _calc_expires_at(int(tk["expires_in"])),
        }
        upsert_token(row)
        return {"received": True, "saved": True, "account_id": account_id}
    except Exception as e:
        return {"received": True, "saved": False, "error": repr(e)}

