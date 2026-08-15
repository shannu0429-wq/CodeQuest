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
                "postgresql://postgres.ywbfdhcllimmargcjvds:Shanmukha0429@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres"
            )
            # Clean up pgbouncer query parameter as it crashes psycopg2 connection parser
            if "?" in database_url:
                base_uri, query = database_url.split("?", 1)
                params = [p for p in query.split("&") if not p.startswith("pgbouncer=")]
                database_url = base_uri + ("?" + "&".join(params) if params else "")
                
            # URL-encode the password if it contains an unencoded '@' character
            if "://" in database_url:
                scheme, rest = database_url.split("://", 1)
                if "@" in rest:
                    userinfo, hostinfo = rest.rsplit("@", 1)
                    if ":" in userinfo:
                        username, password = userinfo.split(":", 1)
                        import urllib.parse
                        password_decoded = urllib.parse.unquote(password)
                        password_encoded = urllib.parse.quote(password_decoded)
                        database_url = f"{scheme}://{username}:{password_encoded}@{hostinfo}"
                
            db_connection = psycopg2.connect(database_url)
            print("PostgreSQL database connected successfully")
        except Exception as e:
            print("PostgreSQL connection failed:", e)
            raise e
    return db_connection

@app.before_request
def before_request_func():
    if not hasattr(app, '_migrations_run'):
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
            cursor.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS solution_text TEXT NULL;")
            cursor.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS solution_image VARCHAR(255) NULL;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id INT NULL REFERENCES users(id) ON DELETE CASCADE,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_read BOOLEAN DEFAULT FALSE
                );
            """)
            db.commit()
            cursor.close()
            app._migrations_run = True
            print("Database migrations applied successfully!")
        except Exception as e:
            print("Database migrations failed:", e)

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
                COALESCE(a.questions_attempted, 0) as questions_attempted,
                COALESCE(a.correct_answers, 0) as correct_answers,
                COALESCE((SELECT COUNT(*) FROM questions WHERE quiz_id = q.id), 0) as total_questions
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
            # If they have attempted at least one question, set attempted = True
            quiz["attempted"] = quiz["questions_attempted"] > 0

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
    created_at = data.get("created_at") or None
    solution_text = data.get("solution_text") or None
    solution_image = data.get("solution_image") or None

    if not all([question, option_a, option_b, option_c, option_d, correct_answer]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute(
            """
            INSERT INTO questions (quiz_id, question, code, option_a, option_b, option_c, option_d, correct_answer, created_at, solution_text, solution_image)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP), %s, %s)
            """,
            (quiz_id, question, code, option_a, option_b, option_c, option_d, correct_answer, created_at, solution_text, solution_image)
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
            if question.get("created_at"):
                question["created_at"] = question["created_at"].strftime("%Y-%m-%d")
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
        created_at = data.get("created_at") or None
        solution_text = data.get("solution_text") or None
        solution_image = data.get("solution_image") or None

        if not all([question_text, option_a, option_b, option_c, option_d, correct_answer]):
            cursor.close()
            return jsonify({"error": "Missing required fields"}), 400

        cursor.execute(
            """
            UPDATE questions
            SET question = %s, code = %s, option_a = %s, option_b = %s, option_c = %s, option_d = %s, correct_answer = %s, created_at = COALESCE(%s, CURRENT_TIMESTAMP), solution_text = %s, solution_image = %s
            WHERE id = %s
            """,
            (question_text, code, option_a, option_b, option_c, option_d, correct_answer, created_at, solution_text, solution_image, question_id)
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

        # Check whether user has an attempt record
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

        # Get user answers
        cursor.execute(
            "SELECT question_id, user_answer, is_correct FROM user_answers WHERE user_id = %s AND quiz_id = %s",
            (user_id, quiz_id)
        )
        answers = cursor.fetchall()
        answered_map = {str(a["question_id"]): {"user_answer": a["user_answer"], "is_correct": a["is_correct"]} for a in answers}

        # Get questions
        cursor.execute(
            "SELECT id, quiz_id, question, code, option_a, option_b, option_c, option_d, correct_answer, created_at, solution_text, solution_image FROM questions WHERE quiz_id = %s ORDER BY id",
            (quiz_id,)
        )
        questions = cursor.fetchall()

        # Format times and hide solutions/answers for unanswered questions
        for question in questions:
            if question.get("created_at"):
                question["created_at"] = question["created_at"].strftime("%Y-%m-%d")
            else:
                question["created_at"] = None

            qid_str = str(question["id"])
            if qid_str not in answered_map:
                # Hide answer and solution from student to prevent cheating
                question["correct_answer"] = None
                question["solution_text"] = None
                question["solution_image"] = None

        if quiz_data.get("created_at"):
            quiz_data["created_at"] = quiz_data["created_at"].strftime("%Y-%m-%d %H:%M:%S")

        cursor.close()
        return jsonify({
            "quiz": quiz_data,
            "attempt": attempt,
            "questions": questions,
            "answers": answered_map
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/quiz/<int:quiz_id>/submit-single", methods=["POST"])
def submit_single(quiz_id):
    user_id, role = get_auth()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    question_id = data.get("question_id")
    user_answer = data.get("user_answer")

    if not question_id or not user_answer:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)

        # Check correct answer
        cursor.execute("SELECT correct_answer FROM questions WHERE id = %s AND quiz_id = %s", (question_id, quiz_id))
        question = cursor.fetchone()
        if not question:
            cursor.close()
            return jsonify({"error": "Question not found"}), 404

        is_correct = (user_answer == question["correct_answer"])

        # Insert/Update in user_answers table
        cursor.execute("""
            INSERT INTO user_answers (user_id, quiz_id, question_id, user_answer, is_correct)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, question_id) 
            DO UPDATE SET user_answer = EXCLUDED.user_answer, is_correct = EXCLUDED.is_correct;
        """, (user_id, quiz_id, question_id, user_answer, is_correct))

        # Recalculate and update attempts table (increment score and attempted questions)
        cursor.execute(
            "SELECT COUNT(*) as count FROM user_answers WHERE user_id = %s AND quiz_id = %s AND is_correct = True",
            (user_id, quiz_id)
        )
        correct_count = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM user_answers WHERE user_id = %s AND quiz_id = %s",
            (user_id, quiz_id)
        )
        attempted_count = cursor.fetchone()["count"]

        # Insert/Update attempts
        cursor.execute("""
            INSERT INTO attempts (user_id, quiz_id, questions_attempted, correct_answers, final_score)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, quiz_id)
            DO UPDATE SET 
                questions_attempted = EXCLUDED.questions_attempted,
                correct_answers = EXCLUDED.correct_answers,
                final_score = EXCLUDED.final_score;
        """, (user_id, quiz_id, attempted_count, correct_count, correct_count))

        # Get and update user streak immediately
        cursor.execute(
            "SELECT current_streak, longest_streak, last_quiz_date FROM users WHERE id = %s",
            (user_id,)
        )
        user = cursor.fetchone()

        today = date.today()
        current_streak = user["current_streak"]
        longest_streak = user["longest_streak"]
        last_quiz_date = user["last_quiz_date"]

        if last_quiz_date != today:
            if last_quiz_date is None:
                current_streak = 1
            elif last_quiz_date == today - timedelta(days=1):
                current_streak += 1
            else:
                current_streak = 1

            if current_streak > longest_streak:
                longest_streak = current_streak

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

        # Retrieve solution to return
        cursor.execute("SELECT solution_text, solution_image FROM questions WHERE id = %s", (question_id,))
        solution_data = cursor.fetchone()

        return jsonify({
            "success": True,
            "is_correct": is_correct,
            "correct_answer": question["correct_answer"],
            "solution_text": solution_data["solution_text"] if (solution_data and "solution_text" in solution_data) else None,
            "solution_image": solution_data["solution_image"] if (solution_data and "solution_image" in solution_data) else None
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    user_id, role = get_auth()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT id, message, created_at, is_read 
            FROM notifications 
            WHERE user_id = %s OR user_id IS NULL 
            ORDER BY created_at DESC
        """, (user_id,))
        notifications = cursor.fetchall()
        for n in notifications:
            n["created_at"] = n["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        cursor.close()
        return jsonify({"notifications": notifications})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications/read", methods=["POST"])
def mark_notifications_read():
    user_id, role = get_auth()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE notifications SET is_read = True WHERE user_id = %s OR user_id IS NULL", (user_id,))
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/notifications", methods=["POST"])
def admin_create_notification():
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    target_user_id = data.get("user_id") or None
    message = data.get("message")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO notifications (user_id, message)
            VALUES (%s, %s)
        """, (target_user_id, message))
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/attempts-log", methods=["GET"])
def admin_attempts_log():
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)
        
        # Join user_answers with users, quizzes, and questions
        cursor.execute("""
            SELECT 
                ua.id,
                u.username,
                qz.title as quiz_title,
                q.id as question_id,
                q.question as question_text,
                ua.user_answer,
                q.correct_answer,
                ua.is_correct
            FROM user_answers ua
            JOIN users u ON ua.user_id = u.id
            JOIN quizzes qz ON ua.quiz_id = qz.id
            JOIN questions q ON ua.question_id = q.id
            ORDER BY ua.id DESC
        """)
        logs = cursor.fetchall()
        cursor.close()
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<int:u_id>", methods=["DELETE"])
def delete_user(u_id):
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    # Check if admin is deleting themselves (not allowed)
    if u_id == user_id:
        return jsonify({"error": "You cannot delete your own admin account."}), 400

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s", (u_id,))
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<int:u_id>/password", methods=["PUT"])
def change_user_password(u_id):
    user_id, role = get_auth()
    if not user_id or role != "admin":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    new_password = data.get("password")

    if not new_password:
        return jsonify({"error": "Password is required"}), 400

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (new_password, u_id))
        db.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
