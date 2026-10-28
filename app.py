from flask import Flask, render_template, request, redirect, url_for, flash, send_file, Response
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, Admin, Trainee, TestSession, SPECIALIZATIONS, COURSES
from forms import LoginForm, TraineeRegistrationForm, SessionForm
from email_service import mail, send_confirmation_email
from pdf_generator import generate_session_report_pdf
from excel_export import generate_excel_xml
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
                    course_name='مقدمة تطبيقات الحاسب',
                    specialization='دعم فني',
                    session_order=1,
                    session_date=date(2026, 11, 15),
                    session_time=time(10, 0),
                    location='معمل 201 - مبنى A',
                    max_capacity=20
                ),
                TestSession(
                    course_name='مقدمة تطبيقات الحاسب',
                    specialization='دعم فني',
                    session_order=2,
                    session_date=date(2026, 11, 16),
                    session_time=time(14, 0),
                    location='معمل 305 - مبنى B',
                    max_capacity=20
                ),
                TestSession(
                    course_name='مقدمة تطبيقات الحاسب',
                    specialization='شبكات الحاسب',
                    session_order=1,
                    session_date=date(2026, 11, 17),
                    session_time=time(9, 0),
                    location='معمل 112 - مبنى A',
                    max_capacity=20
                ),
            ]
            db.session.add_all(sample_sessions)
            db.session.commit()
            print("✅ تم إنشاء جلسات اختبار تجريبية")


def check_registration_rules(trainee_id, session_id, course_name):
    """
    التحقق من قواعد التسجيل:
    1. لا يمكن التسجيل أكثر من 3 جلسات لنفس المقرر
    2. لا يمكن التسجيل في جلسة ثانية إلا بعد حضور الأولى
    3. لا يمكن التسجيل في جلسة ثالثة إلا بعد حضور الثانية
    4. لا يمكن التسجيل في جلسات متزامنة
    """
    # جلب جميع تسجيلات المتدرب لهذا المقرر
    trainee_registrations = Trainee.query.filter_by(
        trainee_id=trainee_id
    ).join(TestSession).filter(
        TestSession.course_name == course_name
    ).all()
    
    # التحقق من عدد التسجيلات
    if len(trainee_registrations) >= 3:
        return False, 'لقد وصلت للحد الأقصى (3 جلسات) لهذا المقرر'
    
    # التحقق من عدم التسجيل في نفس الجلسة
    for reg in trainee_registrations:
        if reg.session_id == int(session_id):
            return False, 'أنت مسجل بالفعل في هذه الجلسة'
    
    # التحقق من التسلسل
    if len(trainee_registrations) > 0:
        # ترتيب التسجيلات حسب ترتيب الجلسة
        sorted_regs = sorted(trainee_registrations, key=lambda x: x.registration_order)
        
        # التحقق من حضور الجلسات السابقة
        for reg in sorted_regs:
            if reg.attendance_status != 'attended':
                return False, f'يجب حضور الجلسة {reg.registration_order} أولاً قبل التسجيل في جلسة جديدة'
        
        # التحقق من عدم التداخل الزمني
        new_session = TestSession.query.get(session_id)
        for reg in trainee_registrations:
            existing_session = reg.session
            # التحقق من نفس التاريخ والوقت
            if (existing_session.session_date == new_session.session_date and 
                existing_session.session_time == new_session.session_time):
                return False, 'لا يمكن التسجيل في جلسات متزامنة زمنياً'
    
    return True, 'التسجيل مسموح'


# ═══════════════════════════════════════════════════════
# مسارات المتدربين (Public Routes)
# ═══════════════════════════════════════════════════════

@app.route('/')
def index():
    """الصفحة الرئيسية - تسجيل المتدربين"""
    form = TraineeRegistrationForm()
    return render_template('index.html', form=form, specializations=SPECIALIZATIONS)


