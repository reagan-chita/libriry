from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin

import os


# ------------------- APP SETUP -------------------
app = Flask(__name__)
app.secret_key = "secret123"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ------------------- MODELS -------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='user')

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    year = db.Column(db.Integer)
    isbn = db.Column(db.String(20), unique=True)
    copies = db.Column(db.Integer, default=1)
    borrowed = db.Column(db.Integer, default=0)

class Borrow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    borrow_date = db.Column(db.Date, nullable=False)

    # relationships
    user = db.relationship("User", backref="borrows")
    book = db.relationship("Book", backref="borrows")

# ------------------- LOGIN MANAGER -------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ------------------- ROUTES -------------------
@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect("/dashboard")
    return redirect("/login")

# --------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role", "user")
        if not all([name, email, password]):
            flash("All fields are required!", "error")
            return redirect("/register")
        user = User(name=name, email=email, password=generate_password_hash(password), role=role)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful!", "success")
        return redirect("/login")
    return render_template("register.html")

# --------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect("/dashboard")
        flash("Invalid email or password", "error")
    return render_template("login.html")

# --------- DASHBOARD ----------
@app.route("/dashboard")
@login_required
def dashboard():

    total_books = Book.query.count()
    borrowed_books = Borrow.query.count()
    total_users = User.query.count()

    # calculate available books
    total_copies = db.session.query(db.func.sum(Book.copies)).scalar() or 0
    available_books = total_copies - borrowed_books

    return render_template(
        "dashboard.html",
        name=current_user.name,
        total_books=total_books,
        borrowed_books=borrowed_books,
        total_users=total_users,
        available_books=available_books
    )
# --------- LOGOUT ----------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# --------- BOOK ROUTES ----------
@app.route("/books")
@login_required
def books():
    all_books = Book.query.all()

    # update borrowed count
    for book in all_books:
        book.borrowed = Borrow.query.filter_by(book_id=book.id).count()
    db.session.commit()

    # show only books borrowed by current user
    borrowed_books = Borrow.query.filter_by(user_id=current_user.id)\
                                 .order_by(Borrow.borrow_date.desc())\
                                 .all()

    return render_template(
        "books.html",
        books=all_books,
        borrowed_books=borrowed_books,
        name=current_user.name
    )

@app.route("/books/add", methods=["POST"])
@login_required
def add_book():
    if current_user.role != 'Admin':
        flash("Unauthorized", "error")
        return redirect("/books")
    book = Book(
        title=request.form.get("title"),
        author=request.form.get("author"),
        category=request.form.get("category"),
        year=int(request.form.get("year")),
        isbn=request.form.get("isbn"),
        copies=int(request.form.get("copies"))
    )
    db.session.add(book)
    db.session.commit()
    return redirect("/books")

@app.route("/books/edit/<int:id>", methods=["POST"])
@login_required
def edit_book(id):
    if current_user.role != 'Admin':
        flash("Unauthorized", "error")
        return redirect("/books")
    book = Book.query.get_or_404(id)
    book.title = request.form.get("title")
    book.author = request.form.get("author")
    book.category = request.form.get("category")
    book.year = int(request.form.get("year"))
    book.isbn = request.form.get("isbn")
    book.copies = int(request.form.get("copies"))
    db.session.commit()
    return redirect("/books")

@app.route("/books/delete/<int:id>", methods=["POST"])
@login_required
def delete_book(id):
    if current_user.role != 'Admin':
        flash("Unauthorized", "error")
        return redirect("/books")
    book = Book.query.get_or_404(id)
    db.session.delete(book)
    db.session.commit()
    return redirect("/books")

@app.route("/books/borrow", methods=["POST"])
@login_required
def borrow_book():
    book_id = int(request.form.get("id"))
    borrow_date_str = request.form.get("borrow_date")
    borrow_date = datetime.strptime(borrow_date_str, "%Y-%m-%d").date()
    book = Book.query.get_or_404(book_id)
    if book.copies > book.borrowed:
        borrow_record = Borrow(book_id=book.id, user_id=current_user.id, borrow_date=borrow_date)
        db.session.add(borrow_record)
        db.session.commit()
    return redirect(url_for("books"))

