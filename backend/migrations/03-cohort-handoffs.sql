CREATE TABLE IF NOT EXISTS cohort_handoffs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    anchor_task_id INT NOT NULL,
    tactic ENUM('replace_signs','guided_sorting','stagger_window','alternate_point') NOT NULL,
    due_day DATE NOT NULL,
    note VARCHAR(240) NOT NULL,
    condition_window_id INT,
    issued_by VARCHAR(40) NOT NULL,
    issued_day DATE NOT NULL,
    issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_by VARCHAR(40),
    closed_at TIMESTAMP NULL,
    close_note VARCHAR(240),
    FOREIGN KEY (anchor_task_id) REFERENCES outreach_tasks(id),
    FOREIGN KEY (condition_window_id) REFERENCES observation_conditions(window_id),
    FOREIGN KEY (issued_by) REFERENCES staff(username),
    FOREIGN KEY (closed_by) REFERENCES staff(username)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS cohort_handoff_members (
    handoff_id INT NOT NULL,
    task_id INT NOT NULL UNIQUE,
    outcome ENUM('implemented','relocated'),
    event_day DATE,
    note VARCHAR(240),
    recorded_by VARCHAR(40),
    recorded_at TIMESTAMP NULL,
    PRIMARY KEY (handoff_id,task_id),
    FOREIGN KEY (handoff_id) REFERENCES cohort_handoffs(id),
    FOREIGN KEY (task_id) REFERENCES outreach_tasks(id),
    FOREIGN KEY (recorded_by) REFERENCES staff(username)
) CHARACTER SET utf8mb4;
