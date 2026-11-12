import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, SelectField, TextAreaField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "CHANGE-ME-before-deployment")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///hadaf_bartar.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "برای ادامه ابتدا وارد حساب خود شوید."

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    grade = db.Column(db.Integer, nullable=True)
    role = db.Column(db.String(20), default="student", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_until = db.Column(db.DateTime, nullable=True)

    @property
    def is_premium(self):
        return self.subscription_until is not None and self.subscription_until > datetime.utcnow()

class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, default="")
    body = db.Column(db.Text, default="")
    premium = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.Integer, nullable=False)
    duration_minutes = db.Column(db.Integer, default=30)
    premium = db.Column(db.Boolean, default=False)
    questions = db.relationship("Question", backref="exam", cascade="all, delete-orphan")

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(300), nullable=False)
    option_b = db.Column(db.String(300), nullable=False)
    option_c = db.Column(db.String(300), nullable=False)
    option_d = db.Column(db.String(300), nullable=False)
    correct = db.Column(db.String(1), nullable=False)

class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")
    exam = db.relationship("Exam")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

class RegisterForm(FlaskForm):
    name = StringField("نام و نام خانوادگی", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("ایمیل", validators=[DataRequired(), Email(), Length(max=160)])
    grade = SelectField("پایه تحصیلی", choices=[("7","هفتم"),("8","هشتم"),("9","نهم")], validators=[DataRequired()])
    password = PasswordField("رمز عبور", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField("تکرار رمز عبور", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("ساخت حساب")

class LoginForm(FlaskForm):
    email = StringField("ایمیل", validators=[DataRequired(), Email()])
    password = PasswordField("رمز عبور", validators=[DataRequired()])
    submit = SubmitField("ورود")

class LessonForm(FlaskForm):
    title = StringField("عنوان درس", validators=[DataRequired(), Length(max=180)])
    subject = StringField("نام درس", validators=[DataRequired(), Length(max=100)])
    grade = SelectField("پایه", choices=[("7","هفتم"),("8","هشتم"),("9","نهم")], validators=[DataRequired()])
    description = TextAreaField("توضیح کوتاه")
    body = TextAreaField("محتوای درس")
    premium = SelectField("دسترسی", choices=[("0","رایگان"),("1","ویژه اشتراک طلایی")])
    submit = SubmitField("ذخیره درس")

class ExamForm(FlaskForm):
    title = StringField("عنوان آزمون", validators=[DataRequired(), Length(max=180)])
    subject = StringField("نام درس", validators=[DataRequired(), Length(max=100)])
    grade = SelectField("پایه", choices=[("7","هفتم"),("8","هشتم"),("9","نهم")], validators=[DataRequired()])
    duration_minutes = IntegerField("مدت آزمون (دقیقه)", validators=[DataRequired(), NumberRange(min=1, max=240)])
    premium = SelectField("دسترسی", choices=[("0","رایگان"),("1","ویژه اشتراک طلایی")])
    submit = SubmitField("ساخت آزمون")

class QuestionForm(FlaskForm):
    prompt = TextAreaField("متن سؤال", validators=[DataRequired()])
    option_a = StringField("گزینه الف", validators=[DataRequired()])
    option_b = StringField("گزینه ب", validators=[DataRequired()])
    option_c = StringField("گزینه ج", validators=[DataRequired()])
    option_d = StringField("گزینه د", validators=[DataRequired()])
    correct = SelectField("پاسخ صحیح", choices=[("A","الف"),("B","ب"),("C","ج"),("D","د")])
    submit = SubmitField("افزودن سؤال")

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

@app.context_processor
def inject_globals():
    return {"now": datetime.utcnow()}

@app.route("/")
def index():
    lessons = Lesson.query.order_by(Lesson.created_at.desc()).limit(6).all()
    exams = Exam.query.order_by(Exam.id.desc()).limit(4).all()
    return render_template("index.html", lessons=lessons, exams=exams)

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash("این ایمیل قبلاً ثبت شده است.", "error")
        else:
            user = User(name=form.name.data.strip(), email=email, grade=int(form.grade.data),
                        password_hash=generate_password_hash(form.password.data))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("حساب شما ساخته شد. خوش آمدید!", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", form=form, title="ثبت‌نام", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            return redirect(url_for("admin") if user.role == "admin" else url_for("dashboard"))
        flash("ایمیل یا رمز عبور درست نیست.", "error")
    return render_template("auth.html", form=form, title="ورود", mode="login")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    lessons = Lesson.query.filter_by(grade=current_user.grade).order_by(Lesson.id.desc()).all()
    exams = Exam.query.filter_by(grade=current_user.grade).order_by(Exam.id.desc()).all()
    attempts = Attempt.query.filter_by(user_id=current_user.id).order_by(Attempt.created_at.desc()).all()
    return render_template("dashboard.html", lessons=lessons, exams=exams, attempts=attempts)

@app.route("/lessons")
@login_required
def lessons():
    grade = request.args.get("grade", type=int) or current_user.grade
    if grade not in (7, 8, 9):
        grade = current_user.grade or 7
    items = Lesson.query.filter_by(grade=grade).order_by(Lesson.id.desc()).all()
    return render_template("lessons.html", lessons=items, grade=grade)

@app.route("/lesson/<int:lesson_id>")
@login_required
def lesson_detail(lesson_id):
    lesson = db.get_or_404(Lesson, lesson_id)
    if lesson.premium and not current_user.is_premium and current_user.role != "admin":
        flash("این درس مخصوص اشتراک طلایی است.", "error")
        return redirect(url_for("plans"))
    return render_template("lesson_detail.html", lesson=lesson)

@app.route("/exams")
@login_required
def exams():
    grade = request.args.get("grade", type=int) or current_user.grade
    if grade not in (7, 8, 9):
        grade = current_user.grade or 7
    items = Exam.query.filter_by(grade=grade).order_by(Exam.id.desc()).all()
    return render_template("exams.html", exams=items, grade=grade)

@app.route("/exam/<int:exam_id>", methods=["GET", "POST"])
@login_required
def take_exam(exam_id):
    exam = db.get_or_404(Exam, exam_id)
    if exam.premium and not current_user.is_premium and current_user.role != "admin":
        flash("این آزمون مخصوص اشتراک طلایی است.", "error")
        return redirect(url_for("plans"))
    questions = Question.query.filter_by(exam_id=exam.id).all()
    if request.method == "POST":
        if not questions:
            flash("این آزمون هنوز سؤالی ندارد.", "error")
            return redirect(url_for("exams"))
        score = sum(1 for q in questions if request.form.get(str(q.id)) == q.correct)
        attempt = Attempt(user_id=current_user.id, exam_id=exam.id, score=score, total=len(questions))
        db.session.add(attempt)
        db.session.commit()
        return render_template("result.html", attempt=attempt)
    return render_template("take_exam.html", exam=exam, questions=questions)

@app.route("/plans")
def plans():
    return render_template("plans.html")

@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html",
        users=User.query.order_by(User.created_at.desc()).all(),
        lessons=Lesson.query.order_by(Lesson.id.desc()).all(),
        exams=Exam.query.order_by(Exam.id.desc()).all(),
        attempts=Attempt.query.order_by(Attempt.created_at.desc()).limit(20).all())

@app.route("/admin/lesson/new", methods=["GET", "POST"])
@admin_required
def new_lesson():
    form = LessonForm()
    if form.validate_on_submit():
        item = Lesson(title=form.title.data, subject=form.subject.data, grade=int(form.grade.data),
                      description=form.description.data, body=form.body.data, premium=form.premium.data == "1")
        db.session.add(item); db.session.commit()
        flash("درس با موفقیت اضافه شد.", "success")
        return redirect(url_for("admin"))
    return render_template("form.html", form=form, title="افزودن درس")

@app.route("/admin/lesson/<int:item_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_lesson(item_id):
    item = db.get_or_404(Lesson, item_id)
    form = LessonForm(obj=item)
    if request.method == "GET":
        form.grade.data = str(item.grade); form.premium.data = "1" if item.premium else "0"
    if form.validate_on_submit():
        item.title=form.title.data; item.subject=form.subject.data; item.grade=int(form.grade.data)
        item.description=form.description.data; item.body=form.body.data; item.premium=form.premium.data=="1"
        db.session.commit(); flash("درس ویرایش شد.", "success")
        return redirect(url_for("admin"))
    return render_template("form.html", form=form, title="ویرایش درس")

@app.route("/admin/lesson/<int:item_id>/delete", methods=["POST"])
@admin_required
def delete_lesson(item_id):
    db.session.delete(db.get_or_404(Lesson, item_id)); db.session.commit()
    flash("درس حذف شد.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/exam/new", methods=["GET", "POST"])
@admin_required
def new_exam():
    form = ExamForm()
    if form.validate_on_submit():
        item = Exam(title=form.title.data, subject=form.subject.data, grade=int(form.grade.data),
                    duration_minutes=form.duration_minutes.data, premium=form.premium.data=="1")
        db.session.add(item); db.session.commit()
        flash("آزمون ساخته شد؛ حالا می‌توانید سؤال اضافه کنید.", "success")
        return redirect(url_for("add_question", exam_id=item.id))
    return render_template("form.html", form=form, title="ساخت آزمون")

@app.route("/admin/exam/<int:exam_id>/question", methods=["GET", "POST"])
@admin_required
def add_question(exam_id):
    exam = db.get_or_404(Exam, exam_id)
    form = QuestionForm()
    if form.validate_on_submit():
        q = Question(exam_id=exam.id, prompt=form.prompt.data, option_a=form.option_a.data,
                     option_b=form.option_b.data, option_c=form.option_c.data,
                     option_d=form.option_d.data, correct=form.correct.data)
        db.session.add(q); db.session.commit()
        flash("سؤال اضافه شد.", "success")
        return redirect(url_for("add_question", exam_id=exam.id))
    return render_template("form.html", form=form, title=f"افزودن سؤال به {exam.title}", extra=exam.questions)

@app.route("/admin/exam/<int:exam_id>/delete", methods=["POST"])
@admin_required
def delete_exam(exam_id):
    db.session.delete(db.get_or_404(Exam, exam_id)); db.session.commit()
    flash("آزمون حذف شد.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/user/<int:user_id>/subscription", methods=["POST"])
@admin_required
def grant_subscription(user_id):
    user = db.get_or_404(User, user_id)
    days = request.form.get("days", type=int)
    if not days or days < 1 or days > 3650:
        flash("مدت اشتراک معتبر نیست.", "error")
    else:
        base = user.subscription_until if user.subscription_until and user.subscription_until > datetime.utcnow() else datetime.utcnow()
        user.subscription_until = base + timedelta(days=days)
        db.session.commit()
        flash(f"اشتراک {days} روزه برای {user.name} فعال شد.", "success")
    return redirect(url_for("admin"))

@app.cli.command("init-db")
def init_db():
    """Create database tables."""
    db.create_all()
    print("Database tables created.")

@app.cli.command("create-admin")
def create_admin():
    """Create the first administrator using ADMIN_NAME, ADMIN_EMAIL and ADMIN_PASSWORD."""
    name = os.environ.get("ADMIN_NAME")
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if not all([name, email, password]):
        raise SystemExit("Set ADMIN_NAME, ADMIN_EMAIL and ADMIN_PASSWORD first.")
    if User.query.filter_by(email=email.lower()).first():
        raise SystemExit("This email already exists.")
    user = User(name=name, email=email.lower(), password_hash=generate_password_hash(password), role="admin")
    db.session.add(user); db.session.commit()
    print("Admin account created.")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
