import os
from datetime import date, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

# Import notifications if available
try:
    from telegram import send_telegram_message
except ImportError:
    send_telegram_message = None

try:
    from whatsapp import send_to_whatsapp_group
except ImportError:
    send_to_whatsapp_group = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "codequest_secret_key")

# Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})

# Global DB connection manager
db_connection = None

def get_db():
    global db_connection
    if db_connection is None or db_connection.closed != 0:
        try:
            # Supabase / PostgreSQL connection string
            database_url = os.environ.get(
                "DATABASE_URL", 
                "postgresql://postgres.ywbfdhcllimmargcjvds:Shanmukha%40429@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres?pgbouncer=true"
            )
            db_connection = psycopg2.connect(database_url)
            print("PostgreSQL database connected successfully")
        except Exception as e:
            print("PostgreSQL connection failed:", e)
            raise e
    return db_connection

# Helper function to get current user from headers
def get_auth():
    user_id = request.headers.get("X-User-Id")
    role = request.headers.get("X-User-Role")
    if not user_id:
        return None, None
    return int(user_id), role

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT * FROM users WHERE username = %s",
            (username,)
        )
        user = cursor.fetchone()
        cursor.close()

        if user is None or user["password"] != password:
            return jsonify({"error": "Invalid username or password."}), 401

        return jsonify({
            "success": True,
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    user_id, role = get_auth()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        # Get user details
        cursor.execute(
            "SELECT username, current_streak, longest_streak FROM users WHERE id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        if not user:
            cursor.close()
            return jsonify({"error": "User not found"}), 404
            
        # Get total score
        cursor.execute(
            "SELECT COALESCE(SUM(final_score), 0) AS total_score FROM attempts WHERE user_id = %s",
            (user_id,)
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
            (user_id,)
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

        return jsonify({
            "user": user,
            "total_score": total_score,
            "quizzes": quizzes
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin", methods=["GET"])
def admin():
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM quizzes ORDER BY id DESC")
        quizzes = cursor.fetchall()
        cursor.close()
        return jsonify({"quizzes": quizzes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/add-quiz", methods=["POST"])
def add_quiz():
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    title = data.get("title")
    description = data.get("description")

    if not title or not description:
        return jsonify({"error": "Title and description are required"}), 400

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO quizzes (title, description) VALUES (%s, %s)",
            (title, description)
        )
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users", methods=["GET", "POST"])
def manage_users():
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        if request.method == "GET":
            cursor.execute("SELECT id, username, role, current_streak, longest_streak, last_quiz_date FROM users ORDER BY id")
            users = cursor.fetchall()
            cursor.close()
            # Convert date objects to string for JSON serialization
            for u in users:
                if u["last_quiz_date"]:
                    u["last_quiz_date"] = u["last_quiz_date"].strftime("%Y-%m-%d")
            return jsonify({"users": users})

        # POST request
        data = request.get_json() or {}
        username = data.get("username")
        password = data.get("password")
        user_role = data.get("role", "user")

        if not username or not password:
            cursor.close()
            return jsonify({"error": "Username and password are required"}), 400

        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            (username, password, user_role)
        )
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/quiz/<int:quiz_id>", methods=["GET"])
def manage_questions(quiz_id):
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        # Get quiz
        cursor.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
        quiz = cursor.fetchone()

        if not quiz:
            cursor.close()
            return jsonify({"error": "Quiz not found"}), 404

        # Get questions
        cursor.execute(
            "SELECT * FROM questions WHERE quiz_id = %s ORDER BY id",
            (quiz_id,)
        )
        questions = cursor.fetchall()
        cursor.close()

        return jsonify({
            "quiz": quiz,
            "questions": questions
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/quiz/<int:quiz_id>/add-question", methods=["POST"])
def add_question(quiz_id):
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    question = data.get("question")
    code = data.get("code")
    option_a = data.get("option_a")
    option_b = data.get("option_b")
    option_c = data.get("option_c")
    option_d = data.get("option_d")
    correct_answer = data.get("correct_answer")

    if not all([question, option_a, option_b, option_c, option_d, correct_answer]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO questions (quiz_id, question, code, option_a, option_b, option_c, option_d, correct_answer)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (quiz_id, question, code, option_a, option_b, option_c, option_d, correct_answer)
        )
        db.commit()
        cursor.close()

        # Send notifications
        notification_text = f"📢 CodeQuest\n\nA new question has been added!\n\n🚀 Login to CodeQuest and try it."
        if send_telegram_message:
            try:
                send_telegram_message(notification_text)
            except Exception as e:
                print("Failed to send telegram notification:", e)
        if send_to_whatsapp_group:
            try:
                send_to_whatsapp_group(notification_text)
            except Exception as e:
                print("Failed to send WhatsApp notification:", e)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/question/<int:question_id>", methods=["GET", "PUT"])
def edit_question(question_id):
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        if request.method == "GET":
            cursor.execute("SELECT * FROM questions WHERE id = %s", (question_id,))
            question = cursor.fetchone()
            cursor.close()
            if not question:
                return jsonify({"error": "Question not found"}), 404
            return jsonify({"question": question})

        # PUT request
        data = request.get_json() or {}
        question_text = data.get("question")
        code = data.get("code")
        option_a = data.get("option_a")
        option_b = data.get("option_b")
        option_c = data.get("option_c")
        option_d = data.get("option_d")
        correct_answer = data.get("correct_answer")

        if not all([question_text, option_a, option_b, option_c, option_d, correct_answer]):
            cursor.close()
            return jsonify({"error": "Missing required fields"}), 400

        cursor.execute(
            """
            UPDATE questions
            SET question = %s, code = %s, option_a = %s, option_b = %s, option_c = %s, option_d = %s, correct_answer = %s
            WHERE id = %s
            """,
            (question_text, code, option_a, option_b, option_c, option_d, correct_answer, question_id)
        )
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/question/<int:question_id>/delete", methods=["POST"])
def delete_question(question_id):
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM questions WHERE id = %s", (question_id,))
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/quiz/<int:quiz_id>/delete", methods=["POST"])
def delete_quiz(quiz_id):
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM quizzes WHERE id = %s", (quiz_id,))
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/quiz/<int:quiz_id>", methods=["GET"])
def quiz(quiz_id):
    user_id, role = get_auth()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        # Check whether user already attempted this quiz
        cursor.execute(
            "SELECT * FROM attempts WHERE user_id = %s AND quiz_id = %s",
            (user_id, quiz_id)
        )
        attempt = cursor.fetchone()

        # Get quiz metadata
        cursor.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
        quiz_data = cursor.fetchone()

        if not quiz_data:
            cursor.close()
            return jsonify({"error": "Quiz not found"}), 404

        if attempt:
            cursor.close()
            return jsonify({
                "attempted": True,
                "quiz": quiz_data,
                "attempt": attempt
            })

        # Get questions
        cursor.execute(
            "SELECT id, quiz_id, question, code, option_a, option_b, option_c, option_d FROM questions WHERE quiz_id = %s ORDER BY id",
            (quiz_id,)
        )
        questions = cursor.fetchall()
        cursor.close()

        return jsonify({
            "attempted": False,
            "quiz": quiz_data,
            "questions": questions
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/quiz/<int:quiz_id>/submit", methods=["POST"])
def submit_quiz(quiz_id):
    user_id, role = get_auth()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    answers = data.get("answers", {})

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        # Check whether quiz exists
        cursor.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
        quiz_data = cursor.fetchone()
        if not quiz_data:
            cursor.close()
            return jsonify({"error": "Quiz not found"}), 404

        # Check whether user already attempted
        cursor.execute(
            "SELECT * FROM attempts WHERE user_id = %s AND quiz_id = %s",
            (user_id, quiz_id)
        )
        existing_attempt = cursor.fetchone()
        if existing_attempt:
            cursor.close()
            return jsonify({"error": "You have already attempted this quiz."}), 400

        # Get questions
        cursor.execute(
            "SELECT id, correct_answer FROM questions WHERE quiz_id = %s ORDER BY id",
            (quiz_id,)
        )
        questions = cursor.fetchall()

        score = 0
        for question in questions:
            qid = question["id"]
            user_ans = answers.get(str(qid)) or answers.get(qid)
            if user_ans == question["correct_answer"]:
                score += 1

        total_questions = len(questions)

        # Save attempt
        cursor.execute(
            """
            INSERT INTO attempts (user_id, quiz_id, final_score)
            VALUES (%s, %s, %s)
            """,
            (user_id, quiz_id, score)
        )

        # Get user streak information
        cursor.execute(
            "SELECT current_streak, longest_streak, last_quiz_date FROM users WHERE id = %s",
            (user_id,)
        )
        user = cursor.fetchone()

        today = date.today()
        current_streak = user["current_streak"]
        longest_streak = user["longest_streak"]
        last_quiz_date = user["last_quiz_date"]

        if last_quiz_date is None:
            current_streak = 1
        elif last_quiz_date == today:
            pass # Keep current
        elif last_quiz_date == today - timedelta(days=1):
            current_streak += 1
        else:
            current_streak = 1

        if current_streak > longest_streak:
            longest_streak = current_streak

        # Update user streak
        cursor.execute(
            """
            UPDATE users
            SET current_streak = %s, longest_streak = %s, last_quiz_date = %s
            WHERE id = %s
            """,
            (current_streak, longest_streak, today, user_id)
        )

        db.commit()
        cursor.close()

        return jsonify({
            "success": True,
            "score": score,
            "total_questions": total_questions
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
