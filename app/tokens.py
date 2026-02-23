from dotenv import load_dotenv
load_dotenv()

import os
import datetime as dt
from typing import Optional, TypedDict
import httpx

from app.supabase_client import get_supabase           # <-- com prefixo app.
from app.config import settings                        # <-- com prefixo app.

ME_TOKEN_ENDPOINT = settings.me_base_url.rstrip("/") + "/oauth/token"
CLIENT_ID = os.environ["ME_CLIENT_ID"]
CLIENT_SECRET = os.environ["ME_CLIENT_SECRET"]
REDIRECT_URI = os.environ["ME_REDIRECT_URI"]

LEWAY_MINUTES = 10  # renovar um pouco antes de expirar

class TokenRow(TypedDict, total=False):
    id: str
    account_id: str
    provider: str
    access_token: str
    refresh_token: str
    token_type: str
    scope: Optional[str]
    expires_at: str  # ISO 8601

def _now_utc() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)

def _parse_ts(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))

def get_token(account_id: str = "default") -> Optional[TokenRow]:
    sb = get_supabase()
    res = sb.table("me_tokens").select("*") \
        .eq("account_id", account_id).eq("provider", "melhor_envio") \
        .limit(1).execute()
    data = res.data or []
    return data[0] if data else None

def upsert_token(tr: TokenRow) -> TokenRow:
    sb = get_supabase()
    tr["provider"] = "melhor_envio"
    res = sb.table("me_tokens").upsert(tr, on_conflict="account_id,provider").execute()
    if not res.data:
        raise RuntimeError("Falha ao salvar token no Supabase.")
    return res.data[0]

def _needs_refresh(token: TokenRow) -> bool:
    exp = _parse_ts(token["expires_at"])
    return exp <= (_now_utc() + dt.timedelta(minutes=LEWAY_MINUTES))

async def _refresh_with_refresh_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "grant_type": "refresh_token",
            "client_id": int(CLIENT_ID),
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": settings.me_user_agent,
        }
        r = await client.post(ME_TOKEN_ENDPOINT, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()

async def _exchange_code_for_token(code: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": int(CLIENT_ID),
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": settings.me_user_agent,
        }
        r = await client.post(ME_TOKEN_ENDPOINT, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()

def _calc_expires_at(expires_in_seconds: int) -> str:
    return (_now_utc() + dt.timedelta(seconds=expires_in_seconds)).isoformat()

async def ensure_valid_token(account_id: str = "default") -> TokenRow:
    tk = get_token(account_id)
    if not tk:
        raise RuntimeError("Nenhum token salvo; rode o fluxo OAuth /oauth/callback para gerar.")

    if not _needs_refresh(tk):
        return tk

    try:
        refreshed = await _refresh_with_refresh_token(tk["refresh_token"])
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"Falha ao renovar token (HTTP {e.response.status_code}): {e.response.text}. "
            "Pode ser necessário refazer o fluxo OAuth."
        ) from e

    new_row: TokenRow = {
        "account_id": account_id,
        "access_token": refreshed["access_token"],
        "refresh_token": refreshed.get("refresh_token", tk["refresh_token"]),
        "token_type": refreshed.get("token_type", "Bearer"),
        "scope": refreshed.get("scope"),
        "expires_at": _calc_expires_at(int(refreshed["expires_in"])),
    }
    return upsert_token(new_row)
