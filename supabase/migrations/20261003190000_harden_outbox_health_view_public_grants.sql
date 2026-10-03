-- Keep operational outbox health internal.
-- The synchronization workers use privileged database access and do not need
-- the health view exposed through the public Data API roles.
revoke all on table public.patrimonios_sheets_outbox_health from anon, authenticated;
revoke all on table public.patrimonios_sheets_outbox_health from public;
