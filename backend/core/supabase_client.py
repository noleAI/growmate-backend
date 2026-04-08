from supabase import create_client, Client
from core.config import get_settings

settings = get_settings()

def get_supabase_client() -> Client:
    # Initialize the client. In a real environment, this would handle 
    # connection pooling or instantiation carefully.
    return create_client(settings.supabase_url, settings.supabase_key)
