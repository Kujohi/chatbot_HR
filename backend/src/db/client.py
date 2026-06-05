
import os
from supabase import create_client, Client
from supabase.client import ClientOptions
from dotenv import load_dotenv
load_dotenv()

def get_supabase():
    supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SECRET_ROLE_KEY") or os.environ.get("SUPABASE_PUBLISHABLE_KEY"),
)
    return supabase