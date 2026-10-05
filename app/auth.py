from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user
from werkzeug.security import check_password_hash
from .models import Worker, WorkerRole, Role  # Імпортуй свою модель користувача
from app import db

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))

        user = Worker.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password_hash, password):
            print('Неправильний логін або пароль')
            return redirect(url_for('auth.login'))

        # логінемо користувача
        login_user(user, remember=remember)

        # отримуємо активні ролі користувача
        active_roles = (
            WorkerRole.query
            .join(Role, WorkerRole.role_id == Role.role_id)
            .filter(
                WorkerRole.worker_id == user.worker_id,
                WorkerRole.status == 'active'
            )
            .with_entities(Role.name)
            .all()
        )
        active_role_names = [r.name.lower() for r in active_roles]

        # Визначаємо, куди редіректити
        if 'admin' in active_role_names:
            return redirect(url_for('admin_views.admin_dashboard'))
        elif 'manager' in active_role_names:
            return redirect(url_for('manager_views.manager_dashboard'))
        elif 'user' in active_role_names:
            return redirect(url_for('user_views.user_dashboard'))
        elif 'worker' in active_role_names:
            return redirect(url_for('worker_views.worker_dashboard'))
        else:
            # якщо нема жодної відомої ролі
            return redirect(url_for('auth.login'))

    return render_template('auth/login.html')

@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/remind-password')
def remind_password():
    return "<h3>Функціонал відновлення пароля буде реалізовано пізніше.</h3>"
