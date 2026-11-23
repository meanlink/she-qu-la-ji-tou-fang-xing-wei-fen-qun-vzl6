SET NAMES utf8mb4;
CREATE TABLE field_register (id INT PRIMARY KEY);
INSERT INTO field_register VALUES (1);
CREATE TABLE staff (
    username VARCHAR(40) PRIMARY KEY,
    display_name VARCHAR(64) NOT NULL,
    role ENUM('analyst','admin','viewer') NOT NULL,
    password_hash VARCHAR(180) NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE disposal_points (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(16) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    sector VARCHAR(40) NOT NULL,
    location VARCHAR(160) NOT NULL,
    revision INT NOT NULL DEFAULT 1,
    sample_from DATE,
    pending_location VARCHAR(160),
    migration_note VARCHAR(240),
    CHECK (revision >= 1)
) CHARACTER SET utf8mb4;
CREATE TABLE behavior_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    from_day DATE NOT NULL,
    through_day DATE NOT NULL,
    requested_clusters INT NOT NULL,
    state ENUM('queued','running','paused','review','confirmed','failed') NOT NULL,
    attempt INT NOT NULL DEFAULT 1,
    lease_owner VARCHAR(64),
    lease_until TIMESTAMP NULL,
    checkpoint JSON,
    started_at TIMESTAMP NULL,
    reasons JSON NOT NULL,
    input_snapshot JSON NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    result JSON,
    requested_by VARCHAR(40) NOT NULL,
    reviewed_by VARCHAR(40),
    review_note VARCHAR(240),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (requested_by) REFERENCES staff(username),
    FOREIGN KEY (reviewed_by) REFERENCES staff(username),
    CHECK (requested_clusters BETWEEN 2 AND 4),
    CHECK (from_day <= through_day),
    INDEX (state,id)
) CHARACTER SET utf8mb4;
CREATE TABLE outreach_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id INT NOT NULL,
    point_id INT NOT NULL,
    point_revision INT NOT NULL,
    cohort INT NOT NULL,
    goal ENUM('accuracy','overflow') NOT NULL,
    focus_slot ENUM('morning','midday','evening') NOT NULL,
    baseline JSON NOT NULL,
    state ENUM('assigned','retesting','improved','followup','obsolete') NOT NULL DEFAULT 'assigned',
    delivered_day DATE,
    delivery_note VARCHAR(240),
    result JSON,
    review_note VARCHAR(240),
    UNIQUE (run_id,point_id),
    FOREIGN KEY (run_id) REFERENCES behavior_runs(id),
    FOREIGN KEY (point_id) REFERENCES disposal_points(id)
) CHARACTER SET utf8mb4;
CREATE TABLE sampling_windows (
    id INT AUTO_INCREMENT PRIMARY KEY,
    point_id INT NOT NULL,
    point_revision INT NOT NULL,
    sample_day DATE NOT NULL,
    slot ENUM('morning','midday','evening') NOT NULL,
    total INT NOT NULL,
    correct INT NOT NULL,
    overflow INT NOT NULL,
    task_id INT,
    entered_by VARCHAR(40) NOT NULL,
    UNIQUE (point_id,point_revision,sample_day,slot),
    FOREIGN KEY (point_id) REFERENCES disposal_points(id),
    FOREIGN KEY (task_id) REFERENCES outreach_tasks(id),
    FOREIGN KEY (entered_by) REFERENCES staff(username),
    CHECK (total BETWEEN 5 AND 1000),
    CHECK (correct BETWEEN 0 AND total),
    CHECK (overflow BETWEEN 0 AND total)
) CHARACTER SET utf8mb4;
CREATE TABLE field_audit (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor VARCHAR(40) NOT NULL,
    event VARCHAR(56) NOT NULL,
    object_id INT NOT NULL,
    facts JSON NOT NULL,
    happened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4;
