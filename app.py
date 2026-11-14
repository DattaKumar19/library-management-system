import os
import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-only-secret-key")
DATABASE_URL = os.environ.get("DATABASE_URL")
_db_initialized = False


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Configure your PostgreSQL connection string.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def log_activity(conn, action, book_name):
    conn.execute(
        "INSERT INTO activity_logs (action, book_name) VALUES (%s, %s)",
        (action, book_name)
    )


def create_tables():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                author TEXT NOT NULL,
                status TEXT DEFAULT 'Available'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id BIGSERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                book_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id BIGSERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS borrow_requests (
                id BIGSERIAL PRIMARY KEY,
                student_id BIGINT NOT NULL,
                book_id TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")

        conn.execute(
            """
            INSERT INTO admins (username, password)
            VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            ("admin", generate_password_hash(admin_password))
        )


@app.before_request
def initialize_database():
    global _db_initialized

    if not _db_initialized:
        create_tables()
        _db_initialized = True


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function
        

@app.route('/')
@admin_required
def home():
    return render_template('index.html')


@app.route('/api/books', methods=['POST'])
@admin_required
def add_book():
    data = request.get_json(silent=True) or {}
    book_id = str(data.get('id', '')).strip()
    name = str(data.get('name', '')).strip()
    author = str(data.get('author', '')).strip()
    if not book_id or not name or not author:
        return jsonify({"message": "All fields are required!"}), 400
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO books (id, name, author) VALUES (%s, %s, %s)",
                (book_id, name, author)
            )
            log_activity(conn, "Added", name)
        return jsonify({"message": "Book added successfully!"}), 201
    except UniqueViolation:
        return jsonify({"message": "Book ID already exists!"}), 409


@app.route('/api/books', methods=['GET'])
@admin_required
def view_books():
    with get_db() as conn:
        books = conn.execute("SELECT * FROM books ORDER BY name").fetchall()
    return jsonify([dict(book) for book in books])


@app.route('/api/books/search', methods=['GET'])
@admin_required
def search_books():
    pattern = f"%{request.args.get('q', '').strip()}%"
    with get_db() as conn:
        books = conn.execute(
            """
            SELECT * FROM books
            WHERE id LIKE %s OR name LIKE %s OR author LIKE %s
            ORDER BY name
            """,
            (pattern, pattern, pattern)
        ).fetchall()
    return jsonify([dict(book) for book in books])


@app.route('/api/books/<book_id>/borrow', methods=['POST'])
@admin_required
def borrow_book(book_id):
    with get_db() as conn:
        book = conn.execute("SELECT * FROM books WHERE id = %s", (book_id,)).fetchone()
        if book is None:
            return jsonify({"message": "Book not found!"}), 404
        if book['status'] == 'Borrowed':
            return jsonify({"message": "Book is already borrowed!"}), 409
        conn.execute("UPDATE books SET status = 'Borrowed' WHERE id = %s", (book_id,))
        log_activity(conn, "Borrowed", book['name'])
    return jsonify({"message": "Book borrowed successfully!"})


@app.route('/api/books/<book_id>/return', methods=['POST'])
@admin_required
def return_book(book_id):
    with get_db() as conn:
        book = conn.execute("SELECT * FROM books WHERE id = %s", (book_id,)).fetchone()
        if book is None:
            return jsonify({"message": "Book not found!"}), 404
        if book['status'] == 'Available':
            return jsonify({"message": "Book is already available!"}), 409
        conn.execute("UPDATE books SET status = 'Available' WHERE id = %s", (book_id,))
        log_activity(conn, "Returned", book['name'])
    return jsonify({"message": "Book returned successfully!"})


@app.route('/api/stats', methods=['GET'])
@admin_required
def dashboard_stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) AS count FROM books").fetchone()['count']
        available = conn.execute(
            "SELECT COUNT(*) AS count FROM books WHERE status = 'Available'"
        ).fetchone()['count']
        borrowed = conn.execute(
            "SELECT COUNT(*) AS count FROM books WHERE status = 'Borrowed'"
        ).fetchone()['count']
    return jsonify({"total": total, "available": available, "borrowed": borrowed})
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        with get_db() as conn:
            admin = conn.execute(
                "SELECT * FROM admins WHERE username = %s", (username,)
            ).fetchone()
        if admin and check_password_hash(admin['password'], password):
            session['admin'] = username
            return redirect(url_for('home'))
        return render_template('auth.html', error="Invalid username or password!", active_tab='admin')
    return render_template('auth.html', active_tab='admin')
@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not all([full_name, email, username, password, confirm_password]):
            return render_template('signup.html', error="Please fill in all fields.")
        if password != confirm_password:
            return render_template('signup.html', error="Passwords do not match.")
        if len(password) < 8:
            return render_template('signup.html', error="Password must be at least 8 characters.")
        try:
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO students (full_name, email, username, password)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (full_name, email, username, generate_password_hash(password))
                )
            return render_template('signup.html', success="Account created successfully! You can now log in.")
        except UniqueViolation:
            return render_template('signup.html', error="Email or username already exists.")
    return render_template('signup.html')
@app.route('/student-login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        with get_db() as conn:
            student = conn.execute(
                "SELECT * FROM students WHERE username = %s", (username,)
            ).fetchone()
        if student and check_password_hash(student['password'], password):
            session['student_id'] = student['id']
            session['student_name'] = student['full_name']
            return redirect(url_for('student_dashboard'))
        return render_template('student-login.html', error="Invalid username or password.")
    return render_template('student-login.html')
@app.route('/student')
def student_dashboard():
    if 'student_id' not in session:
        return redirect('/student-login')
    student_id = session['student_id']
    with get_db() as conn:
        available_count = conn.execute(
            "SELECT COUNT(*) AS count FROM books WHERE status = 'Available'"
        ).fetchone()['count']
        pending_count = conn.execute(
            "SELECT COUNT(*) AS count FROM borrow_requests WHERE student_id = %s AND status = 'Pending'",
            (student_id,)
        ).fetchone()['count']
        approved_count = conn.execute(
            "SELECT COUNT(*) AS count FROM borrow_requests WHERE student_id = %s AND status = 'Approved'",
            (student_id,)
        ).fetchone()['count']
        rejected_count = conn.execute(
            "SELECT COUNT(*) AS count FROM borrow_requests WHERE student_id = %s AND status = 'Rejected'",
            (student_id,)
        ).fetchone()['count']
    return render_template(
        'student.html',
        student_name=session['student_name'],
        available_count=available_count,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count
    )
@app.route('/student-logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    return redirect('/student-login')


@app.route('/student/books')
def student_books():
    if 'student_id' not in session:
        return redirect('/student-login')
    search = request.args.get('search', '').strip()
    pattern = f'%{search}%'
    with get_db() as conn:
        books = conn.execute(
            """
            SELECT * FROM books
            WHERE status = 'Available'
              AND (name LIKE %s OR author LIKE %s OR id LIKE %s)
            ORDER BY name
            """,
            (pattern, pattern, pattern)
        ).fetchall()
    return render_template('student-books.html', books=books, search=search)
@app.route('/student/request-book/<book_id>', methods=['POST'])
def request_book(book_id):
    if 'student_id' not in session:
        return redirect('/student-login')
    student_id = session['student_id']
    with get_db() as conn:
        book = conn.execute(
            "SELECT * FROM books WHERE id = %s AND status = 'Available'",
            (book_id,)
        ).fetchone()
        if not book:
            return redirect('/student/books')
        existing = conn.execute(
            """
            SELECT id FROM borrow_requests
            WHERE student_id = %s AND book_id = %s AND status = 'Pending'
            """,
            (student_id, book_id)
        ).fetchone()
        if existing:
            return redirect('/student/books?message=already')
        conn.execute(
            "INSERT INTO borrow_requests (student_id, book_id) VALUES (%s, %s)",
            (student_id, book_id)
        )
    return redirect('/student/books?message=requested')
@app.route('/admin/requests')
@admin_required
def admin_requests():
    with get_db() as conn:
        requests_list = conn.execute(
            """
            SELECT
                borrow_requests.id,
                students.full_name,
                books.id AS book_id,
                books.name AS book_name,
                books.author,
                borrow_requests.status,
                borrow_requests.requested_at
            FROM borrow_requests
            JOIN students ON borrow_requests.student_id = students.id
            JOIN books ON borrow_requests.book_id = books.id
            ORDER BY borrow_requests.requested_at DESC
            """
        ).fetchall()
    return render_template('admin-requests.html', requests=requests_list)
@app.route('/admin/request/<int:request_id>/<action>', methods=['POST'])
@admin_required
def update_request(request_id, action):
    if action not in ['approve', 'reject']:
        return "Invalid action", 400
    with get_db() as conn:
        borrow_request = conn.execute(
            "SELECT * FROM borrow_requests WHERE id = %s AND status = 'Pending'",
            (request_id,)
        ).fetchone()
        if not borrow_request:
            return redirect('/admin/requests')
        if action == 'approve':
            book = conn.execute(
                "SELECT * FROM books WHERE id = %s AND status = 'Available'",
                (borrow_request['book_id'],)
            ).fetchone()
            if not book:
                return redirect('/admin/requests')
            conn.execute(
                "UPDATE books SET status = 'Borrowed' WHERE id = %s",
                (borrow_request['book_id'],)
            )
            conn.execute(
                "UPDATE borrow_requests SET status = 'Approved' WHERE id = %s",
                (request_id,)
            )
            log_activity(conn, "Borrowed", book['name'])
        else:
            conn.execute(
                "UPDATE borrow_requests SET status = 'Rejected' WHERE id = %s",
                (request_id,)
            )
    return redirect('/admin/requests')
@app.route('/student/my-requests')
def student_my_requests():
    if 'student_id' not in session:
        return redirect('/student-login')
    with get_db() as conn:
        requests_list = conn.execute(
            """
            SELECT
                borrow_requests.id,
                books.name AS book_name,
                books.author,
                borrow_requests.status,
                borrow_requests.requested_at
            FROM borrow_requests
            JOIN books ON borrow_requests.book_id = books.id
            WHERE borrow_requests.student_id = %s
            ORDER BY borrow_requests.requested_at DESC
            """,
            (session['student_id'],)
        ).fetchall()
    return render_template('student-requests.html', requests=requests_list)

@app.route('/api/activity', methods=['GET'])
@admin_required
def get_activity():
    with get_db() as conn:
        activities = conn.execute(
            """
            SELECT action, book_name, created_at
            FROM activity_logs
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()
    return jsonify([dict(row) for row in activities])
if __name__ == '__main__':
    create_tables()
    app.run(debug=True)


