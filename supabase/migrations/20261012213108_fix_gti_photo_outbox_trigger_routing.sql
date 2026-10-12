CREATE OR REPLACE FUNCTION public.gti_enqueue_foto_outboxes()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.drive_file_id IS NOT NULL AND btrim(NEW.drive_file_id) <> ''
       AND NEW.drive_web_url IS NOT NULL AND btrim(NEW.drive_web_url) <> '' THEN
      INSERT INTO public.patrimonio_fotos_sheets_outbox
        (patrimonio_id, foto_id, evento, status, tentativas,
         proxima_tentativa_em, processando_em, sincronizado_em,
         ultimo_erro, atualizado_em)
      VALUES
        (NEW.patrimonio_id, NEW.id, 'upsert', 'pending', 0,
         now(), NULL, NULL, NULL, now())
      ON CONFLICT (foto_id, evento) WHERE foto_id IS NOT NULL DO UPDATE
        SET patrimonio_id = EXCLUDED.patrimonio_id,
            status = 'pending', proxima_tentativa_em = now(),
            processando_em = NULL, sincronizado_em = NULL,
            ultimo_erro = NULL, atualizado_em = now();
    ELSE
      INSERT INTO public.patrimonio_fotos_drive_outbox
        (patrimonio_id, foto_id, evento, status, tentativas,
         proxima_tentativa_em, processando_em, sincronizado_em,
         ultimo_erro, atualizado_em)
      VALUES
        (NEW.patrimonio_id, NEW.id, 'upsert', 'pending', 0,
         now(), NULL, NULL, NULL, now())
      ON CONFLICT (foto_id, evento) DO UPDATE
        SET patrimonio_id = EXCLUDED.patrimonio_id,
            status = 'pending', proxima_tentativa_em = now(),
            processando_em = NULL, sincronizado_em = NULL,
            ultimo_erro = NULL, atualizado_em = now();
    END IF;
  ELSIF NEW.patrimonio_id IS DISTINCT FROM OLD.patrimonio_id
     OR NEW.storage_bucket IS DISTINCT FROM OLD.storage_bucket
     OR NEW.storage_path IS DISTINCT FROM OLD.storage_path
     OR NEW.arquivo_nome IS DISTINCT FROM OLD.arquivo_nome
     OR NEW.mime_type IS DISTINCT FROM OLD.mime_type
     OR NEW.tamanho_bytes IS DISTINCT FROM OLD.tamanho_bytes
     OR NEW.sha256 IS DISTINCT FROM OLD.sha256 THEN
    INSERT INTO public.patrimonio_fotos_drive_outbox
      (patrimonio_id, foto_id, evento, status, tentativas,
       proxima_tentativa_em, processando_em, sincronizado_em,
       ultimo_erro, atualizado_em)
    VALUES
      (NEW.patrimonio_id, NEW.id, 'upsert', 'pending', 0,
       now(), NULL, NULL, NULL, now())
    ON CONFLICT (foto_id, evento) DO UPDATE
      SET patrimonio_id = EXCLUDED.patrimonio_id,
          status = 'pending', proxima_tentativa_em = now(),
          processando_em = NULL, sincronizado_em = NULL,
          ultimo_erro = NULL, atualizado_em = now();
  ELSIF NEW.drive_file_id IS DISTINCT FROM OLD.drive_file_id
     OR NEW.drive_web_url IS DISTINCT FROM OLD.drive_web_url
     OR NEW.drive_file_name IS DISTINCT FROM OLD.drive_file_name THEN
    IF NEW.drive_file_id IS NOT NULL AND btrim(NEW.drive_file_id) <> ''
       AND NEW.drive_web_url IS NOT NULL AND btrim(NEW.drive_web_url) <> '' THEN
      INSERT INTO public.patrimonio_fotos_sheets_outbox
        (patrimonio_id, foto_id, evento, status, tentativas,
         proxima_tentativa_em, processando_em, sincronizado_em,
         ultimo_erro, atualizado_em)
      VALUES
        (NEW.patrimonio_id, NEW.id, 'upsert', 'pending', 0,
         now(), NULL, NULL, NULL, now())
      ON CONFLICT (foto_id, evento) WHERE foto_id IS NOT NULL DO UPDATE
        SET patrimonio_id = EXCLUDED.patrimonio_id,
            status = 'pending', proxima_tentativa_em = now(),
            processando_em = NULL, sincronizado_em = NULL,
            ultimo_erro = NULL, atualizado_em = now();
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
