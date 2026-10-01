-- GTI-SESA: trigger de validação é interno ao PostgreSQL.
-- A função não é uma API/RPC para clientes anon/authenticated.
REVOKE EXECUTE ON FUNCTION public.validar_movimentacao_patrimonio() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.validar_movimentacao_patrimonio() TO service_role;
GRANT EXECUTE ON FUNCTION public.validar_movimentacao_patrimonio() TO postgres;
