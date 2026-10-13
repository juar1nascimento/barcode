-- Serialize creation/verification of Drive folders per patrimonio across worker instances.
-- Lease acquisition is a short database transaction; the lease remains durable across RPC calls.
create table if not exists public.gti_drive_folder_leases (
  patrimonio_id bigint primary key,
  lease_token uuid not null,
  lease_until timestamptz not null,
  updated_at timestamptz not null default clock_timestamp()
);

alter table public.gti_drive_folder_leases enable row level security;
revoke all on table public.gti_drive_folder_leases from public, anon, authenticated;
grant select, insert, update, delete on table public.gti_drive_folder_leases to service_role;

create or replace function public.gti_acquire_drive_folder_lease(
  p_patrimonio_id bigint,
  p_lease_token uuid,
  p_lease_seconds integer default 120
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_acquired boolean := false;
begin
  if p_patrimonio_id is null or p_patrimonio_id <= 0 then
    raise exception 'invalid_patrimonio_id';
  end if;
  if p_lease_token is null then
    raise exception 'invalid_lease_token';
  end if;
  if p_lease_seconds is null or p_lease_seconds < 30 or p_lease_seconds > 300 then
    raise exception 'invalid_lease_seconds';
  end if;

  insert into public.gti_drive_folder_leases
    (patrimonio_id, lease_token, lease_until, updated_at)
  values
    (p_patrimonio_id, p_lease_token,
     clock_timestamp() + make_interval(secs => p_lease_seconds),
     clock_timestamp())
  on conflict (patrimonio_id) do update
    set lease_token = excluded.lease_token,
        lease_until = excluded.lease_until,
        updated_at = clock_timestamp()
    where public.gti_drive_folder_leases.lease_until <= clock_timestamp()
  returning true into v_acquired;

  return coalesce(v_acquired, false);
end;
$$;

create or replace function public.gti_release_drive_folder_lease(
  p_patrimonio_id bigint,
  p_lease_token uuid
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from public.gti_drive_folder_leases
   where patrimonio_id = p_patrimonio_id
     and lease_token = p_lease_token;
  return found;
end;
$$;

revoke all on function public.gti_acquire_drive_folder_lease(bigint, uuid, integer) from public, anon, authenticated;
revoke all on function public.gti_release_drive_folder_lease(bigint, uuid) from public, anon, authenticated;
grant execute on function public.gti_acquire_drive_folder_lease(bigint, uuid, integer) to service_role;
grant execute on function public.gti_release_drive_folder_lease(bigint, uuid) to service_role;
