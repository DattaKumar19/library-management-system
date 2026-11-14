from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import os
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-only-secret-key")
# --------------------------------
# DATABASE CONNECTION
# --------------------------------

def get_db():
    conn = sqlite3.connect("library.db")
    conn.row_factory = sqlite3.Row
    return conn
def log_activity(conn, action, book_name):
    conn.execute(
        """
        INSERT INTO activity_logs (action, book_name)
        VALUES (?, ?)
        """,
        (action, book_name)
    )


# --------------------------------
# CREATE DATABASE TABLE
# --------------------------------

def create_table():
    conn = get_db()

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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            book_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
      # NEW BORROW REQUESTS TABLE
    conn.execute("""
        CREATE TABLE IF NOT EXISTS borrow_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            book_id TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
 # ADD THE NEW ADMIN TABLE FUNCTION BELOW
def create_admin_table():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    admin = conn.execute(
        "SELECT * FROM admins WHERE username = ?", ("admin",)
    ).fetchone()

    if admin is None:
        hashed_password = generate_password_hash("Admin@123")
        conn.execute(
            "INSERT INTO admins (username, password) VALUES (?, ?)",
            ("admin", hashed_password)
        )

    conn.commit()
    conn.close()
    # CREATE STUDENT TABLE
def create_student_table():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()  
    # ADMIN LOGIN PROTECTION
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
    # --------------------------------
# HOME PAGE
# --------------------------------

@app.route('/')
@admin_required
def home():
    return render_template('index.html')

# --------------------------------
# ADD BOOK
# --------------------------------

@app.route('/api/books', methods=['POST'])
def add_book():

    data = request.get_json(silent=True) or {}

    book_id = str(data.get('id', '')).strip()
    name = str(data.get('name', '')).strip()
    author = str(data.get('author', '')).strip()

    if not book_id or not name or not author:
        return jsonify({
            "message": "All fields are required!"
        }), 400

    conn = get_db()

    try:
        conn.execute(
            """
            INSERT INTO books (id, name, author)
            VALUES (?, ?, ?)
            """,
            (book_id, name, author)
        )
        log_activity(conn, "Added", name)
        conn.commit()

        return jsonify({
            "message": "Book added successfully!"
        }), 201

    except sqlite3.IntegrityError:
        return jsonify({
            "message": "Book ID already exists!"
        }), 409

    finally:
        conn.close()


# --------------------------------
# VIEW ALL BOOKS
# --------------------------------

@app.route('/api/books', methods=['GET'])
def view_books():

    conn = get_db()

    try:
        books = conn.execute(
            "SELECT * FROM books ORDER BY name"
        ).fetchall()

        return jsonify([
            dict(book) for book in books
        ])

    finally:
        conn.close()


# --------------------------------
# SEARCH BOOKS
# --------------------------------

@app.route('/api/books/search', methods=['GET'])
def search_books():

    keyword = request.args.get('q', '').strip()

    conn = get_db()

    try:
        books = conn.execute(
            """
            SELECT * FROM books
            WHERE id LIKE ?
            OR name LIKE ?
            OR author LIKE ?
            ORDER BY name
            """,
            (
                f'%{keyword}%',
                f'%{keyword}%',
                f'%{keyword}%'
            )
        ).fetchall()

        return jsonify([
            dict(book) for book in books
        ])

    finally:
        conn.close()


# --------------------------------
# BORROW BOOK
# --------------------------------

@app.route('/api/books/<book_id>/borrow', methods=['POST'])
def borrow_book(book_id):

    conn = get_db()

    try:
        book = conn.execute(
            "SELECT * FROM books WHERE id = ?",
            (book_id,)
        ).fetchone()

        if book is None:
            return jsonify({
                "message": "Book not found!"
            }), 404

        if book['status'] == 'Borrowed':
            return jsonify({
                "message": "Book is already borrowed!"
            }), 409

        conn.execute(
            """
            UPDATE books
            SET status = 'Borrowed'
            WHERE id = ?
            """,
            (book_id,)
        )
        log_activity(conn, "Borrowed", book['name'])
        conn.commit()

        return jsonify({
            "message": "Book borrowed successfully!"
        })

    finally:
        conn.close()


# --------------------------------
# RETURN BOOK
# --------------------------------

@app.route('/api/books/<book_id>/return', methods=['POST'])
def return_book(book_id):

    conn = get_db()

    try:
        book = conn.execute(
            "SELECT * FROM books WHERE id = ?",
            (book_id,)
        ).fetchone()

        if book is None:
            return jsonify({
                "message": "Book not found!"
            }), 404

        if book['status'] == 'Available':
            return jsonify({
                "message": "Book is already available!"
            }), 409

        conn.execute(
            """
            UPDATE books
            SET status = 'Available'
            WHERE id = ?
            """,
            (book_id,)
        )
        log_activity(conn, "Returned", book['name'])
        conn.commit()

        return jsonify({
            "message": "Book returned successfully!"
        })

    finally:
        conn.close()
# DASHBOARD STATISTICS

@app.route('/api/stats', methods=['GET'])
def dashboard_stats():

    conn = get_db()

    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM books"
        ).fetchone()[0]

        available = conn.execute(
            "SELECT COUNT(*) FROM books WHERE status = 'Available'"
        ).fetchone()[0]

        borrowed = conn.execute(
            "SELECT COUNT(*) FROM books WHERE status = 'Borrowed'"
        ).fetchone()[0]

        return jsonify({
            "total": total,
            "available": available,
            "borrowed": borrowed
        })

    finally:
        conn.close()
# ADMIN LOGIN

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        conn = get_db()

        admin = conn.execute(
            "SELECT * FROM admins WHERE username = ?",
            (username,)
        ).fetchone()

        conn.close()

        if admin and check_password_hash(admin['password'], password):
            session['admin'] = username
            return redirect(url_for('home'))

        return render_template(
            'auth.html',
            error="Invalid username or password!",
            active_tab='admin'
        )

    return render_template('auth.html', active_tab='admin')


# ADMIN LOGOUT

@app.route('/logout')
def logout():

    session.pop('admin', None)

    return redirect(url_for('login'))

# --------------------------------
# RUN FLASK SERVER
# --------------------------------
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

        conn = get_db()

        try:
            hashed_password = generate_password_hash(password)

            conn.execute("""
                INSERT INTO students (full_name, email, username, password)
                VALUES (?, ?, ?, ?)
            """, (full_name, email, username, hashed_password))

            conn.commit()
            return render_template(
                'signup.html',
                success="Account created successfully! Student login will be available soon."
            )

        except sqlite3.IntegrityError:
            return render_template(
                'signup.html',
                error="Email or username already exists."
            )

        finally:
            conn.close()

    return render_template('signup.html')
# STUDENT LOGIN
@app.route('/student-login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        conn = get_db()
        student = conn.execute(
            "SELECT * FROM students WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if student and check_password_hash(student['password'], password):
            session['student_id'] = student['id']
            session['student_name'] = student['full_name']
            return redirect('/student')

        return render_template(
            'student-login.html',
            error="Invalid username or password."
        )

    return render_template('student-login.html')


# STUDENT DASHBOARD
@app.route('/student')
def student_dashboard():
    if 'student_id' not in session:
        return redirect('/student-login')

    conn = get_db()

    available_count = conn.execute(
        "SELECT COUNT(*) FROM books WHERE status = 'Available'"
    ).fetchone()[0]

    pending_count = conn.execute("""
        SELECT COUNT(*) FROM borrow_requests
        WHERE student_id = ? AND status = 'Pending'
    """, (session['student_id'],)).fetchone()[0]

    approved_count = conn.execute("""
        SELECT COUNT(*) FROM borrow_requests
        WHERE student_id = ? AND status = 'Approved'
    """, (session['student_id'],)).fetchone()[0]

    rejected_count = conn.execute("""
        SELECT COUNT(*) FROM borrow_requests
        WHERE student_id = ? AND status = 'Rejected'
    """, (session['student_id'],)).fetchone()[0]

    conn.close()

    return render_template(
        'student.html',
        student_name=session['student_name'],
        available_count=available_count,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count
    )

# STUDENT LOGOUT
@app.route('/student-logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    return redirect('/student-login')

# STUDENT VIEW AVAILABLE BOOKS
@app.route('/student/books')
def student_books():
    if 'student_id' not in session:
        return redirect('/student-login')

    search = request.args.get('search', '').strip()

    conn = get_db()

    books = conn.execute("""
        SELECT * FROM books
        WHERE status = 'Available'
        AND (
            name LIKE ?
            OR author LIKE ?
            OR id LIKE ?
        )
        ORDER BY name
    """, (
        f'%{search}%',
        f'%{search}%',
        f'%{search}%'
    )).fetchall()

    conn.close()

    return render_template(
        'student-books.html',
        books=books,
        search=search
    )

@app.route('/student/request-book/<book_id>', methods=['POST'])
def request_book(book_id):

    if 'student_id' not in session:
        return redirect('/student-login')

    conn = get_db()

    # Check whether the book exists and is available
    book = conn.execute(
        "SELECT * FROM books WHERE id = ? AND status = 'Available'",
        (book_id,)
    ).fetchone()

    if not book:
        conn.close()
        return redirect('/student/books')

    # Prevent duplicate pending requests
    existing = conn.execute("""
        SELECT id FROM borrow_requests
        WHERE student_id = ? AND book_id = ?
        AND status = 'Pending'
    """, (session['student_id'], book_id)).fetchone()

    if existing:
        conn.close()
        return redirect('/student/books?message=already')

    # Save the request
    conn.execute("""
        INSERT INTO borrow_requests (student_id, book_id)
        VALUES (?, ?)
    """, (session['student_id'], book_id))

    conn.commit()
    conn.close()

    return redirect('/student/books?message=requested')

# ADMIN VIEW BORROWING REQUESTS
@app.route('/admin/requests')
@admin_required
def admin_requests():

    conn = get_db()

    requests_list = conn.execute("""
        SELECT
            borrow_requests.id,
            students.full_name,
            books.id AS book_id,
            books.name AS book_name,
            books.author,
            borrow_requests.status,
            borrow_requests.requested_at
        FROM borrow_requests
        JOIN students
            ON borrow_requests.student_id = students.id
        JOIN books
            ON borrow_requests.book_id = books.id
        ORDER BY borrow_requests.requested_at DESC
    """).fetchall()

    conn.close()

    return render_template(
        'admin-requests.html',
        requests=requests_list
    )


# ADMIN APPROVE OR REJECT REQUEST
@app.route('/admin/request/<int:request_id>/<action>', methods=['POST'])
@admin_required
def update_request(request_id, action):

    if action not in ['approve', 'reject']:
        return "Invalid action", 400

    conn = get_db()

    borrow_request = conn.execute("""
        SELECT * FROM borrow_requests
        WHERE id = ? AND status = 'Pending'
    """, (request_id,)).fetchone()

    if not borrow_request:
        conn.close()
        return redirect('/admin/requests')

    if action == 'approve':

        book = conn.execute("""
            SELECT * FROM books
            WHERE id = ? AND status = 'Available'
        """, (borrow_request['book_id'],)).fetchone()

        if not book:
            conn.close()
            return redirect('/admin/requests')

        conn.execute("""
            UPDATE books
            SET status = 'Borrowed'
            WHERE id = ?
        """, (borrow_request['book_id'],))

        conn.execute("""
            UPDATE borrow_requests
            SET status = 'Approved'
            WHERE id = ?
        """, (request_id,))

        log_activity(conn, "Borrowed", book['name'])

    else:

        conn.execute("""
            UPDATE borrow_requests
            SET status = 'Rejected'
            WHERE id = ?
        """, (request_id,))

    conn.commit()
    conn.close()

    return redirect('/admin/requests')

# STUDENT BORROWING REQUESTS
@app.route('/student/my-requests')
def student_my_requests():
    if 'student_id' not in session:
        return redirect('/student-login')

    conn = get_db()

    requests_list = conn.execute("""
        SELECT
            borrow_requests.id,
            books.name AS book_name,
            books.author,
            borrow_requests.status,
            borrow_requests.requested_at
        FROM borrow_requests
        JOIN books
            ON borrow_requests.book_id = books.id
        WHERE borrow_requests.student_id = ?
        ORDER BY borrow_requests.requested_at DESC
    """, (session['student_id'],)).fetchall()

    conn.close()

    return render_template(
        'student-requests.html',
        requests=requests_list
    )

if __name__ == '__main__':
    create_table()
    create_admin_table()
    create_student_table()
    print(app.url_map)
    app.run(debug=True)
@app.route('/api/activity', methods=['GET'])
@admin_required
def get_activity():
    conn = get_db()

    try:
        activities = conn.execute("""
            SELECT action, book_name, created_at
            FROM activity_logs
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

        return jsonify([dict(row) for row in activities])

    finally:
        conn.close()  
