import os
import threading
from supabase import create_client, Client

_SUPABASE: Client | None = None
_LOCK = threading.Lock()

def get_supabase() -> Client:
    global _SUPABASE
    if _SUPABASE is None:
        with _LOCK:
            if _SUPABASE is None:
                url = os.environ["SUPABASE_URL"]
                key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
                _SUPABASE = create_client(url, key)
    return _SUPABASE
