from src.db.client import get_supabase

supabase = get_supabase()

response = supabase.auth.sign_in_with_password({
    "email": "admin@gmail.com",
    "password": "admin"
})

print(response.session.access_token)