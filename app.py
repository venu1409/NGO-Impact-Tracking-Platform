from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"


# ---------------- DATABASE ---------------- #

def get_db():
    return sqlite3.connect("database.db")


def init_db():
    conn = get_db()
    c = conn.cursor()

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 email TEXT,
                 password TEXT,
                 role TEXT)''')

    # Projects table
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT,
                 goal INTEGER,
                 collected INTEGER DEFAULT 0)''')

    # Donations table
    c.execute('''CREATE TABLE IF NOT EXISTS donations (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 project_id INTEGER,
                 amount INTEGER)''')


    c.execute('''CREATE TABLE IF NOT EXISTS updates (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             project_id INTEGER,
             description TEXT,
             amount_used INTEGER)''')

    # Insert default admin
    c.execute("SELECT * FROM users WHERE email='123@gmail.com'")
    if not c.fetchone():
        c.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
                  ("123@gmail.com", "ADMINPASS", "admin"))

    conn.commit()
    conn.close()


# ---------------- ROUTES ---------------- #

@app.route("/")
def home():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM projects")
    projects = c.fetchall()
    conn.close()
    return render_template("index.html", projects=projects)


# ---------------- REGISTER ---------------- #

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
                  (email, password, "user"))
        conn.commit()
        conn.close()

        return render_template("register_success.html")

    return render_template("register.html")


# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=? AND password=?",
                  (email, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = user[1]
            session["role"] = user[3]
            return redirect("/dashboard")
        else:
            return "Invalid Credentials"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- DASHBOARD ---------------- #

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM projects")
    projects = c.fetchall()
    conn.close()

    return render_template("dashboard.html", projects=projects)


# ---------------- ADD PROJECT (ADMIN) ---------------- #

@app.route("/add_project", methods=["POST"])
def add_project():
    if session.get("role") == "admin":
        name = request.form["name"]
        goal = request.form["goal"]

        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO projects (name, goal) VALUES (?, ?)",
                  (name, goal))
        conn.commit()
        conn.close()

    return redirect("/dashboard")


# ---------------- DONATE ---------------- #
@app.route("/donate/<int:id>", methods=["POST"])
def donate(id):
    if "user" not in session:
        return redirect("/login")

    amount = int(request.form["amount"])

    conn = get_db()
    c = conn.cursor()

    # Get user id safely
    c.execute("SELECT id FROM users WHERE email=?", (session["user"],))
    user = c.fetchone()

    if not user:
        conn.close()
        return "User not found. Please login again."

    user_id = user[0]

    # Update project collected amount
    c.execute("UPDATE projects SET collected = collected + ? WHERE id = ?", (amount, id))

    # Insert donation record
    c.execute("INSERT INTO donations (user_id, project_id, amount) VALUES (?, ?, ?)",
              (user_id, id, amount))

    conn.commit()
    conn.close()

    return redirect("/project/" + str(id))


@app.route("/project/<int:id>")
def project(id):
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()

    # Get project
    c.execute("SELECT * FROM projects WHERE id=?", (id,))
    project = c.fetchone()

    if not project:
        conn.close()
        return "Project not found"

    # Get transparency updates
    c.execute("SELECT * FROM updates WHERE project_id=?", (id,))
    updates = c.fetchall()

    # Calculate total used
    total_used = 0
    for u in updates:
        total_used += u[3]

    remaining = project[3] - total_used

    conn.close()

    return render_template("project.html",
                           project=project,
                           updates=updates,
                           total_used=total_used,
                           remaining=remaining)


# ---------------- DONATION HISTORY + BADGE ---------------- #

@app.route("/donation_history")
def donation_history():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()

    if session.get("role") == "admin":

        # Get all users (excluding admin)
        c.execute("SELECT id, email FROM users WHERE role='user'")
        users = c.fetchall()

        admin_data = []

        for user in users:
            user_id = user[0]
            email = user[1]

            c.execute('''
                SELECT projects.name, donations.amount, projects.goal
                FROM donations
                JOIN projects ON donations.project_id = projects.id
                WHERE donations.user_id=?
            ''', (user_id,))
            donations = c.fetchall()

            unique_projects = set()
            badge = False

            for d in donations:
                unique_projects.add(d[0])

                # Condition 1: donated >= 50% of project goal
                if d[1] >= 0.5 * d[2]:
                    badge = True

            # Condition 2: donated to more than 5 projects
            if len(unique_projects) > 5:
                badge = True

            admin_data.append({
                "email": email,
                "donations": donations,
                "badge": badge
            })

        conn.close()
        return render_template("donation_history.html",
                               admin_view=True,
                               admin_data=admin_data)

    else:
        # Normal user view
        c.execute("SELECT id FROM users WHERE email=?", (session["user"],))
        user_id = c.fetchone()[0]

        c.execute('''
            SELECT projects.name, donations.amount, projects.goal
            FROM donations
            JOIN projects ON donations.project_id = projects.id
            WHERE donations.user_id=?
        ''', (user_id,))
        donations = c.fetchall()

        unique_projects = set()
        badge = False

        for d in donations:
            unique_projects.add(d[0])

            if d[1] >= 0.5 * d[2]:
                badge = True

        if len(unique_projects) > 5:
            badge = True

        conn.close()

        return render_template("donation_history.html",
                               admin_view=False,
                               donations=donations,
                               badge=badge)


@app.route("/add_update/<int:id>", methods=["POST"])
def add_update(id):
    if session.get("role") != "admin":
        return redirect("/dashboard")

    description = request.form["description"]
    amount_used = int(request.form["amount"])

    conn = get_db()
    c = conn.cursor()

    c.execute("INSERT INTO updates (project_id, description, amount_used) VALUES (?, ?, ?)",
              (id, description, amount_used))

    conn.commit()
    conn.close()

    return redirect("/project/" + str(id))

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    init_db()
    app.run(debug=True)