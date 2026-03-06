-- ============================================================
-- Trigger: auto-convert Kubernetes resource suffixes to Docker
-- Gi -> g, Mi -> m, Ki -> k
-- Runs on every INSERT/UPDATE to actor_definition
-- ============================================================

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

-- Create trigger
DROP TRIGGER IF EXISTS trg_fix_k8s_resources ON actor_definition;
CREATE TRIGGER trg_fix_k8s_resources
    BEFORE INSERT OR UPDATE ON actor_definition
    FOR EACH ROW
    EXECUTE FUNCTION fix_k8s_resource_suffixes();

-- Fix all existing rows (trigger fires on UPDATE)
UPDATE actor_definition
SET resource_requirements = resource_requirements
WHERE resource_requirements::text ~ '(Gi|Mi|Ki)"';
