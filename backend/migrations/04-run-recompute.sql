-- Recomputable runs: running state, attempt generation, worker lease and merge checkpoint.
-- Every statement is idempotent so startup migration can replay the file on existing volumes.
ALTER TABLE behavior_runs MODIFY COLUMN state
  ENUM('queued','running','paused','review','confirmed','failed') NOT NULL;

SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'behavior_runs' AND COLUMN_NAME = 'attempt');
SET @sql := IF(@col = 0,
  'ALTER TABLE behavior_runs ADD COLUMN attempt INT NOT NULL DEFAULT 1 AFTER state', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'behavior_runs' AND COLUMN_NAME = 'lease_owner');
SET @sql := IF(@col = 0,
  'ALTER TABLE behavior_runs ADD COLUMN lease_owner VARCHAR(64) AFTER attempt', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'behavior_runs' AND COLUMN_NAME = 'lease_until');
SET @sql := IF(@col = 0,
  'ALTER TABLE behavior_runs ADD COLUMN lease_until TIMESTAMP NULL AFTER lease_owner', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'behavior_runs' AND COLUMN_NAME = 'checkpoint');
SET @sql := IF(@col = 0,
  'ALTER TABLE behavior_runs ADD COLUMN checkpoint JSON AFTER lease_until', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col := (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'behavior_runs' AND COLUMN_NAME = 'started_at');
SET @sql := IF(@col = 0,
  'ALTER TABLE behavior_runs ADD COLUMN started_at TIMESTAMP NULL AFTER checkpoint', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
