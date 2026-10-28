from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, DateField, TimeField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Email, Length, ValidationError, Regexp
import re

class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[DataRequired(message='اسم المستخدم مطلوب')])
    password = PasswordField('كلمة المرور', validators=[DataRequired(message='كلمة المرور مطلوبة')])
    submit = SubmitField('تسجيل الدخول')


class TraineeRegistrationForm(FlaskForm):
    full_name = StringField('الاسم الكامل', validators=[
        DataRequired(message='الاسم الكامل مطلوب'),
        Length(min=3, max=100, message='يجب أن يكون الاسم بين 3 و 100 حرف')
    ])
    
    trainee_id = StringField('الرقم التدريبي', validators=[
        DataRequired(message='الرقم التدريبي مطلوب'),
        Regexp(r'^[0-9]{6,10}$', message='الرقم التدريبي يجب أن يتكون من 6-10 أرقام فقط')
    ])
    
    phone = StringField('رقم الجوال', validators=[
        DataRequired(message='رقم الجوال مطلوب'),
        Regexp(r'^05[0-9]{8}$', message='رقم الجوال يجب أن يبدأ بـ 05 ويتكون من 10 أرقام')
    ])
    
    email = StringField('البريد الإلكتروني', validators=[
        DataRequired(message='البريد الإلكتروني مطلوب'),
        Email(message='صيغة البريد الإلكتروني غير صحيحة')
    ])
    
    session_id = StringField('الجلسة المختارة', validators=[
        DataRequired(message='يجب اختيار جلسة')
    ])
    
    submit = SubmitField('تأكيد التسجيل')


class SessionForm(FlaskForm):
    course_name = StringField('اسم المقرر', default='مقدمة تطبيقات الحاسب',
                              validators=[DataRequired(message='اسم المقرر مطلوب')])
    session_date = DateField('تاريخ الجلسة', format='%Y-%m-%d',
                             validators=[DataRequired(message='تاريخ الجلسة مطلوب')])
    session_time = TimeField('وقت الجلسة', format='%H:%M',
                             validators=[DataRequired(message='وقت الجلسة مطلوب')])
    location = StringField('رقم المعمل / مكان الجلسة', validators=[
        DataRequired(message='رقم المعمل مطلوب'),
        Length(max=100)
    ])
    max_capacity = IntegerField('السعة القصوى', default=20,
                                validators=[DataRequired(message='السعة مطلوبة')])
    submit = SubmitField('حفظ')