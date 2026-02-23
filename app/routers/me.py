from __future__ import annotations
import asyncio
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Any, Dict, List

from app.clients.melhor_envio import me_get, me_post, get_order
from app.db.repos import upsert_shipments

router = APIRouter(prefix="/api/v1/me", tags=["melhor-envio"])

ELIGIBLE = {"paid", "released"}

def _is_eligible(o: Dict[str, Any]) -> bool:
    s = (o.get("status") or "").lower()
    return (
        (s in ELIGIBLE)
        and (o.get("generated_at") is None)
        and not any(o.get(k) for k in ("canceled_at", "expired_at", "suspended_at"))
    )

async def _fetch_orders_by_ids(ids: List[str]) -> List[Dict[str, Any]]:
    """Busca cada order individualmente (evita paginar tudo)."""
    tasks = [get_order(oid) for oid in ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    orders: List[Dict[str, Any]] = []
    for r in results:
        if isinstance(r, dict) and r.get("id"):
            orders.append(r)
    return orders

def _with_tracking(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [o for o in orders if (o.get("tracking") or o.get("self_tracking"))]

@router.get("/orders")
async def list_orders(
    only_eligible: bool = Query(False, description="Se true, aplica status=released direto no ME"),
    only_unlabeled: bool = Query(True, description="Se true, retorna apenas pedidos sem generated_at"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """
    Pass-through paginado para /me/orders.
    - only_eligible => filtra no ME por status=released
    - only_unlabeled => filtra localmente por generated_at is null
    """
    try:
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if only_eligible:
            params["status"] = "released"

        resp = await me_get("/me/orders", params=params)

        data = resp.get("data", []) if isinstance(resp, dict) else (resp or [])
        if only_unlabeled:
            data = [
                o for o in data
                if o.get("generated_at") in (None, "")  # etiqueta AINDA não gerada
                and not any(o.get(k) for k in ("canceled_at", "expired_at", "suspended_at"))
            ]

        resp["data"] = data
        resp["ok"] = True
        return resp
    except Exception as e:
        raise HTTPException(400, f"Falha ao listar pedidos: {e!r}")


class GenerateBody(BaseModel):
    orders: List[str] = Field(..., min_items=1, description="UUIDs de 36 chars (id), não usar ORD-...")

async def _delayed_sync(ids: List[str], delay_seconds: int = 60) -> None:
    """
    Aguarda 'delay_seconds', busca as orders individualmente e faz upsert SOMENTE
    das que já tiverem tracking_code/self_tracking.
    """
    try:
        await asyncio.sleep(delay_seconds)
        fetched = await _fetch_orders_by_ids(ids)
        with_track = _with_tracking(fetched)
        if with_track:
            upsert_shipments(with_track)
    except Exception:
        return

@router.post("/generate")
async def generate_labels(body: GenerateBody, background_tasks: BackgroundTasks):
    """
    Gera etiqueta(s) via /me/shipment/generate.
    - Tenta sincronizar imediatamente as que já tiverem tracking.
    - Agenda uma sync atrasada (60s) para capturar o tracking que aparece depois.
    """
    try:
        # 1) gerar
        await me_post("/me/shipment/generate", json={"orders": body.orders})

        # 2) tentativa imediata
        fetched_now = await _fetch_orders_by_ids(body.orders)
        now_with_track = _with_tracking(fetched_now)
        if now_with_track:
            upsert_shipments(now_with_track)

        # 3) agenda a sync atrasada (60s)
        background_tasks.add_task(_delayed_sync, body.orders, 60)

        return {
            "ok": True,
            "generated": body.orders,
            "synced_now": [o["id"] for o in now_with_track] if now_with_track else [],
            "deferred_sync_seconds": 60,
        }
    except Exception as e:
        raise HTTPException(400, f"Falha ao gerar etiquetas: {e!r}")
