-- Supabase (PostgreSQL) Database Setup Script for CodeQuest

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(10) CHECK (role IN ('user', 'admin')) DEFAULT 'user',
    current_streak INT DEFAULT 0,
    longest_streak INT DEFAULT 0,
    last_quiz_date DATE NULL
);

-- Quizzes Table
CREATE TABLE IF NOT EXISTS quizzes (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Questions Table
CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    quiz_id INT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    code TEXT NULL,
    option_a VARCHAR(255) NOT NULL,
    option_b VARCHAR(255) NOT NULL,
    option_c VARCHAR(255) NOT NULL,
    option_d VARCHAR(255) NOT NULL,
    correct_answer CHAR(1) NOT NULL CHECK (correct_answer IN ('A', 'B', 'C', 'D')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    solution_text TEXT NULL,
    solution_image VARCHAR(255) NULL
);

-- Attempts Table
CREATE TABLE IF NOT EXISTS attempts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    quiz_id INT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    questions_attempted INT DEFAULT 0,
    correct_answers INT DEFAULT 0,
    wrong_answers INT DEFAULT 0,
    unanswered INT DEFAULT 0,
    quiz_score INT DEFAULT 0,
    streak_bonus INT DEFAULT 0,
    final_score INT DEFAULT 0,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, quiz_id)
);

-- User Answers Table (stores individual choices per question)
CREATE TABLE IF NOT EXISTS user_answers (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    quiz_id INT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_id INT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    user_answer CHAR(1) NOT NULL,
    is_correct BOOLEAN NOT NULL,
    UNIQUE (user_id, question_id)
);


-- Insert Default Seed Data (Check if users exist before inserting)
INSERT INTO users (username, password, role)
VALUES 
    ('shanmukha', 'test123', 'user'),
    ('admin', 'admin123', 'admin')
ON CONFLICT (username) DO NOTHING;

INSERT INTO quizzes (id, title, description)
VALUES (1, 'Python Basics', 'Test your basic Python knowledge')
ON CONFLICT (id) DO NOTHING;

-- Reset serial sequence after explicit ID insert
SELECT setval(pg_get_serial_sequence('quizzes', 'id'), COALESCE(max(id), 1)) FROM quizzes;

INSERT INTO questions (quiz_id, question, code, option_a, option_b, option_c, option_d, correct_answer)
VALUES
    (1, 'Which keyword is used to define a function in Python?', NULL, 'function', 'def', 'fun', 'define', 'B'),
    (1, 'What will be the output of this code?', 'x = 10' || chr(10) || 'y = 20' || chr(10) || 'print(x + y)', '10', '20', '30', '40', 'C')
ON CONFLICT DO NOTHING;
