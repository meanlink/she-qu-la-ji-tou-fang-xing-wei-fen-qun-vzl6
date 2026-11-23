CREATE TABLE IF NOT EXISTS observation_conditions (
    window_id INT PRIMARY KEY,
    condition_type ENUM('rain','access','signage','staffing') NOT NULL,
    state ENUM('pending','verified','dismissed') NOT NULL DEFAULT 'pending',
    note VARCHAR(240) NOT NULL,
    reported_by VARCHAR(40) NOT NULL,
    reported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decision_note VARCHAR(240),
    decided_by VARCHAR(40),
    decided_at TIMESTAMP NULL,
    FOREIGN KEY (window_id) REFERENCES sampling_windows(id),
    FOREIGN KEY (reported_by) REFERENCES staff(username),
    FOREIGN KEY (decided_by) REFERENCES staff(username)
) CHARACTER SET utf8mb4;
