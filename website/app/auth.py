from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
import traceback

from .models import Worker, WorkerStatusEnum, HistoryStatusEnum
from . import db

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))


        user = Worker.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash('Неправильний логін або пароль.', 'danger')
            return redirect(url_for('auth.login'))


        if user.worker_status != WorkerStatusEnum.ACTIVE:
            flash('Ваш акаунт неактивний. Будь ласка, зверніться до адміністратора.', 'warning')
            return redirect(url_for('auth.login'))
        

        login_user(user, remember=remember)


        try:
            # === ДЕБАГ-БЛОК ===
            print(f"--- DEBUG START for user: {user.username} ---")
            
            # 1. Перевіряємо, чи є roles_history запитом
            print(f"Type of user.roles_history: {type(user.roles_history)}")
            
            active_worker_roles = user.roles_history.filter_by(status=HistoryStatusEnum.ACTIVE).all()
            
            # 2. Дивимося, що саме повернув запит
            print(f"Found active role records: {active_worker_roles!r}")
            
            if active_worker_roles:
                # 3. Перевіряємо перший елемент та його зв'язки
                first_wr = active_worker_roles[0]
                print(f"First record 'wr': {first_wr!r}")
                print(f"Type of wr.role: {type(first_wr.role)}")
                print(f"Value of wr.role: {first_wr.role!r}")
            
            print("--- DEBUG END ---")
            # === КІНЕЦЬ ДЕБАГ-БЛОКУ ===

            active_role_names = [wr.role.name.lower() for wr in active_worker_roles]

        except Exception as e:
            # B-) Дуже важливо виводити саму помилку в консоль!
            print(f"!!! EXCEPTION CAUGHT: {e} !!!") 
            traceback.print_exc() # Друкує повний трейсбек помилки
            
            flash('Не вдалося визначити вашу роль. Спробуйте ще раз.', 'danger')
            logout_user()
            return redirect(url_for('auth.login'))

        if 'admin' in active_role_names:
            return redirect(url_for('admin_views.admin_dashboard'))
        elif 'manager' in active_role_names:
            return redirect(url_for('manager_views.manager_dashboard'))
        elif 'worker' in active_role_names:
            return redirect(url_for('worker_views.worker_dashboard'))
        elif 'user' in active_role_names: 
            return redirect(url_for('user_views.user_dashboard'))
        else:

            flash('Для вашого акаунта не призначено жодної ролі.', 'warning')
            logout_user()
            return redirect(url_for('auth.login'))

    return render_template('auth/login.html')

@auth.route('/logout')
@login_required 
def logout():
    logout_user()
    flash('Ви успішно вийшли з системи.', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/remind-password')
def remind_password():
    # Цей функціонал можна буде додати пізніше
    return "<h3>Функціонал відновлення пароля буде реалізовано пізніше.</h3>"