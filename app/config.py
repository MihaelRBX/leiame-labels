from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Ambiente
    app_env: str = "prod"

    # Melhor Envio
    me_base_url: str = "https://melhorenvio.com.br"
    me_client_id: str
    me_client_secret: str
    me_redirect_uri: str
    me_user_agent: str = "Integracao Melhor Envio - Leia-me (mihaelrbx@outlook.com)"

    # Supabase
    supabase_url: str
    supabase_service_role_key: str

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

settings = Settings()

