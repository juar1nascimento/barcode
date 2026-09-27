SET statement_timeout = 0;

SET lock_timeout = 0;

SET idle_in_transaction_session_timeout = 0;

SET client_encoding = 'UTF8';

SET standard_conforming_strings = on;

SELECT pg_catalog.set_config('search_path', '', false);

SET check_function_bodies = false;

SET xmloption = content;

SET client_min_messages = warning;

SET row_security = off;

COMMENT ON SCHEMA "public" IS 'standard public schema';

CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";

CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";

CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";

SET default_tablespace = '';

SET default_table_access_method = "heap";

CREATE TABLE IF NOT EXISTS "public"."patrimonio_fotos" (
    "id" bigint NOT NULL,
    "patrimonio_id" bigint NOT NULL,
    "ordem" integer NOT NULL,
    "storage_bucket" character varying(100) DEFAULT 'patrimonio-fotos'::character varying NOT NULL,
    "storage_path" character varying(500) NOT NULL,
    "arquivo_nome" character varying(255) NOT NULL,
    "mime_type" character varying(100) NOT NULL,
    "tamanho_bytes" integer NOT NULL,
    "largura" integer,
    "altura" integer,
    "sha256" character(64) NOT NULL,
    "criado_em" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_patrimonio_fotos_dimensoes" CHECK (((("largura" IS NULL) AND ("altura" IS NULL)) OR (("largura" > 0) AND ("altura" > 0)))),
    CONSTRAINT "ck_patrimonio_fotos_ordem" CHECK (("ordem" > 0)),
    CONSTRAINT "ck_patrimonio_fotos_sha256" CHECK (("sha256" ~ '^[0-9a-fA-F]{64}$'::"text")),
    CONSTRAINT "ck_patrimonio_fotos_tamanho" CHECK (("tamanho_bytes" > 0))
);

ALTER TABLE "public"."patrimonio_fotos" OWNER TO "postgres";

CREATE SEQUENCE IF NOT EXISTS "public"."patrimonio_fotos_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "public"."patrimonio_fotos_id_seq" OWNER TO "postgres";

ALTER SEQUENCE "public"."patrimonio_fotos_id_seq" OWNED BY "public"."patrimonio_fotos"."id";

CREATE TABLE IF NOT EXISTS "public"."patrimonios" (
    "id" bigint NOT NULL,
    "unidade_id" bigint NOT NULL,
    "setor_id" bigint NOT NULL,
    "tipo" character varying(50) NOT NULL,
    "numero_patrimonio" character varying(150) NOT NULL,
    "codigo_barras" character varying(150),
    "fabricante" character varying(150),
    "data_cadastro" timestamp with time zone DEFAULT "now"() NOT NULL,
    "atualizado_em" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "patrimonios_tipo_check" CHECK ((("tipo")::"text" = ANY ((ARRAY['CPU'::character varying, 'Monitores'::character varying, 'Teclado'::character varying, 'Mouse'::character varying, 'Imprenssoras'::character varying, 'Outros Dispositivos'::character varying])::"text"[])))
);

ALTER TABLE "public"."patrimonios" OWNER TO "postgres";

CREATE SEQUENCE IF NOT EXISTS "public"."patrimonios_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "public"."patrimonios_id_seq" OWNER TO "postgres";

ALTER SEQUENCE "public"."patrimonios_id_seq" OWNED BY "public"."patrimonios"."id";

CREATE TABLE IF NOT EXISTS "public"."setores" (
    "id" bigint NOT NULL,
    "unidade_id" bigint NOT NULL,
    "nome" character varying(120) NOT NULL,
    "numero_consultorio" integer,
    "especialidade" character varying(150),
    "ativo" boolean DEFAULT true NOT NULL,
    "criado_em" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "ck_setor_consultorio_dados" CHECK ((((("nome")::"text" = 'Consultório'::"text") AND ("numero_consultorio" IS NOT NULL) AND ("especialidade" IS NOT NULL)) OR ((("nome")::"text" <> 'Consultório'::"text") AND ("numero_consultorio" IS NULL) AND ("especialidade" IS NULL)))),
    CONSTRAINT "ck_setor_consultorio_numero" CHECK ((("numero_consultorio" IS NULL) OR ("numero_consultorio" > 0)))
);

