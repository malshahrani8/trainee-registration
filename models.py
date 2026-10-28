from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Admin(UserMixin, db.Model):
    """نموذج المسؤول"""
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Trainee(db.Model):
    """نموذج المتدرب"""
    __tablename__ = 'trainees'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    trainee_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(15), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    session = db.relationship('TestSession', backref=db.backref('trainees', lazy=True))
    
    def __repr__(self):
        return f'<Trainee {self.full_name} - {self.trainee_id}>'


class TestSession(db.Model):
    """نموذج جلسة الاختبار"""
    __tablename__ = 'test_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    course_name = db.Column(db.String(200), default='مقدمة تطبيقات الحاسب', nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    session_time = db.Column(db.Time, nullable=False)
    location = db.Column(db.String(100), nullable=False)  # رقم المعمل
    max_capacity = db.Column(db.Integer, default=20, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def current_count(self):
        return len(self.trainees)
    
    @property
    def is_full(self):
        return self.current_count >= self.max_capacity
    
    @property
    def available_seats(self):
        return self.max_capacity - self.current_count
    
    @property
    def display_datetime(self):
        return f"{self.session_date.strftime('%Y-%m-%d')} الساعة {self.session_time.strftime('%H:%M')}"
    
    @property
    def status_badge(self):
        if self.is_full:
            return '<span class="badge bg-danger">مكتملة</span>'
        return f'<span class="badge bg-tvtc-green">متاحة ({self.available_seats} مقعد)</span>'
    
    def __repr__(self):
        return f'<TestSession {self.course_name} - {self.location}>'