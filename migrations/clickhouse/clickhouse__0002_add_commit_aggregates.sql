-- upgrade

ALTER TABLE commits ADD COLUMN IF NOT EXISTS is_merge Bool DEFAULT false

-- rollback

ALTER TABLE commits DROP COLUMN is_merge
