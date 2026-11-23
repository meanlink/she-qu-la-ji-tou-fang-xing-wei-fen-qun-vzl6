CREATE TABLE IF NOT EXISTS retest_appointments (
    task_id INT PRIMARY KEY,
    first_day DATE NOT NULL,
    second_day DATE NOT NULL,
    planned_by VARCHAR(40) NOT NULL,
    note VARCHAR(240) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (first_day < second_day),
    FOREIGN KEY (task_id) REFERENCES outreach_tasks(id),
    FOREIGN KEY (planned_by) REFERENCES staff(username)
) CHARACTER SET utf8mb4;
