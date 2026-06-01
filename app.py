from flask import Flask, render_template, request, redirect, jsonify, send_from_directory, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime
from dotenv import load_dotenv
from google import genai
import sqlite3
import os
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = "studyos_secret_key_2025"

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"mp4", "webm", "mov", "avi", "mkv"}
ALLOWED_IMG = {"png", "jpg", "jpeg", "gif", "webp"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_img(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMG

# ── GEMINI SETUP ──
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
print("KEY FOUND:", bool(GEMINI_API_KEY))
client = genai.Client(api_key=GEMINI_API_KEY)

# ── DATABASE ──
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        bio TEXT DEFAULT '',
        exam TEXT DEFAULT 'JEE',
        class_year TEXT DEFAULT '12',
        avatar TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedule(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        class TEXT,
        subject TEXT,
        start_time TEXT,
        end_time TEXT,
        done INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS leaderboard(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        marks INTEGER,
        week INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS documentary(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        class INTEGER,
        position INTEGER,
        story TEXT,
        content TEXT,
        video TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS planner(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject TEXT,
        notes TEXT,
        start_time TEXT,
        end_time TEXT,
        resource TEXT,
        done INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        content TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS progress(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS quiz(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        value TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ncert_pdf(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        filename TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fc_folders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        emoji TEXT DEFAULT '📁',
        color TEXT DEFAULT '#7c6ff7',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fc_cards(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_id INTEGER,
        user_id INTEGER,
        question TEXT,
        answer TEXT,
        emoji TEXT DEFAULT '❓',
        color TEXT DEFAULT '#7c6ff7',
        known INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS nodes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        subject TEXT,
        question TEXT,
        answer TEXT,
        x REAL DEFAULT 100,
        y REAL DEFAULT 100,
        color TEXT DEFAULT '#7c6ff7'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS node_connections(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        from_id INTEGER,
        to_id INTEGER
    )
    """)
    cur.execute("""
     CREATE TABLE IF NOT EXISTS feedback(
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         user_id INTEGER,
         username TEXT,
          page TEXT,
          message TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    # ✅ doubts table here not inside route
    cur.execute("""
    CREATE TABLE IF NOT EXISTS doubts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        question TEXT,
        answer TEXT,
        subject TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ── USER MODEL ──
class User(UserMixin):
    def __init__(self, id, username, email, bio, exam, class_year, avatar):
        self.id = id
        self.username = username
        self.email = email
        self.bio = bio
        self.exam = exam
        self.class_year = class_year
        self.avatar = avatar

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if u:
        return User(u['id'], u['username'], u['email'], u['bio'],
                    u['exam'], u['class_year'], u['avatar'])
    return None

# ── VISITOR LOG ──
@app.before_request
def log_visitor():
    ip = request.remote_addr
    path = request.path
    user_agent = request.headers.get('User-Agent')
    with open("visitors.txt", "a", encoding="utf-8") as f:
        f.write(
            f"Time: {datetime.now()} | "
            f"IP: {ip} | "
            f"Page: {path} | "
            f"Browser: {user_agent}\n"
        )

# ── AUTH ──
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect("/")
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        exam = request.form.get("exam", "JEE")
        class_year = request.form.get("class_year", "12")
        bio = request.form.get("bio", "")

        conn = get_db()
        existing = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (username, email)
        ).fetchone()

        if existing:
            conn.close()
            return render_template("register.html",
                error="Username or email already taken!")

        hashed = bcrypt.generate_password_hash(password).decode("utf-8")

        avatar = ""
        if "avatar" in request.files:
            file = request.files["avatar"]
            if file and file.filename != "" and allowed_img(file.filename):
                filename = secure_filename("avatar_" + username + "_" + file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                avatar = "/static/uploads/" + filename

        conn.execute(
            "INSERT INTO users(username, email, password, bio, exam, class_year, avatar) VALUES(?,?,?,?,?,?,?)",
            (username, email, hashed, bio, exam, class_year, avatar)
        )
        conn.commit()
        conn.close()
        return redirect("/login")

    return render_template("register.html", error=None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect("/")
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()
        u = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (username, username)
        ).fetchone()
        conn.close()

        if u and bcrypt.check_password_hash(u['password'], password):
            user = User(u['id'], u['username'], u['email'], u['bio'],
                        u['exam'], u['class_year'], u['avatar'])
            login_user(user)
            return redirect("/")
        return render_template("login.html",
            error="Wrong username or password!")

    return render_template("login.html", error=None)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        bio = request.form.get("bio", "")
        exam = request.form.get("exam", "JEE")
        class_year = request.form.get("class_year", "12")
        conn = get_db()

        avatar = current_user.avatar
        if "avatar" in request.files:
            file = request.files["avatar"]
            if file and file.filename != "" and allowed_img(file.filename):
                filename = secure_filename(
                    "avatar_" + current_user.username + "_" + file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                avatar = "/static/uploads/" + filename

        conn.execute(
            "UPDATE users SET bio=?, exam=?, class_year=?, avatar=? WHERE id=?",
            (bio, exam, class_year, avatar, current_user.id)
        )
        conn.commit()
        conn.close()
        return redirect("/profile")

    return render_template("profile.html")


# ── HOME ──
@app.route("/")
@login_required
def home():
    conn = get_db()
    cur = conn.cursor()
    uid = current_user.id

    planner_all = cur.execute(
        "SELECT * FROM planner WHERE user_id=?", (uid,)
    ).fetchall()
    planner_done = sum(1 for p in planner_all if p['done'] == 1)
    planner_count = len(planner_all)
    planner_pct = int((planner_done / planner_count) * 100) if planner_count > 0 else 0

    progress_count = cur.execute(
        "SELECT COUNT(*) FROM progress WHERE user_id=?", (uid,)
    ).fetchone()[0]

    leaderboard_count = cur.execute(
        "SELECT COUNT(*) FROM leaderboard"
    ).fetchone()[0]

    schedule = cur.execute(
        "SELECT * FROM schedule WHERE user_id=? ORDER BY start_time", (uid,)
    ).fetchall()
    schedule_done = sum(1 for s in schedule if s['done'] == 1)

    streak = cur.execute(
        "SELECT COUNT(DISTINCT DATE(created_at)) FROM progress WHERE user_id=?",
        (uid,)
    ).fetchone()[0]

    conn.close()
    now = datetime.now()

    return render_template("index.html",
        planner_count=planner_count,
        planner_done=planner_done,
        planner_pct=planner_pct,
        progress_count=progress_count,
        leaderboard_count=leaderboard_count,
        schedule=schedule,
        schedule_done=schedule_done,
        streak=streak,
        now_hour=now.hour,
        now_min=now.minute
    )


# ── SCHEDULE ──
@app.route("/schedule", methods=["GET", "POST"])
@login_required
def schedule():
    conn = get_db()
    cur = conn.cursor()
    uid = current_user.id

    if request.method == "POST":
        cur.execute("""
        INSERT INTO schedule(user_id, name, class, subject, start_time, end_time)
        VALUES(?,?,?,?,?,?)
        """, (uid, request.form["name"], request.form["class"],
              request.form["subject"], request.form["start_time"],
              request.form["end_time"]))
        conn.commit()

    data = cur.execute(
        "SELECT * FROM schedule WHERE user_id=? ORDER BY start_time", (uid,)
    ).fetchall()
    conn.close()
    return render_template("schedule.html", schedule=data)


@app.route("/update_done", methods=["POST"])
@login_required
def update_done():
    data = request.get_json()
    conn = get_db()
    conn.execute("UPDATE schedule SET done=? WHERE id=? AND user_id=?",
                 (1 if data["done"] else 0, data["id"], current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/delete_schedule/<int:id>", methods=["POST"])
@login_required
def delete_schedule(id):
    conn = get_db()
    conn.execute("DELETE FROM schedule WHERE id=? AND user_id=?",
                 (id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


# ── LEADERBOARD ──
@app.route("/leaderboard", methods=["GET", "POST"])
@login_required
def leaderboard():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute(
            "INSERT INTO leaderboard(user_id, name, marks, week) VALUES(?,?,?,?)",
            (current_user.id, request.form["name"],
             request.form["marks"], request.form["week"])
        )
        conn.commit()

    selected_week = request.args.get("week")

    if selected_week:
        rows = cur.execute(
            "SELECT * FROM leaderboard WHERE week=? ORDER BY marks DESC",
            (selected_week,)
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT * FROM leaderboard ORDER BY marks DESC"
        ).fetchall()

    weeks = cur.execute(
        "SELECT DISTINCT week FROM leaderboard ORDER BY week DESC"
    ).fetchall()
    weeks = [w["week"] for w in weeks]

    max_marks = rows[0]["marks"] if rows else 1
    students = []
    for r in rows:
        pct = int((r["marks"] / max_marks) * 100) if max_marks > 0 else 0
        students.append({
            "name": r["name"], "marks": r["marks"],
            "week": r["week"], "pct": pct
        })

    conn.close()
    return render_template("leaderboard.html",
        students=students, weeks=weeks, selected_week=selected_week)


# ── DOCUMENTARY ──
@app.route("/documentary", methods=["GET", "POST"])
@login_required
def documentary():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        video_path = None
        if "video" in request.files:
            file = request.files["video"]
            if file and file.filename != "" and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                video_path = "/static/uploads/" + filename

        cur.execute("""
        INSERT INTO documentary(user_id, name, class, position, story, content, video)
        VALUES(?,?,?,?,?,?,?)
        """, (current_user.id, request.form["name"], request.form["class"],
              request.form["position"], request.form["story"],
              request.form["content"], video_path))
        conn.commit()

    students = cur.execute(
        "SELECT * FROM documentary ORDER BY position ASC"
    ).fetchall()
    conn.close()
    return render_template("documentary.html", students=students)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ── PLANNER ──
@app.route("/planner", methods=["GET", "POST"])
@login_required
def planner():
    conn = get_db()
    cur = conn.cursor()
    uid = current_user.id

    if request.method == "POST":
        cur.execute("""
        INSERT INTO planner(user_id, subject, notes, start_time, end_time, resource)
        VALUES(?,?,?,?,?,?)
        """, (uid, request.form["subject"], request.form["notes"],
              request.form["start_time"], request.form["end_time"],
              request.form["resource"]))
        conn.commit()

    data = cur.execute(
        "SELECT * FROM planner WHERE user_id=? ORDER BY id DESC", (uid,)
    ).fetchall()
    conn.close()
    return render_template("planner.html", entries=data)


@app.route("/update_planner", methods=["POST"])
@login_required
def update_planner():
    data = request.get_json()
    conn = get_db()
    conn.execute("UPDATE planner SET done=? WHERE id=? AND user_id=?",
                 (1 if data["done"] else 0, data["id"], current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/delete_task/<int:id>", methods=["POST"])
@login_required
def delete_task(id):
    conn = get_db()
    conn.execute("DELETE FROM planner WHERE id=? AND user_id=?",
                 (id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


# ── AI PLAN ──
@app.route("/ai_plan", methods=["POST"])
@login_required
def ai_plan():
    topic = request.form.get("topic", "").strip()
    if not topic:
        return jsonify({"plan": "Please enter a topic."})

    try:
        prompt = f"""You are a study planner for JEE/NEET students.
Create a detailed 4-day study plan for: {topic}

Format exactly like this:
Day 1 — [Topic Name]
- Task 1
- Task 2
- Time: X hours

Day 2 — [Topic Name]
- Task 1
- Task 2
- Time: X hours

Day 3 — [Topic Name]
- Task 1
- Task 2
- Time: X hours

Day 4 — [Topic Name]
- Task 1
- Task 2
- Time: X hours

Keep it practical and specific for Indian competitive exams."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return jsonify({"plan": response.text})

    except Exception as e:
        print("AI PLAN ERROR:", e)
        return jsonify({"plan": f"AI Error: {str(e)}"})


# ── AI SAVE ──
@app.route("/ai_save", methods=["POST"])
@login_required
def ai_save():
    subject = request.form.get("subject", "AI Plan")
    plan = request.form.get("plan", "")
    conn = get_db()
    conn.execute(
        "INSERT INTO planner(user_id, subject, notes) VALUES(?,?,?)",
        (current_user.id, subject, plan)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "saved"})


# ── DOUBT PAGE ──
@app.route("/doubt")
@login_required
def doubt():
    conn = get_db()
    doubts = conn.execute(
        "SELECT * FROM doubts WHERE user_id=? ORDER BY id DESC",
        (current_user.id,)
    ).fetchall()
    conn.close()
    return render_template("doubt.html", doubts=doubts)


# ── ASK DOUBT (AJAX) ──
@app.route("/ask_doubt", methods=["POST"])
@login_required
def ask_doubt():
    data = request.get_json()
    question = data.get("question", "").strip()
    subject = data.get("subject", "General")

    if not question:
        return jsonify({"answer": "Please enter a question."})

    try:
        prompt = f"""You are an expert tutor for Indian competitive exams (JEE/NEET/UPSC).
A student has this doubt in {subject}:

{question}

Give a clear, step-by-step explanation with:
- Simple language
- Examples where needed
- Formulas if relevant
- Key points at the end

Be concise but complete."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        answer = response.text

        # ✅ Save to DB before return
        conn = get_db()
        conn.execute(
            "INSERT INTO doubts(user_id, question, answer, subject) VALUES(?,?,?,?)",
            (current_user.id, question, answer, subject)
        )
        conn.commit()
        conn.close()

    except Exception as e:
        print("ASK DOUBT ERROR:", e)
        answer = f"AI Error: {str(e)}"

    return jsonify({"answer": answer})


# ── DELETE DOUBT ──
@app.route("/delete_doubt/<int:id>", methods=["POST"])
@login_required
def delete_doubt(id):
    conn = get_db()
    conn.execute("DELETE FROM doubts WHERE id=? AND user_id=?",
                 (id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


# ── NOTES ──
@app.route("/notes", methods=["GET", "POST"])
@login_required
def notes():
    conn = get_db()
    cur = conn.cursor()
    uid = current_user.id

    if request.method == "POST":
        cur.execute(
            "INSERT INTO notes(user_id, title, content) VALUES(?,?,?)",
            (uid, request.form["title"], request.form["content"])
        )
        conn.commit()

    data = cur.execute(
        "SELECT * FROM notes WHERE user_id=? ORDER BY id DESC", (uid,)
    ).fetchall()
    conn.close()
    return render_template("notes.html", notes=data)


# ── PROGRESS ──
@app.route("/progress", methods=["GET", "POST"])
@login_required
def progress():
    conn = get_db()
    cur = conn.cursor()
    uid = current_user.id

    if request.method == "POST":
        cur.execute(
            "INSERT INTO progress(user_id, title) VALUES(?,?)",
            (uid, request.form["title"])
        )
        conn.commit()

    data = cur.execute(
        "SELECT * FROM progress WHERE user_id=? ORDER BY id DESC", (uid,)
    ).fetchall()
    conn.close()
    return render_template("progress.html", progress=data)


@app.route("/delete_progress/<int:id>", methods=["POST"])
@login_required
def delete_progress(id):
    conn = get_db()
    conn.execute("DELETE FROM progress WHERE id=? AND user_id=?",
                 (id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

# ── FEEDBACK ──
@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        page = request.form.get("page", "").strip()
        message = request.form.get("message", "").strip()
        conn = get_db()
        conn.execute(
            "INSERT INTO feedback(user_id, username, page, message) VALUES(?,?,?,?)",
            (current_user.id, current_user.username, page, message)
        )
        conn.commit()
        conn.close()
        flash("✅ Feedback sent! Thank you.", "success")
        return redirect("/feedback")
    return render_template("feedback.html")


# ── ADMIN: VIEW FEEDBACK ──
@app.route("/admin/feedback")
@login_required
def admin_feedback():
    if current_user.username != "anuragrajraj14@gmail.com":  # 👈 put your username here
        return "Access denied", 403
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM feedback ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("admin_feedback.html", feedbacks=rows)


# ── DELETE FEEDBACK (admin only) ──
@app.route("/delete_feedback/<int:id>", methods=["POST"])
@login_required
def delete_feedback(id):
    if current_user.username != "anuragrajraj14@gmail.com":  # 👈 same username
        return "Access denied", 403
    conn = get_db()
    conn.execute("DELETE FROM feedback WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

# ── QUIZ ──
@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    conn = get_db()
    cur = conn.cursor()
    uid = current_user.id

    if request.method == "POST":
        cur.execute(
            "INSERT INTO quiz(user_id, name, value) VALUES(?,?,?)",
            (uid, request.form["name"], request.form["value"])
        )
        conn.commit()

    data = cur.execute(
        "SELECT * FROM quiz WHERE user_id=?", (uid,)
    ).fetchall()
    conn.close()
    return render_template("quiz.html", quiz=data)


# ── NCERT PDF ──
@app.route("/ncert_pdf")
@login_required
def ncert_pdf():
    return render_template("ncert_pdf.html")


# ── FLASHCARDS ──
@app.route("/flashcards")
@login_required
def flashcards():
    conn = get_db()
    cur = conn.cursor()
    uid = current_user.id

    folders = cur.execute(
        "SELECT * FROM fc_folders WHERE user_id=? ORDER BY id DESC", (uid,)
    ).fetchall()
    cards = cur.execute(
        "SELECT * FROM fc_cards WHERE user_id=?", (uid,)
    ).fetchall()

    folders_list = []
    for f in folders:
        f_cards = [c for c in cards if c['folder_id'] == f['id']]
        known = sum(1 for c in f_cards if c['known'] == 1)
        folders_list.append({
            'id': f['id'], 'name': f['name'],
            'emoji': f['emoji'], 'color': f['color'],
            'total': len(f_cards), 'known': known,
            'pct': int((known / len(f_cards)) * 100) if f_cards else 0
        })

    cards_list = [dict(c) for c in cards]
    conn.close()
    return render_template("flashcards.html",
        folders=folders_list, cards=cards_list)


@app.route("/fc_add_folder", methods=["POST"])
@login_required
def fc_add_folder():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO fc_folders(user_id, name, emoji, color) VALUES(?,?,?,?)",
        (current_user.id, data["name"], data["emoji"], data["color"])
    )
    conn.commit()
    fid = cur.lastrowid
    conn.close()
    return jsonify({"status": "ok", "id": fid})


@app.route("/fc_delete_folder/<int:id>", methods=["POST"])
@login_required
def fc_delete_folder(id):
    conn = get_db()
    folder = conn.execute(
        "SELECT * FROM fc_folders WHERE id=? AND user_id=?",
        (id, current_user.id)
    ).fetchone()
    if not folder:
        conn.close()
        return jsonify({"status": "forbidden"}), 403
    conn.execute("DELETE FROM fc_folders WHERE id=? AND user_id=?",
                 (id, current_user.id))
    conn.execute("DELETE FROM fc_cards WHERE folder_id=? AND user_id=?",
                 (id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


@app.route("/fc_add_card", methods=["POST"])
@login_required
def fc_add_card():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    folder = cur.execute(
        "SELECT * FROM fc_folders WHERE id=? AND user_id=?",
        (data["folder_id"], current_user.id)
    ).fetchone()
    if not folder:
        conn.close()
        return jsonify({"status": "forbidden"}), 403
    cur.execute(
        "INSERT INTO fc_cards(user_id, folder_id, question, answer, emoji, color) VALUES(?,?,?,?,?,?)",
        (current_user.id, data["folder_id"], data["question"],
         data["answer"], data["emoji"], data["color"])
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return jsonify({"status": "ok", "id": cid})


@app.route("/fc_delete_card/<int:id>", methods=["POST"])
@login_required
def fc_delete_card(id):
    conn = get_db()
    card = conn.execute(
        "SELECT * FROM fc_cards WHERE id=? AND user_id=?",
        (id, current_user.id)
    ).fetchone()
    if not card:
        conn.close()
        return jsonify({"status": "forbidden"}), 403
    conn.execute("DELETE FROM fc_cards WHERE id=? AND user_id=?",
                 (id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


@app.route("/fc_mark_known", methods=["POST"])
@login_required
def fc_mark_known():
    data = request.get_json()
    conn = get_db()
    card = conn.execute(
        "SELECT * FROM fc_cards WHERE id=? AND user_id=?",
        (data["id"], current_user.id)
    ).fetchone()
    if not card:
        conn.close()
        return jsonify({"status": "forbidden"}), 403
    conn.execute(
        "UPDATE fc_cards SET known=? WHERE id=? AND user_id=?",
        (1 if data["known"] else 0, data["id"], current_user.id)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/fc_reset_folder/<int:id>", methods=["POST"])
@login_required
def fc_reset_folder(id):
    conn = get_db()
    folder = conn.execute(
        "SELECT * FROM fc_folders WHERE id=? AND user_id=?",
        (id, current_user.id)
    ).fetchone()
    if not folder:
        conn.close()
        return jsonify({"status": "forbidden"}), 403
    conn.execute(
        "UPDATE fc_cards SET known=0 WHERE folder_id=? AND user_id=?",
        (id, current_user.id)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "reset"})


# ── NODES ──
@app.route("/nodes", methods=["GET", "POST"])
@login_required
def nodes():
    conn = get_db()
    cur = conn.cursor()
    uid = current_user.id

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            cur.execute(
                "INSERT INTO nodes(user_id, subject, question, answer, x, y, color) VALUES(?,?,?,?,?,?,?)",
                (uid, request.form["subject"], request.form["question"],
                 request.form["answer"], request.form.get("x", 100),
                 request.form.get("y", 100), request.form.get("color", "#7c6ff7"))
            )
            conn.commit()

    all_nodes = cur.execute(
        "SELECT * FROM nodes WHERE user_id=?", (uid,)
    ).fetchall()
    all_conns = cur.execute(
        "SELECT * FROM node_connections WHERE user_id=?", (uid,)
    ).fetchall()
    conn.close()

    return render_template("nodes.html",
        nodes=[dict(n) for n in all_nodes],
        connections=[dict(c) for c in all_conns]
    )


@app.route("/save_node_pos", methods=["POST"])
@login_required
def save_node_pos():
    data = request.get_json()
    conn = get_db()
    node = conn.execute(
        "SELECT * FROM nodes WHERE id=? AND user_id=?",
        (data["id"], current_user.id)
    ).fetchone()
    if not node:
        conn.close()
        return jsonify({"status": "forbidden"}), 403
    conn.execute(
        "UPDATE nodes SET x=?, y=? WHERE id=? AND user_id=?",
        (data["x"], data["y"], data["id"], current_user.id)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/delete_node/<int:id>", methods=["POST"])
@login_required
def delete_node(id):
    conn = get_db()
    node = conn.execute(
        "SELECT * FROM nodes WHERE id=? AND user_id=?",
        (id, current_user.id)
    ).fetchone()
    if not node:
        conn.close()
        return jsonify({"status": "forbidden"}), 403
    conn.execute("DELETE FROM nodes WHERE id=? AND user_id=?",
                 (id, current_user.id))
    conn.execute(
        "DELETE FROM node_connections WHERE (from_id=? OR to_id=?) AND user_id=?",
        (id, id, current_user.id)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


@app.route("/save_connection", methods=["POST"])
@login_required
def save_connection():
    data = request.get_json()
    conn = get_db()
    from_node = conn.execute(
        "SELECT * FROM nodes WHERE id=? AND user_id=?",
        (data["from_id"], current_user.id)
    ).fetchone()
    to_node = conn.execute(
        "SELECT * FROM nodes WHERE id=? AND user_id=?",
        (data["to_id"], current_user.id)
    ).fetchone()
    if not from_node or not to_node:
        conn.close()
        return jsonify({"status": "forbidden"}), 403
    existing = conn.execute(
        "SELECT * FROM node_connections WHERE from_id=? AND to_id=? AND user_id=?",
        (data["from_id"], data["to_id"], current_user.id)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO node_connections(user_id, from_id, to_id) VALUES(?,?,?)",
            (current_user.id, data["from_id"], data["to_id"])
        )
        conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/delete_connection", methods=["POST"])
@login_required
def delete_connection():
    data = request.get_json()
    conn = get_db()
    conn.execute(
        "DELETE FROM node_connections WHERE from_id=? AND to_id=? AND user_id=?",
        (data["from_id"], data["to_id"], current_user.id)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


# ── RUN ──
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)