ALTER TABLE "public"."setores" OWNER TO "postgres";

CREATE SEQUENCE IF NOT EXISTS "public"."setores_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "public"."setores_id_seq" OWNER TO "postgres";

ALTER SEQUENCE "public"."setores_id_seq" OWNED BY "public"."setores"."id";

CREATE TABLE IF NOT EXISTS "public"."unidades" (
    "id" bigint NOT NULL,
    "nome" character varying(150) NOT NULL,
    "tipo" character varying(10) NOT NULL,
    "ativo" boolean DEFAULT true NOT NULL,
    "criado_em" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "unidades_tipo_check" CHECK ((("tipo")::"text" = ANY ((ARRAY['UBS'::character varying, 'URS'::character varying, 'ALMOX'::character varying])::"text"[])))
);

ALTER TABLE "public"."unidades" OWNER TO "postgres";

CREATE SEQUENCE IF NOT EXISTS "public"."unidades_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "public"."unidades_id_seq" OWNER TO "postgres";

ALTER SEQUENCE "public"."unidades_id_seq" OWNED BY "public"."unidades"."id";

ALTER TABLE ONLY "public"."patrimonio_fotos" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."patrimonio_fotos_id_seq"'::"regclass");

ALTER TABLE ONLY "public"."patrimonios" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."patrimonios_id_seq"'::"regclass");

ALTER TABLE ONLY "public"."setores" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."setores_id_seq"'::"regclass");

ALTER TABLE ONLY "public"."unidades" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."unidades_id_seq"'::"regclass");

ALTER TABLE ONLY "public"."patrimonio_fotos"
    ADD CONSTRAINT "patrimonio_fotos_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."patrimonios"
    ADD CONSTRAINT "patrimonios_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."setores"
    ADD CONSTRAINT "setores_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."unidades"
    ADD CONSTRAINT "unidades_nome_key" UNIQUE ("nome");

ALTER TABLE ONLY "public"."unidades"
    ADD CONSTRAINT "unidades_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."patrimonios"
    ADD CONSTRAINT "uq_patrimonio_codigo_barras" UNIQUE ("codigo_barras");

ALTER TABLE ONLY "public"."patrimonio_fotos"
    ADD CONSTRAINT "uq_patrimonio_fotos_ordem" UNIQUE ("patrimonio_id", "ordem");

ALTER TABLE ONLY "public"."patrimonio_fotos"
    ADD CONSTRAINT "uq_patrimonio_fotos_storage_path" UNIQUE ("storage_bucket", "storage_path");

ALTER TABLE ONLY "public"."patrimonios"
    ADD CONSTRAINT "uq_patrimonio_numero" UNIQUE ("numero_patrimonio");

CREATE INDEX "idx_patrimonio_fotos_patrimonio" ON "public"."patrimonio_fotos" USING "btree" ("patrimonio_id");

CREATE INDEX "idx_patrimonio_fotos_sha256" ON "public"."patrimonio_fotos" USING "btree" ("sha256");

CREATE INDEX "idx_patrimonios_setor" ON "public"."patrimonios" USING "btree" ("setor_id");

CREATE INDEX "idx_patrimonios_tipo" ON "public"."patrimonios" USING "btree" ("tipo");

CREATE INDEX "idx_patrimonios_unidade" ON "public"."patrimonios" USING "btree" ("unidade_id");

CREATE INDEX "idx_setores_unidade" ON "public"."setores" USING "btree" ("unidade_id");

CREATE UNIQUE INDEX "uq_setor_consultorio" ON "public"."setores" USING "btree" ("unidade_id", "numero_consultorio", "especialidade") WHERE ((("nome")::"text" = 'Consultório'::"text") AND ("numero_consultorio" IS NOT NULL) AND ("especialidade" IS NOT NULL));

