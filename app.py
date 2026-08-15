from flask import Flask, render_template, request, session, redirect
import mysql.connector
from datetime import date, timedelta


app = Flask(__name__)

app.secret_key = "codequest_secret_key"

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="admin",
    database="codequest_db"
)

print("mysql connected successfully")


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
@app.route("/login", methods=["GET", "POST"])
def login():

    # When clicking Login from index.html
    if request.method == "GET":
        return render_template("login.html")

    # Login form submission
    username = request.form["username"]
    password = request.form["password"]

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE username = %s
        """,
        (username,)
    )

    user = cursor.fetchone()

    cursor.close()

    if user is None or user["password"] != password:

        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    if user["role"] == "admin":
        return redirect("/admin")

    return redirect("/dashboard")


@app.route("/dashboard")
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "user":
        return redirect("/admin")

    cursor = db.cursor(dictionary=True)

    # Get user details
    cursor.execute(
        """
        SELECT username,
               current_streak,
               longest_streak
        FROM users
        WHERE id = %s
        """,
        (session["user_id"],)
    )

    user = cursor.fetchone()

    # Get total score
    cursor.execute(
        """
        SELECT COALESCE(SUM(final_score), 0) AS total_score
        FROM attempts
        WHERE user_id = %s
        """,
        (session["user_id"],)
    )

    score_data = cursor.fetchone()

    total_score = score_data["total_score"]

    # Get all quizzes + user's attempt information
    cursor.execute(
        """
        SELECT
            q.id,
            q.title,
            q.description,

            a.final_score

        FROM quizzes q

        LEFT JOIN attempts a
            ON q.id = a.quiz_id
            AND a.user_id = %s

        ORDER BY q.id DESC
        """,
        (session["user_id"],)
    )

    quizzes = cursor.fetchall()

    cursor.close()

    # Add attempted status
    for quiz in quizzes:

        if quiz["final_score"] is not None:

            quiz["attempted"] = True
            quiz["score"] = quiz["final_score"]

        else:

            quiz["attempted"] = False
            quiz["score"] = 0

    return render_template(
        "dashboard.html",
        user=user,
        total_score=total_score,
        quizzes=quizzes
    )
    
@app.route("/admin")
@app.route("/admin")
def admin():

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "select * from quizzes order by id desc"
    )

    quizzes = cursor.fetchall()

    cursor.close()

    return render_template(
        "admin.html",
        quizzes=quizzes
    )


@app.route("/admin/add-quiz", methods=["POST"])
@app.route("/admin/add-quiz", methods=["POST"])
def add_quiz():

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    title = request.form["title"]
    description = request.form["description"]

    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO quizzes
        (title, description)
        VALUES (%s, %s)
        """,
        (title, description)
    )

    db.commit()

    cursor.close()

    return redirect("/admin")

@app.route("/admin/quiz/<int:quiz_id>")
@app.route("/admin/quiz/<int:quiz_id>")
def manage_questions(quiz_id):

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    cursor = db.cursor(dictionary=True)

    # get quiz
    cursor.execute(
        "select * from quizzes where id = %s",
        (quiz_id,)
    )

    quiz = cursor.fetchone()

    if not quiz:
        cursor.close()
        return "quiz not found"

    # get questions
    cursor.execute(
        """
        select * from questions
        where quiz_id = %s
        order by id
        """,
        (quiz_id,)
    )

    questions = cursor.fetchall()

    cursor.close()

    return render_template(
        "questions.html",
        quiz=quiz,
        questions=questions
    )
def add_question(quiz_id):

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    question = request.form["question"]
    code = request.form["code"]
    option_a = request.form["option_a"]
    option_b = request.form["option_b"]
    option_c = request.form["option_c"]
    option_d = request.form["option_d"]
    correct_answer = request.form["correct_answer"]

    cursor = db.cursor()

    cursor.execute(
        """
        insert into questions
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
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
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
    )

    db.commit()

    cursor.close()

    return redirect(f"/admin/quiz/{quiz_id}")

@app.route("/admin/question/<int:question_id>/edit", methods=["GET", "POST"])
def edit_question(question_id):

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    cursor = db.cursor(dictionary=True)

    # Get question
    cursor.execute(
        """
        SELECT *
        FROM questions
        WHERE id = %s
        """,
        (question_id,)
    )

    question = cursor.fetchone()

    if not question:
        cursor.close()
        return "Question not found"

    if request.method == "POST":

        question_text = request.form["question"]
        code = request.form["code"]

        option_a = request.form["option_a"]
        option_b = request.form["option_b"]
        option_c = request.form["option_c"]
        option_d = request.form["option_d"]

        correct_answer = request.form["correct_answer"]

        cursor.execute(
            """
            UPDATE questions
            SET question = %s,
                code = %s,
                option_a = %s,
                option_b = %s,
                option_c = %s,
                option_d = %s,
                correct_answer = %s
            WHERE id = %s
            """,
            (
                question_text,
                code,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_answer,
                question_id
            )
        )

        db.commit()

        quiz_id = question["quiz_id"]

        cursor.close()

        return redirect(f"/admin/quiz/{quiz_id}")

    cursor.close()

    return render_template(
        "edit_question.html",
        question=question
    )
    
    
@app.route("/admin/question/<int:question_id>/delete", methods=["POST"])
@app.route("/admin/question/<int:question_id>/delete", methods=["POST"])
def delete_question(question_id):

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT quiz_id
        FROM questions
        WHERE id = %s
        """,
        (question_id,)
    )

    question = cursor.fetchone()

    if not question:
        cursor.close()
        return "Question not found"

    quiz_id = question["quiz_id"]

    cursor.execute(
        "DELETE FROM questions WHERE id = %s",
        (question_id,)
    )

    db.commit()

    cursor.close()

    return redirect(f"/admin/quiz/{quiz_id}")


