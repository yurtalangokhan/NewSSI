#!/bin/bash
set -e

echo "==> Creating Airbyte databases and role..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create airbyte role with CREATEDB so Temporal can manage its own DBs
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'airbyte') THEN
            CREATE ROLE airbyte WITH LOGIN CREATEDB PASSWORD '${AIRBYTE_DB_PASSWORD:-airbyte_password}';
        ELSE
            ALTER ROLE airbyte WITH CREATEDB;
        END IF;
    END
    \$\$;

    GRANT airbyte TO $POSTGRES_USER;

    -- Airbyte config/jobs database
    SELECT 'CREATE DATABASE airbyte OWNER airbyte'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airbyte')
    \gexec

    -- Temporal workflow database
    SELECT 'CREATE DATABASE temporal OWNER airbyte'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal')
    \gexec

    -- Temporal visibility database
    SELECT 'CREATE DATABASE temporal_visibility OWNER airbyte'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal_visibility')
    \gexec

    REVOKE airbyte FROM $POSTGRES_USER;
EOSQL

echo "==> Airbyte databases ready (airbyte, temporal, temporal_visibility)."

# ============================================================
# Trigger: auto-convert Kubernetes resource suffixes to Docker
# Bootloader writes 1Gi/2Gi (K8s format) but Docker needs 1g/2g
# This trigger fires on every INSERT/UPDATE to actor_definition
# ============================================================
echo "==> Installing K8s→Docker resource suffix trigger on airbyte DB..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "airbyte" <<-'EOTRIGGER'
    CREATE OR REPLACE FUNCTION fix_k8s_resource_suffixes()
    RETURNS TRIGGER AS $fn$
    DECLARE
        rr       jsonb;
        arr      jsonb;
        inner_rr jsonb;
        k        text;
        v        text;
        changed  boolean := false;
    BEGIN
        rr := NEW.resource_requirements;
        IF rr IS NULL THEN
            RETURN NEW;
        END IF;

        -- Walk through jobSpecific array
        arr := rr -> 'jobSpecific';
        IF arr IS NOT NULL AND jsonb_typeof(arr) = 'array' THEN
            FOR i IN 0 .. jsonb_array_length(arr) - 1 LOOP
                inner_rr := arr -> i -> 'resourceRequirements';
                IF inner_rr IS NOT NULL THEN
                    FOR k IN SELECT jsonb_object_keys(inner_rr) LOOP
                        v := inner_rr ->> k;
                        IF v ~ '[0-9]+Gi$' THEN
                            v := regexp_replace(v, 'Gi$', 'g');
                            changed := true;
                        ELSIF v ~ '[0-9]+Mi$' THEN
                            v := regexp_replace(v, 'Mi$', 'm');
                            changed := true;
                        ELSIF v ~ '[0-9]+Ki$' THEN
                            v := regexp_replace(v, 'Ki$', 'k');
                            changed := true;
                        END IF;
                        IF changed THEN
                            inner_rr := jsonb_set(inner_rr, ARRAY[k], to_jsonb(v));
                        END IF;
                    END LOOP;
                    IF changed THEN
                        arr := jsonb_set(arr, ARRAY[i::text, 'resourceRequirements'], inner_rr);
                    END IF;
                END IF;
            END LOOP;
            IF changed THEN
                rr := jsonb_set(rr, ARRAY['jobSpecific'], arr);
            END IF;
        END IF;

        -- Also handle top-level resourceRequirements keys
        FOR k IN SELECT jsonb_object_keys(rr) LOOP
            IF k NOT IN ('jobSpecific') AND jsonb_typeof(rr -> k) = 'string' THEN
                v := rr ->> k;
                IF v ~ '[0-9]+Gi$' THEN
                    rr := jsonb_set(rr, ARRAY[k], to_jsonb(regexp_replace(v, 'Gi$', 'g')));
                    changed := true;
                ELSIF v ~ '[0-9]+Mi$' THEN
                    rr := jsonb_set(rr, ARRAY[k], to_jsonb(regexp_replace(v, 'Mi$', 'm')));
                    changed := true;
                ELSIF v ~ '[0-9]+Ki$' THEN
                    rr := jsonb_set(rr, ARRAY[k], to_jsonb(regexp_replace(v, 'Ki$', 'k')));
                    changed := true;
                END IF;
            END IF;
        END LOOP;

        NEW.resource_requirements := rr;
        RETURN NEW;
    END;
    $fn$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_fix_k8s_resources ON actor_definition;
    CREATE TRIGGER trg_fix_k8s_resources
        BEFORE INSERT OR UPDATE ON actor_definition
        FOR EACH ROW
        EXECUTE FUNCTION fix_k8s_resource_suffixes();
EOTRIGGER

# ============================================================
# Trigger on jobs table: Airbyte server merges resource values
# into jobs.config JSON at job creation time. This trigger
# catches any Gi/Mi/Ki suffixes in the serialized JSON.
# ============================================================
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "airbyte" <<-'EOJOBS'
    CREATE OR REPLACE FUNCTION fix_k8s_resource_suffixes_jobs()
    RETURNS TRIGGER AS $fn$
    DECLARE
        cfg_text text;
        new_text text;
    BEGIN
        IF NEW.config IS NULL THEN
            RETURN NEW;
        END IF;

        cfg_text := NEW.config::text;

        IF cfg_text ~ '([0-9]+)(Gi|Mi|Ki)"' THEN
            new_text := regexp_replace(cfg_text, '([0-9]+)Gi"', '\1g"', 'g');
            new_text := regexp_replace(new_text, '([0-9]+)Mi"', '\1m"', 'g');
            new_text := regexp_replace(new_text, '([0-9]+)Ki"', '\1k"', 'g');
            NEW.config := new_text::jsonb;
        END IF;

        RETURN NEW;
    END;
    $fn$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_fix_k8s_resources_jobs ON jobs;
    CREATE TRIGGER trg_fix_k8s_resources_jobs
        BEFORE INSERT OR UPDATE ON jobs
        FOR EACH ROW
        EXECUTE FUNCTION fix_k8s_resource_suffixes_jobs();
EOJOBS

echo "==> K8s resource suffix triggers installed (actor_definition + jobs)."