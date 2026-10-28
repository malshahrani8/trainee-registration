from flask import Flask, render_template, request, redirect, url_for, flash, send_file, Response
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, Admin, Trainee, TestSession
from forms import LoginForm, TraineeRegistrationForm, SessionForm
from email_service import mail, send_confirmation_email
from pdf_generator import generate_session_report_pdf
from config import Config
from sqlalchemy.exc import IntegrityError
from datetime import datetime, date, time
import os

app = Flask(__name__)
app.config.from_object(Config)

# تهيئة الامتدادات
db.init_app(app)
mail.init_app(app)

# إعداد Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'
login_manager.login_message = 'الرجاء تسجيل الدخول للوصول إلى هذه الصفحة'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


# ═══════════════════════════════════════════════════════
# دوال مساعدة
# ═══════════════════════════════════════════════════════

def init_db():
    """تهيئة قاعدة البيانات وإنشاء حساب مسؤول افتراضي"""
    with app.app_context():
        db.create_all()
        
        # إنشاء حساب مسؤول افتراضي إن لم يكن موجوداً
        if not Admin.query.filter_by(username='admin').first():
            admin = Admin(
                username='admin',
                email='admin@tvtc.gov.sa',
                full_name='مسؤول النظام'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ تم إنشاء حساب مسؤول افتراضي (admin / admin123)")
        
        # إضافة جلسات تجريبية
        if TestSession.query.count() == 0:
            sample_sessions = [
                TestSession(
                    session_date=date(2026, 11, 15),
                    session_time=time(10, 0),
                    location='معمل 201 - مبنى A',
                    max_capacity=20
                ),
                TestSession(
                    session_date=date(2026, 11, 16),
                    session_time=time(14, 0),
                    location='معمل 305 - مبنى B',
                    max_capacity=20
                ),
                TestSession(
                    session_date=date(2026, 11, 17),
                    session_time=time(9, 0),
                    location='معمل 112 - مبنى A',
                    max_capacity=20
                ),
            ]
            db.session.add_all(sample_sessions)
            db.session.commit()
            print("✅ تم إنشاء جلسات اختبار تجريبية")


# ═══════════════════════════════════════════════════════
# مسارات المتدربين (Public Routes)
# ═══════════════════════════════════════════════════════

@app.route('/')
def index():
    """الصفحة الرئيسية - تسجيل المتدربين"""
    available_sessions = [
        s for s in TestSession.query.order_by(
            TestSession.session_date, TestSession.session_time
        ).all() if not s.is_full
    ]
    form = TraineeRegistrationForm()
    return render_template('index.html', sessions=available_sessions, form=form)


@app.route('/register', methods=['POST'])
def register():
    """معالجة تسجيل المتدرب"""
    form = TraineeRegistrationForm(request.form)
    
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
        return redirect(url_for('index'))
    
    try:
        trainee_id = form.trainee_id.data.strip()
        email = form.email.data.strip().lower()
        phone = form.phone.data.strip()
        full_name = form.full_name.data.strip()
        session_id = form.session_id.data
        
        # قفل الصف لمنع Race Condition
        session = db.session.query(TestSession).filter_by(id=session_id).with_for_update().first()
        
        if not session:
            flash('الجلسة المحددة غير موجودة', 'danger')
            return redirect(url_for('index'))
        
        if session.is_full:
            flash('عذراً، هذه الجلسة مكتملة العدد', 'danger')
            return redirect(url_for('index'))
        
        # إنشاء متدرب جديد
        new_trainee = Trainee(
            full_name=full_name,
            email=email,
            phone=phone,
            trainee_id=trainee_id,
            session_id=session_id
        )
        
        db.session.add(new_trainee)
        db.session.commit()
        
        # إرسال بريد التأكيد (لا يوقف التسجيل عند الفشل)
        email_sent, email_msg = send_confirmation_email(new_trainee, session)
        if not email_sent:
            print(f"⚠️ {email_msg}")
        
        return render_template('success.html',
                             trainee=new_trainee,
                             session=session,
                             email_sent=email_sent)
        
    except IntegrityError:
        db.session.rollback()
        flash('هذا البريد الإلكتروني أو الرقم التدريبي مسجل مسبقاً', 'danger')
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ غير متوقع: {str(e)}', 'danger')
        return redirect(url_for('index'))


# ═══════════════════════════════════════════════════════
# مسارات المسؤول (Admin Routes)
# ═══════════════════════════════════════════════════════

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        admin = Admin.query.filter_by(username=form.username.data).first()
        if admin and admin.check_password(form.password.data):
            login_user(admin)
            flash(f'مرحباً {admin.full_name}!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('admin/login.html', form=form)


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin')
@login_required
def admin_dashboard():
    sessions = TestSession.query.order_by(TestSession.session_date).all()
    total_trainees = Trainee.query.count()
    total_sessions = len(sessions)
    full_sessions = sum(1 for s in sessions if s.is_full)
    
    return render_template('admin/dashboard.html',
                         sessions=sessions,
                         total_trainees=total_trainees,
                         total_sessions=total_sessions,
                         full_sessions=full_sessions)


@app.route('/admin/sessions')
@login_required
def admin_sessions():
    sessions = TestSession.query.order_by(TestSession.session_date, TestSession.session_time).all()
    return render_template('admin/sessions.html', sessions=sessions)


@app.route('/admin/sessions/new', methods=['GET', 'POST'])
@login_required
def admin_session_new():
    form = SessionForm()
    if form.validate_on_submit():
        session = TestSession(
            course_name=form.course_name.data,
            session_date=form.session_date.data,
            session_time=form.session_time.data,
            location=form.location.data,
            max_capacity=form.max_capacity.data
        )
        db.session.add(session)
        db.session.commit()
        flash('تم إنشاء الجلسة بنجاح', 'success')
        return redirect(url_for('admin_sessions'))
    return render_template('admin/session_form.html', form=form, title='إضافة جلسة جديدة')


@app.route('/admin/sessions/<int:session_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_session_edit(session_id):
    session = TestSession.query.get_or_404(session_id)
    form = SessionForm(obj=session)
    
    if form.validate_on_submit():
        session.course_name = form.course_name.data
        session.session_date = form.session_date.data
        session.session_time = form.session_time.data
        session.location = form.location.data
        session.max_capacity = form.max_capacity.data
        db.session.commit()
        flash('تم تحديث الجلسة بنجاح', 'success')
        return redirect(url_for('admin_sessions'))
    
    return render_template('admin/session_form.html', form=form, session=session, title='تعديل جلسة')


@app.route('/admin/sessions/<int:session_id>/delete', methods=['POST'])
@login_required
def admin_session_delete(session_id):
    session = TestSession.query.get_or_404(session_id)
    if session.trainees:
        flash('لا يمكن حذف جلسة بها متدربين مسجلين', 'danger')
        return redirect(url_for('admin_sessions'))
    db.session.delete(session)
    db.session.commit()
    flash('تم حذف الجلسة بنجاح', 'success')
    return redirect(url_for('admin_sessions'))


@app.route('/admin/reports')
@login_required
def admin_reports():
    sessions = TestSession.query.order_by(TestSession.session_date).all()
    return render_template('admin/reports.html', sessions=sessions)


@app.route('/admin/reports/<int:session_id>/pdf')
@login_required
def admin_report_pdf(session_id):
    session = TestSession.query.get_or_404(session_id)
    pdf_file = generate_session_report_pdf(session)
    
    filename = f"report_session_{session_id}_{session.session_date}.pdf"
    return send_file(
        pdf_file,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


@app.route('/admin/reports/<int:session_id>/print')
@login_required
def admin_report_print(session_id):
    session = TestSession.query.get_or_404(session_id)
    return render_template('admin/report_print.html', session=session)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)