@app.route("/quiz/<int:quiz_id>")
def quiz(quiz_id):

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "user":
        return redirect("/admin")

    cursor = db.cursor(dictionary=True)

    # Check whether user already attempted this quiz
    cursor.execute(
        """
        SELECT *
        FROM attempts
        WHERE user_id = %s AND quiz_id = %s
        """,
        (session["user_id"], quiz_id)
    )

    attempt = cursor.fetchone()

    # Get quiz
    cursor.execute(
        """
        SELECT *
        FROM quizzes
        WHERE id = %s
        """,
        (quiz_id,)
    )

    quiz_data = cursor.fetchone()

    if not quiz_data:
        cursor.close()
        return "Quiz not found"

    # If already attempted
    if attempt:

        cursor.close()

        return render_template(
            "already_attempted.html",
            attempt=attempt,
            quiz=quiz_data
        )

    # Get questions
    cursor.execute(
        """
        SELECT *
        FROM questions
        WHERE quiz_id = %s
        ORDER BY id
        """,
        (quiz_id,)
    )

    questions = cursor.fetchall()

    cursor.close()

    return render_template(
        "quiz.html",
        quiz=quiz_data,
        questions=questions
    )
    
@app.route("/quiz/<int:quiz_id>/submit", methods=["POST"])
def submit_quiz(quiz_id):

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "user":
        return redirect("/admin")

    cursor = db.cursor(dictionary=True)

    # Check whether quiz exists
    cursor.execute(
        """
        SELECT *
        FROM quizzes
        WHERE id = %s
        """,
        (quiz_id,)
    )

    quiz_data = cursor.fetchone()

    if not quiz_data:
        cursor.close()
        return "Quiz not found"

    # Check whether user already attempted
    cursor.execute(
        """
        SELECT *
        FROM attempts
        WHERE user_id = %s AND quiz_id = %s
        """,
        (session["user_id"], quiz_id)
    )

    existing_attempt = cursor.fetchone()

    if existing_attempt:
        cursor.close()
        return "You have already attempted this quiz."

    # Get questions
    cursor.execute(
        """
        SELECT *
        FROM questions
        WHERE quiz_id = %s
        ORDER BY id
        """,
        (quiz_id,)
    )

    questions = cursor.fetchall()

    score = 0

    # Check answers
    for question in questions:

        question_id = question["id"]

        user_answer = request.form.get(
            f"question_{question_id}"
        )

        correct_answer = question["correct_answer"]

        if user_answer == correct_answer:
            score += 1

    total_questions = len(questions)

    # Save attempt
    cursor.execute(
        """
        INSERT INTO attempts
        (
            user_id,
            quiz_id,
            final_score
        )
        VALUES (%s, %s, %s)
        """,
        (
            session["user_id"],
            quiz_id,
            score
        )
    )

    # Get user streak information
    cursor.execute(
        """
        SELECT current_streak,
               longest_streak,
               last_quiz_date
        FROM users
        WHERE id = %s
        """,
        (session["user_id"],)
    )

    user = cursor.fetchone()

    today = date.today()

    current_streak = user["current_streak"]
    longest_streak = user["longest_streak"]
    last_quiz_date = user["last_quiz_date"]

    # Update streak
    if last_quiz_date is None:

        current_streak = 1

    elif last_quiz_date == today:

        # Already completed a quiz today
        current_streak = current_streak

    elif last_quiz_date == today - timedelta(days=1):

        current_streak += 1

    else:

        current_streak = 1

    if current_streak > longest_streak:
        longest_streak = current_streak

    # Update user
    cursor.execute(
        """
        UPDATE users
        SET current_streak = %s,
            longest_streak = %s,
            last_quiz_date = %s
        WHERE id = %s
        """,
        (
            current_streak,
            longest_streak,
            today,
            session["user_id"]
        )
    )

    db.commit()

    cursor.close()

    return render_template(
        "result.html",
        quiz=quiz_data,
        score=score,
        total_questions=total_questions
    )
    
@app.route("/admin/quiz/<int:quiz_id>/delete", methods=["POST"])  
def delete_quiz(quiz_id):

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    cursor = db.cursor()

    cursor.execute(
        "delete from quizzes where id = %s",
        (quiz_id,)
    )

    db.commit()

    cursor.close()

    return redirect("/admin")

@app.route(
    "/admin/quiz/<int:quiz_id>/add-question",
    methods=["POST"]
)
def add_question(quiz_id):

    if "user_id" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    question = request.form["question"]
    code = request.form["code"]

    option_a = request.form["option_a"]
    option_b = request.form["option_b"]
    option_c = request.form["option_c"]
    option_d = request.form["option_d"]

    correct_answer = request.form["correct_answer"]

    cursor = db.cursor()

    cursor.execute(
        """
        insert into questions
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
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
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
    )

    db.commit()

    cursor.close()

    return redirect(
        f"/admin/quiz/{quiz_id}"
    )
    

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)