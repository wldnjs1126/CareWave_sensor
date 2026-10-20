-- Apply manually on a TEST/NCP database before sending any batch_id values.
-- This creates only a new receipt table; existing sensor_raw rows are untouched.
-- Required: MySQL InnoDB for atomic receipt + sensor_raw transaction.
CREATE TABLE IF NOT EXISTS sensor_batch_receipt (
  batch_id VARCHAR(96) NOT NULL PRIMARY KEY,
  payload_sha256 CHAR(64) NOT NULL,
  sensor_id VARCHAR(64) NOT NULL,
  subject_id VARCHAR(64) NULL,
  first_frame_id BIGINT NULL,
  last_frame_id BIGINT NULL,
  window_start DATETIME NOT NULL,
  window_end DATETIME NOT NULL,
  sample_count INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Verify both tables use InnoDB before relying on atomicity:
SHOW TABLE STATUS WHERE Name IN ('sensor_raw','sensor_batch_receipt');
