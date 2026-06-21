DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'auth' AND table_name = 'users'
  ) THEN
    DROP TABLE auth.users CASCADE;
  END IF;
END $$;

DROP FUNCTION IF EXISTS public.handle_new_user();