CREATE UNIQUE INDEX "uq_setor_normal" ON "public"."setores" USING "btree" ("unidade_id", "nome") WHERE ((("nome")::"text" <> 'Consultório'::"text") AND ("numero_consultorio" IS NULL) AND ("especialidade" IS NULL));

ALTER TABLE ONLY "public"."patrimonio_fotos"
    ADD CONSTRAINT "patrimonio_fotos_patrimonio_id_fkey" FOREIGN KEY ("patrimonio_id") REFERENCES "public"."patrimonios"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."patrimonios"
    ADD CONSTRAINT "patrimonios_setor_id_fkey" FOREIGN KEY ("setor_id") REFERENCES "public"."setores"("id") ON DELETE RESTRICT;

ALTER TABLE ONLY "public"."patrimonios"
    ADD CONSTRAINT "patrimonios_unidade_id_fkey" FOREIGN KEY ("unidade_id") REFERENCES "public"."unidades"("id") ON DELETE RESTRICT;

ALTER TABLE ONLY "public"."setores"
    ADD CONSTRAINT "setores_unidade_id_fkey" FOREIGN KEY ("unidade_id") REFERENCES "public"."unidades"("id") ON DELETE CASCADE;

ALTER TABLE "public"."patrimonio_fotos" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."patrimonios" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."setores" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."unidades" ENABLE ROW LEVEL SECURITY;

ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";

GRANT USAGE ON SCHEMA "public" TO "postgres";

GRANT USAGE ON SCHEMA "public" TO "anon";

GRANT USAGE ON SCHEMA "public" TO "authenticated";

GRANT USAGE ON SCHEMA "public" TO "service_role";

GRANT ALL ON TABLE "public"."patrimonio_fotos" TO "anon";

GRANT ALL ON TABLE "public"."patrimonio_fotos" TO "authenticated";

GRANT ALL ON TABLE "public"."patrimonio_fotos" TO "service_role";

GRANT ALL ON SEQUENCE "public"."patrimonio_fotos_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."patrimonio_fotos_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."patrimonio_fotos_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."patrimonios" TO "anon";

GRANT ALL ON TABLE "public"."patrimonios" TO "authenticated";

GRANT ALL ON TABLE "public"."patrimonios" TO "service_role";

GRANT ALL ON SEQUENCE "public"."patrimonios_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."patrimonios_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."patrimonios_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."setores" TO "anon";

GRANT ALL ON TABLE "public"."setores" TO "authenticated";

GRANT ALL ON TABLE "public"."setores" TO "service_role";

GRANT ALL ON SEQUENCE "public"."setores_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."setores_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."setores_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."unidades" TO "anon";

GRANT ALL ON TABLE "public"."unidades" TO "authenticated";

GRANT ALL ON TABLE "public"."unidades" TO "service_role";

GRANT ALL ON SEQUENCE "public"."unidades_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."unidades_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."unidades_id_seq" TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";

drop extension if exists "pg_net";

alter table "public"."patrimonios" drop constraint "patrimonios_tipo_check";

alter table "public"."unidades" drop constraint "unidades_tipo_check";

alter table "public"."patrimonios" add constraint "patrimonios_tipo_check" CHECK (((tipo)::text = ANY ((ARRAY['CPU'::character varying, 'Monitores'::character varying, 'Teclado'::character varying, 'Mouse'::character varying, 'Imprenssoras'::character varying, 'Outros Dispositivos'::character varying])::text[]))) not valid;

alter table "public"."patrimonios" validate constraint "patrimonios_tipo_check";

alter table "public"."unidades" add constraint "unidades_tipo_check" CHECK (((tipo)::text = ANY ((ARRAY['UBS'::character varying, 'URS'::character varying, 'ALMOX'::character varying])::text[]))) not valid;

alter table "public"."unidades" validate constraint "unidades_tipo_check";
