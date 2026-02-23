from __future__ import annotations

import argparse
import asyncio
from typing import Optional
from app.tokens import _exchange_code_for_token, _calc_expires_at, upsert_token

def _mask(token: Optional[str]) -> str:
    if not token:
        return "<none>"
    if len(token) <= 12:
        return token
    return f"{token[:6]}...{token[-6:]}"

async def run(account_id: str, code: str) -> int:
    try:
        tk = await _exchange_code_for_token(code)
        row = {
            "account_id": account_id,
            "access_token": tk["access_token"],
            "refresh_token": tk["refresh_token"],
            "token_type": tk.get("token_type", "Bearer"),
            "scope": tk.get("scope"),
            "expires_at": _calc_expires_at(int(tk["expires_in"])),
        }
        saved = upsert_token(row)

        print("[OK] Token salvo no Supabase.")
        print(f"  account_id   : {account_id}")
        print(f"  access_token : {_mask(saved.get('access_token'))}")
        print(f"  refresh_token: {_mask(saved.get('refresh_token'))}")
        print(f"  token_type   : {saved.get('token_type', 'Bearer')}")
        print(f"  scope        : {saved.get('scope')}")
        print(f"  expires_at   : {saved.get('expires_at')}")
        return 0
    except Exception as e:
        print("[ERRO] Falha ao trocar o code por token ou salvar no Supabase.")
        print("Detalhes:", repr(e))
        return 2

def main() -> None:
    parser = argparse.ArgumentParser(description="Troca authorization_code por tokens e salva no Supabase.")
    parser.add_argument("code", help="Authorization code retornado no callback OAuth")
    parser.add_argument("--account-id", default="default", help="Identificador lógico da conta (default)")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.account_id, args.code)))

if __name__ == "__main__":
    main()
