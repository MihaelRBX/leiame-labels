from __future__ import annotations
import asyncio
import httpx
from typing import Any, Dict, Optional, List
from app.tokens import ensure_valid_token
from app.config import settings


_base = settings.me_base_url.rstrip("/")
if not _base.endswith("/api/v2"):
    _base = f"{_base}/api/v2"
ME_API_BASE = _base

ME_USER_AGENT = settings.me_user_agent
DEFAULT_TIMEOUT = 30.0  # s

_CLIENT: httpx.AsyncClient | None = None

async def init_http_client() -> None:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers={
                "Accept": "application/json",
                "User-Agent": ME_USER_AGENT,
            },
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )

async def close_http_client() -> None:
    global _CLIENT
    if _CLIENT is not None:
        await _CLIENT.aclose()
        _CLIENT = None

def _client() -> httpx.AsyncClient:
    if _CLIENT is None:
        raise RuntimeError("HTTP client não inicializado. Chame init_http_client() no startup.")
    return _CLIENT

async def _request_with_retry(
    method: str,
    path: str,
    account_id: str = "default",
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Any] = None,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Any:
    url = f"{ME_API_BASE}{path if path.startswith('/') else '/' + path}"

    token_row = await ensure_valid_token(account_id)
    token = token_row["access_token"]

    hdrs = {"Authorization": f"Bearer {token}"}
    if headers:
        hdrs.update(headers)

    client = _client()
    r = await client.request(
        method.upper(),
        url,
        params=params,
        json=json,
        data=data,
        headers=hdrs,
        timeout=timeout or DEFAULT_TIMEOUT,
    )

    if r.status_code == 401:
        token_row = await ensure_valid_token(account_id)  # fará refresh se necessário
        hdrs["Authorization"] = f"Bearer {token_row['access_token']}"
        r = await client.request(
            method.upper(), url, params=params, json=json, data=data, headers=hdrs, timeout=timeout or DEFAULT_TIMEOUT
        )

    attempts = 0
    while 500 <= r.status_code < 600 and attempts < 2:
        attempts += 1
        await asyncio.sleep(0.5 * attempts)  # backoff
        r = await client.request(
            method.upper(), url, params=params, json=json, data=data, headers=hdrs, timeout=timeout or DEFAULT_TIMEOUT
        )

    r.raise_for_status()
    if r.status_code == 204 or not r.content:
        return None
    return r.json()

async def me_get(
    path: str,
    account_id: str = "default",
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Any:
    return await _request_with_retry("GET", path, account_id=account_id, params=params, headers=headers, timeout=timeout)

async def me_post(
    path: str,
    account_id: str = "default",
    *,
    json: Optional[Any] = None,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Any:
    return await _request_with_retry("POST", path, account_id=account_id, json=json, data=data, headers=headers, timeout=timeout)

async def get_order(order_id: str, account_id: str = "default") -> Dict[str, Any]:
    """Obtém uma ordem individual (útil para depuração)."""
    return await me_get(f"/me/orders/{order_id}", account_id=account_id)

async def list_orders_all_pages(account_id: str = "default") -> List[Dict[str, Any]]:
    """
    Lista todos os pedidos do ME agregando paginação.
    Útil para o front 'Listar pedidos' e para sincronizar no Supabase.
    """
    page = 1
    out: List[Dict[str, Any]] = []
    while True:
        resp = await me_get(f"/me/orders?page={page}", account_id=account_id)
        data = resp.get("data") if isinstance(resp, dict) else resp
        if not data:
            break
        out.extend(data)
        if not resp.get("next_page_url"):
            break
        page += 1
    return out

async def shipment_generate(orders: List[str], account_id: str = "default") -> Any:
    """
    Gera etiquetas para uma lista de UUIDs (36 chars) de pedidos já comprados.
    Equivale ao POST /me/shipment/generate.
    """
    if not orders:
        return {"data": []}
    return await me_post("/me/shipment/generate", account_id=account_id, json={"orders": orders})