@app.route("/books/return/<int:borrow_id>", methods=["POST"])
@login_required
def return_book(borrow_id):
    borrow_record = Borrow.query.get_or_404(borrow_id)
    book = Book.query.get(borrow_record.book_id)
    if book.borrowed > 0:
        book.borrowed -= 1
    db.session.delete(borrow_record)
    db.session.commit()
    return redirect(url_for("books"))

# --------- BORROWED BOOKS PAGE ----------
@app.route("/borrowed")
@login_required
def borrowed_books():
    borrowed = Borrow.query.order_by(Borrow.borrow_date.desc()).all()
    borrowed_info = []
    for b in borrowed:
        book = Book.query.get(b.book_id)
        user = User.query.get(b.user_id)
        borrowed_info.append({
            "borrow_id": b.id,
            "book_title": book.title,
            "book_author": book.author,
            "borrower": user.name,
            "borrow_date": b.borrow_date
        })
    return render_template("borrowed.html", borrowed=borrowed_info, name=current_user.name)

# --------- USER ROUTES ----------
@app.route("/users")
@login_required
def users():
    all_users = User.query.all()
    return render_template("users.html", users=all_users, name=current_user.name)

@app.route("/users/add", methods=["POST"])
@login_required
def add_user():
    if current_user.role != 'Admin':
        flash("Unauthorized", "error")
        return redirect("/users")
    name = request.form.get("name")
    email = request.form.get("email")
    password = request.form.get("password")
    role = request.form.get("role", "user")
    if not all([name, email, password]):
        flash("All fields are required!", "error")
        return redirect("/users")
    user = User(name=name, email=email, password=generate_password_hash(password), role=role)
    db.session.add(user)
    db.session.commit()
    flash("User added successfully!", "success")
    return redirect("/users")

@app.route("/users/edit/<int:id>", methods=["POST"])
@login_required
def edit_user(id):
    if current_user.role != 'Admin':
        flash("Unauthorized", "error")
        return redirect("/users")
    user = User.query.get_or_404(id)
    user.name = request.form.get("name")
    user.email = request.form.get("email")
    user.role = request.form.get("role")
    password = request.form.get("password")
    if password:
        user.password = generate_password_hash(password)
    db.session.commit()
    flash("User updated successfully!", "success")
    return redirect("/users")

@app.route("/users/reset_password/<int:id>", methods=["POST"])
@login_required
def reset_password(id):
    if current_user.role != 'Admin':
        flash("Unauthorized", "error")
        return redirect("/users")
    user = User.query.get_or_404(id)
    new_password = request.form.get("new_password")
    if not new_password:
        flash("Password is required!", "error")
        return redirect("/users")
    user.password = generate_password_hash(new_password)
    db.session.commit()
    flash(f"Password for {user.name} reset successfully!", "success")
    return redirect("/users")

@app.route("/users/delete/<int:id>", methods=["POST"])
@login_required
def delete_user(id):
    if current_user.role != 'Admin':
        flash("Unauthorized", "error")
        return redirect("/users")
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.name} deleted successfully!", "success")
    return redirect("/users")


    # --------- REPORTS ----------
@app.route("/reports")
@login_required
def reports():

    # Allow only admin
    if current_user.role != "Admin":
        flash("Access denied. Admins only.", "error")
        return redirect("/dashboard")

    total_books = Book.query.count()
    total_borrowed = Borrow.query.count()
    total_available = total_books - total_borrowed
    borrowed_list = Borrow.query.order_by(Borrow.borrow_date.desc()).all()

    return render_template(
        "reports.html",
        total_books=total_books,
        total_borrowed=total_borrowed,
        total_available=total_available,
        borrowed_list=borrowed_list,
        name=current_user.name
    )


# ------------------- MAIN -------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)