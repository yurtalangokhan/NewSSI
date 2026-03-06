-- ============================================================
-- Fix 1: Patch existing jobs with Gi/Mi/Ki values
-- ============================================================
UPDATE jobs
SET config = regexp_replace(
    regexp_replace(
        regexp_replace(config::text, '([0-9]+)Gi"', '\1g"', 'g'),
        '([0-9]+)Mi"', '\1m"', 'g'),
    '([0-9]+)Ki"', '\1k"', 'g')::jsonb
WHERE config::text ~ '([0-9]+)(Gi|Mi|Ki)"';

-- ============================================================
-- Fix 2: Trigger on jobs table to auto-convert on INSERT/UPDATE
-- ============================================================
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

    -- Only do work if there are K8s suffixes
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

-- ============================================================
-- Verify
-- ============================================================
SELECT id, 
  CASE WHEN config::text ~ '(Gi|Mi|Ki)"' THEN 'STILL HAS K8S' ELSE 'OK' END as status,
  substring(config::text from '"memory_limit"\s*:\s*"[^"]*"') as sample
FROM jobs
ORDER BY id DESC
LIMIT 5;
