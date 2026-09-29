create or replace function public.validar_movimentacao_patrimonio()
returns trigger
language plpgsql
as $$
declare
  origem_unidade bigint;
  destino_unidade bigint;
begin
  if NEW.tipo not in ('ENTRADA','SAIDA','TRANSFERENCIA') then
    raise exception 'Tipo de movimentação inválido: %', NEW.tipo;
  end if;
  if NEW.tipo = 'TRANSFERENCIA' then
    if NEW.unidade_origem_id is null or NEW.setor_origem_id is null or NEW.unidade_destino_id is null or NEW.setor_destino_id is null then
      raise exception 'Transferência exige origem e destino completos.';
    end if;
  elsif NEW.tipo = 'ENTRADA' then
    if NEW.unidade_destino_id is null or NEW.setor_destino_id is null then
      raise exception 'Entrada exige unidade e setor de destino.';
    end if;
  elsif NEW.tipo = 'SAIDA' then
    if NEW.unidade_destino_id is not null or NEW.setor_destino_id is not null then
      raise exception 'Saída não pode possuir destino interno.';
    end if;
  end if;
  if (NEW.unidade_origem_id is null) <> (NEW.setor_origem_id is null) then
    raise exception 'Origem deve informar unidade e setor juntos.';
  end if;
  if (NEW.unidade_destino_id is null) <> (NEW.setor_destino_id is null) then
    raise exception 'Destino deve informar unidade e setor juntos.';
  end if;
  if NEW.setor_origem_id is not null then
    select unidade_id into origem_unidade from public.setores where id = NEW.setor_origem_id and coalesce(ativo, true);
    if origem_unidade is null then raise exception 'Setor de origem inválido ou inativo.'; end if;
    if origem_unidade <> NEW.unidade_origem_id then raise exception 'Setor de origem não pertence à unidade de origem.'; end if;
  end if;
  if NEW.setor_destino_id is not null then
    select unidade_id into destino_unidade from public.setores where id = NEW.setor_destino_id and coalesce(ativo, true);
    if destino_unidade is null then raise exception 'Setor de destino inválido ou inativo.'; end if;
    if destino_unidade <> NEW.unidade_destino_id then raise exception 'Setor de destino não pertence à unidade de destino.'; end if;
  end if;
  if NEW.tipo = 'TRANSFERENCIA' then
    if NEW.unidade_origem_id = NEW.unidade_destino_id and NEW.setor_origem_id = NEW.setor_destino_id then
      raise exception 'O patrimônio já está na localização de destino.';
    end if;
    if not exists (select 1 from public.patrimonios p where p.id = NEW.patrimonio_id and p.unidade_id = NEW.unidade_origem_id and p.setor_id = NEW.setor_origem_id) then
      raise exception 'A origem informada não corresponde à localização atual do patrimônio.';
    end if;
  end if;
  return NEW;
end;
$$;
alter function public.validar_movimentacao_patrimonio() set search_path = public, pg_catalog;
drop trigger if exists trg_validar_movimentacao_patrimonio on public.movimentacoes_patrimonio;
create trigger trg_validar_movimentacao_patrimonio before insert or update on public.movimentacoes_patrimonio for each row execute function public.validar_movimentacao_patrimonio();