@app.route('/api/sessions')
def api_sessions():
    """API لجلب الجلسات المتاحة حسب التخصص"""
    specialization = request.args.get('specialization')
    
    if not specialization:
        return {'sessions': []}
    
    # جلب الجلسات المتاحة للتخصص المحدد
    available_sessions = TestSession.query.filter_by(
        specialization=specialization
    ).order_by(
        TestSession.session_date, TestSession.session_time
    ).all()
    
    # فلترة الجلسات غير المكتملة
    available_sessions = [s for s in available_sessions if not s.is_full]
    
    # تحويل إلى JSON
    sessions_data = []
    for session in available_sessions:
        sessions_data.append({
            'id': session.id,
            'course_name': session.course_name,
            'session_order': session.session_order,
            'session_order_text': session.session_order_text,
            'session_date': session.session_date.strftime('%Y-%m-%d'),
            'session_time': session.session_time.strftime('%H:%M'),
            'location': session.location,
            'current_count': session.current_count,
            'max_capacity': session.max_capacity,
            'available_seats': session.available_seats
        })
    
    return {'sessions': sessions_data}


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
        specialization = form.specialization.data
        session_id = form.session_id.data
        
        # جلب الجلسة
        session = TestSession.query.get(session_id)
        
        if not session:
            flash('الجلسة المحددة غير موجودة', 'danger')
            return redirect(url_for('index'))
        
        if session.is_full:
            flash('عذراً، هذه الجلسة مكتملة العدد', 'danger')
            return redirect(url_for('index'))
        
        # التحقق من قواعد التسجيل
        is_allowed, message = check_registration_rules(trainee_id, session_id, session.course_name)
        if not is_allowed:
            flash(message, 'danger')
            return redirect(url_for('index'))
        
        # تحديد ترتيب التسجيل
        existing_count = Trainee.query.filter_by(trainee_id=trainee_id).join(TestSession).filter(
            TestSession.course_name == session.course_name
        ).count()
        registration_order = existing_count + 1
        
        # قفل الصف لمنع Race Condition
        session = db.session.query(TestSession).filter_by(id=session_id).with_for_update().first()
        
        if session.is_full:
            flash('عذراً، اكتملت الجلسة أثناء تسجيلك', 'danger')
            return redirect(url_for('index'))
        
        # إنشاء متدرب جديد
        new_trainee = Trainee(
            full_name=full_name,
            email=email,
            phone=phone,
            trainee_id=trainee_id,
            specialization=specialization,
            session_id=session_id,
            registration_order=registration_order,
            attendance_status='pending'
        )
        
        db.session.add(new_trainee)
        db.session.commit()
        
        # إرسال بريد التأكيد
        email_sent, email_msg = send_confirmation_email(new_trainee, session)
        if not email_sent:
            print(f"⚠️ {email_msg}")
        
        return render_template('success.html',
                             trainee=new_trainee,
                             session=session,
                             email_sent=email_sent)
        
    except IntegrityError:
        db.session.rollback()
        flash('هذا الرقم التدريبي مسجل مسبقاً في هذه الجلسة', 'danger')
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
            specialization=form.specialization.data,
            session_order=form.session_order.data,
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
        session.specialization = form.specialization.data
        session.session_order = form.session_order.data
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


@app.route('/admin/sessions/<int:session_id>/attendance', methods=['GET', 'POST'])
@login_required
def admin_session_attendance(session_id):
    """إدارة حضور المتدربين في الجلسة"""
    session = TestSession.query.get_or_404(session_id)
    
    if request.method == 'POST':
        # تحديث حالة الحضور
        for trainee in session.trainees:
            status = request.form.get(f'attendance_{trainee.id}')
            if status:
                trainee.attendance_status = status
        db.session.commit()
        flash('تم تحديث سجل الحضور بنجاح', 'success')
        return redirect(url_for('admin_session_attendance', session_id=session_id))
    
    return render_template('admin/attendance.html', session=session)


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


@app.route('/admin/reports/<int:session_id>/excel')
@login_required
def admin_report_excel(session_id):
    """تصدير التقرير بصيغة Excel XML"""
    session = TestSession.query.get_or_404(session_id)
    xml_content = generate_excel_xml(session)
    
    filename = f"report_session_{session_id}_{session.session_date}.xml"
    
    return Response(
        xml_content,
        mimetype='application/xml',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'application/xml; charset=utf-8'
        }
    )


@app.route('/admin/reports/<int:session_id>/print')
@login_required
def admin_report_print(session_id):
    session = TestSession.query.get_or_404(session_id)
    return render_template('admin/report_print.html', session=session)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
