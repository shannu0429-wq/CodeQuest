create database codequest_db;

use codequest_db;

create table users(
id int auto_increment primary key,
username varchar(50) unique not null,
password varchar(255) not null,
role enum('user', 'admin') default 'user',
current_streak int default 0,
longest_streak int default 0,
last_quiz_date date null
);
desc users;

INSERT INTO users
(username, password, role)
VALUES
('shanmukha', 'test123', 'user');

SELECT * FROM users;




create table quizzes(
id int auto_increment primary key,
title varchar(100) not null,
description varchar(255),
created_at timestamp default current_timestamp
);



create table questions(
id int auto_increment primary key,
quiz_id int not null,
question text not null,
code text null,

option_a varchar(255) not null,
option_b varchar(255) not null,
option_c varchar(255) not null,
option_d varchar(255) not null,

correct_answer char(1) not null,

foreign key(quiz_id) references quizzes(id) on delete cascade
);


show tables;


insert INTO quizzes (title, description)
VALUES (
    'Python Basics',
    'Test your basic Python knowledge'
);

select * from quizzes;


INSERT INTO questions
(
    quiz_id,
    question,
    code,
    option_a,
    option_b,
    option_c,
    option_d,
    correct_answer
)
VALUES
(
    1,
    'Which keyword is used to define a function in Python?',
    NULL,
    'function',
    'def',
    'fun',
    'define',
    'B'
);


INSERT INTO questions
(
    quiz_id,
    question,
    code,
    option_a,
    option_b,
    option_c,
    option_d,
    correct_answer
)
VALUES
(
    1,
    'What will be the output of this code?',
    'x = 10\n y = 20\n print(x + y)',
    '10',
    '20',
    '30',
    '40',
    'C'
);


select * from questions;



create table attempts (
    id int auto_increment primary key,

    user_id int not null,
    quiz_id int not null,

    questions_attempted int default 0,
    correct_answers int default 0,
    wrong_answers int default 0,
    unanswered int default 0,

    quiz_score int default 0,
    streak_bonus int default 0,
    final_score int default 0,

    attempted_at timestamp default current_timestamp,

    foreign key (user_id)
        references users(id)
        on delete cascade,

    foreign key (quiz_id)
        references quizzes(id)
        on delete cascade,

    unique (user_id, quiz_id)
);

show tables;


insert into users
(username, password, role)
values
('admin', 'admin123', 'admin');
select * from users;


