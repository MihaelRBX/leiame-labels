from __future__ import annotations

import re
from typing import Any, Dict, Optional, List

from app.supabase_client import get_supabase

# -------- helpers --------

def _only_digits(s: Optional[str]) -> str:
    return re.sub(r"\D", "", s or "")

def to_e164_br(raw_phone: Optional[str]) -> Optional[str]:
    """Normaliza telefone BR para +55XXXXXXXXXX/XXXXX."""
    if not raw_phone:
        return None
    d = _only_digits(raw_phone).lstrip("0")
    if d.startswith("55"):
        d = d[2:]
    if len(d) not in (10, 11):
        return None
    return f"+55{d}"


def _tracking_url_from_order(order: Dict[str, Any]) -> Optional[str]:
    """
    Constrói a URL de rastreio:
      1) usa order['tracking_url'] se existir;
      2) senão usa service.company.tracking_link + (tracking || self_tracking);
      3) senão usa fallback do Melhor Rastreio com o código.
    """
    # 1) já veio pronta?
    if order.get("tracking_url"):
        return order["tracking_url"]

    code = order.get("tracking") or order.get("self_tracking")
    if not code:
        return None

    # 2) base enviada pela transportadora
    company = ((order.get("service") or {}).get("company") or {})
    base = company.get("tracking_link")
    if base:
        return f"{base.rstrip('/')}/{code}"

    # 3) fallback (seguro)
    return f"https://www.melhorrastreio.com.br/rastreio/{code}"

def _row_from_order(order: Dict[str, Any]) -> Dict[str, Any]:
    to_obj = order.get("to") or {}
    return {
        "order_id": order.get("id"),                          # UUID (36)
        "protocol": order.get("protocol"),                    # ORD-...
        "status": order.get("status"),
        "recipient_name": to_obj.get("name") or "cliente",
        "recipient_phone_e164": to_e164_br(to_obj.get("phone")),
        "tracking_code": order.get("tracking") or order.get("self_tracking"),
        "tracking_url": _tracking_url_from_order(order),
        "raw_payload": order,
    }



# -------- NOVO: upsert a partir de /me/orders (lista) --------

def upsert_shipments(orders: List[Dict[str, Any]]) -> None:
    if not orders:
        return
    rows = []
    for o in orders:
        if o.get("id"):
            rows.append(_row_from_order(o))
    if not rows:
        return
    sb = get_supabase()
    sb.table("me_orders").upsert(rows, on_conflict="order_id").execute()