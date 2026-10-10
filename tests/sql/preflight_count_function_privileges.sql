-- GTI SESA: read-only preflight for the inventory-count function.
-- Run against the intended non-production database using the same connection
-- role/configuration as the application. This script performs no writes and
-- never reads or prints connection strings, passwords, or secrets.

SELECT
  current_database() AS database_name,
  current_user AS effective_role,
  session_user AS login_role,
  to_regprocedure(
    'public.registrar_contagem_patrimonio(text,text,bigint,text)'
  ) IS NOT NULL AS function_exists,
  CASE
    WHEN to_regprocedure(
      'public.registrar_contagem_patrimonio(text,text,bigint,text)'
    ) IS NULL THEN false
    ELSE has_function_privilege(
      current_user,
      'public.registrar_contagem_patrimonio(text,text,bigint,text)',
      'EXECUTE'
    )
  END AS effective_role_can_execute;

-- Optional expected-role checks, without assuming those roles exist on every
-- PostgreSQL installation.
SELECT
  r.rolname AS role_name,
  has_function_privilege(
    r.rolname,
    'public.registrar_contagem_patrimonio(text,text,bigint,text)',
    'EXECUTE'
  ) AS can_execute
FROM pg_roles AS r
WHERE r.rolname IN ('anon', 'authenticated', 'service_role')
ORDER BY r.rolname;

-- Expected for the application connection: function_exists=true and
-- effective_role_can_execute=true. Review the effective_role with the
-- deployment configuration owner before changing any grants.
