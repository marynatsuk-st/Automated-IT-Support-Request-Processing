from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import traceback
import re
from datetime import date
import random
from flask import jsonify

from . import db
from .models import (
    Worker, Department, Role, WorkerDepartment, WorkerRole, WorkerTaskType,
    Task, TaskType, WorkerTask, Device, DeviceWorker,
    WorkerStatusEnum, HistoryStatusEnum, DeviceStatusEnum, AssignmentStatusEnum,
    WorkerTaskStatusEnum, TaskStatusEnum
)
from .decorators import role_required 
from .worker_assign import choose_worker

admin_views = Blueprint('admin_views', __name__, url_prefix='/admin')

#====================== ADMIN =====================================
# View list of all workers
# @admin_views.route('/admin_dashboard', methods=['GET', 'POST'])
# # @login_required
# # @role_required([1]) #Admin
# def admin_dashboard():
#     # users = db.session.query(Worker, Department.name, Role.name).join(Department).join(Role).order_by(asc(Worker.id)).all()
#     # roles = Role.query.all()
#     # departments = Department.query.all()
#     # return render_template("admin/admin_dashboard.html", users = users, roles=roles, departments=departments)
#     return render_template("admin/admin_dashboard.html")

@admin_views.route('/admin_dashboard', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def admin_dashboard():
    try:
        users = Worker.query.order_by(Worker.surname, Worker.name).all()
    except SQLAlchemyError as e:
        flash(f"Помилка бази даних при завантаженні користувачів: {e}", "danger")
        users = []
    
    return render_template("admin/admin_dashboard.html", users=users, WorkerStatusEnum=WorkerStatusEnum)





@admin_views.route('/create_user', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def create_user():
    if request.method == 'POST':
        # --- 1. Збір та валідація даних ---
        form_data = request.form
        errors = []

        # Валідація телефону
        phone = form_data.get('phone')
        if not re.match(r'^\+380\d{9}$', phone):
            errors.append('Номер телефону має бути у форматі +380XXXXXXXXX.')

        # Валідація унікальності
        if Worker.query.filter_by(email=form_data.get('email')).first():
            errors.append('Користувач з таким email вже існує.')
        if Worker.query.filter_by(username=form_data.get('username')).first():
            errors.append('Користувач з таким username вже існує.')
            
        # Валідація пароля
        if len(form_data.get('password1')) < 7:
            errors.append('Пароль має містити щонайменше 7 символів.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            # Перезавантажуємо сторінку, щоб показати помилки
            # Дані форми будуть втрачені, але це стандартна поведінка для створення
            return redirect(url_for('admin_views.create_user'))

        # --- 2. Створення об'єктів (якщо валідація пройдена) ---
        try:
            new_user = Worker(
                surname=form_data.get('surname'),
                name=form_data.get('name'),
                email=form_data.get('email'),
                phone=phone,
                date_of_birth=datetime.strptime(form_data.get('date_of_birth'), '%Y-%m-%d').date(),
                username=form_data.get('username'),
                password_hash=generate_password_hash(form_data.get('password1'), method='pbkdf2:sha256'),
                manager_id=int(form_data.get('manager')) if form_data.get('manager') else None,
                worker_status=WorkerStatusEnum.ACTIVE # Використовуємо Enum
            )
            db.session.add(new_user)
            db.session.flush() # Отримуємо ID для подальшого використання

            department_link = WorkerDepartment(
                worker_id=new_user.worker_id,
                department_id=int(form_data.get('department_id')),
                title=form_data.get('title'),
                status=HistoryStatusEnum.ACTIVE # Використовуємо Enum
            )
            role_link = WorkerRole(
                worker_id=new_user.worker_id,
                role_id=int(form_data.get('role')),
                status=HistoryStatusEnum.ACTIVE # Використовуємо Enum
            )

            db.session.add_all([department_link, role_link])
            db.session.commit()
            flash("Користувача успішно створено!", "success")
            return redirect(url_for('admin_views.admin_dashboard'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Непередбачувана помилка при створенні користувача: {e}", "danger")

    # --- 3. GET-запит: готуємо дані для форми ---
    departments = Department.query.order_by(Department.name).all()
    roles = Role.query.order_by(Role.name).all()
    # Менеджерів тепер завантажує JavaScript, тому тут їх отримувати не потрібно
    return render_template("admin/create_user.html", departments=departments, roles=roles)



# admin_views.py

@admin_views.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_user(user_id):
    user = Worker.query.get_or_404(user_id)
    current_dept_record = user.current_department_record
    current_role_record = user.current_role_record

    if request.method == 'POST':
        try:
            # --- Валідація та оновлення базових полів ---
            phone_number = request.form['phone']
            if not re.match(r'^\+380\d{9}$', phone_number):
                flash('Номер телефону має бути у форматі +380XXXXXXXXX (12 цифр).', 'danger')
                return redirect(url_for('admin_views.edit_user', user_id=user_id))
            
            user.phone = phone_number
            user.surname = request.form['surname']
            user.name = request.form['name']
            user.email = request.form['email']
            user.username = request.form['username']
            user.date_of_birth = datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date()

            if request.form['password1']:
                user.password_hash = generate_password_hash(request.form['password1'], method='pbkdf2:sha256')

            # --- Логіка для статусу та дати недоступності ---
            new_status = WorkerStatusEnum(request.form['worker_status'])
            unavailable_until_str = request.form.get("unavailable_until")
            new_unavailable_date = None
            if unavailable_until_str:
                new_unavailable_date = datetime.strptime(unavailable_until_str, "%Y-%m-%d").date()

            if new_status == WorkerStatusEnum.ACTIVE:
                if user.unavailable_until is not None:
                    flash('Дата недоступності була очищена, оскільки встановлено статус "Active".', 'info')
                user.worker_status = WorkerStatusEnum.ACTIVE
                user.unavailable_until = None
            elif new_status == WorkerStatusEnum.ON_VACATION:
                if new_unavailable_date:
                    user.worker_status = WorkerStatusEnum.ON_VACATION
                    user.unavailable_until = new_unavailable_date
                else:
                    flash("Статус 'On Vacation' вимагає вказання дати недоступності.", "danger")
                    return redirect(url_for('admin_views.edit_user', user_id=user_id))
            else:
                user.worker_status = new_status
                user.unavailable_until = None

            # B-) ================== ВІДНОВЛЕНИЙ БЛОК ДЛЯ ОНОВЛЕННЯ ВІДДІЛУ/РОЛІ ==================
            
            # 1. Оновлення відділу та посади (з веденням ІСТОРІЇ!)
            new_department_id = int(request.form['department_id'])
            new_title = request.form['title']

            if current_dept_record and (current_dept_record.department_id != new_department_id or current_dept_record.title != new_title):
                # а) Деактивуємо старий запис
                current_dept_record.end_date = datetime.utcnow().date()
                current_dept_record.status = HistoryStatusEnum.INACTIVE
                
                # б) Створюємо новий активний запис
                new_dept_link = WorkerDepartment(
                    worker=user,
                    department_id=new_department_id,
                    title=new_title,
                    status=HistoryStatusEnum.ACTIVE
                )
                db.session.add(new_dept_link)

            new_role_id = int(request.form['role'])
            if current_role_record and current_role_record.role_id != new_role_id:
                old_role_name = current_role_record.role.name
                print(f"Починається зміна ролі з '{old_role_name}' на нову.")

                # --- ФАЗА 1: ПЕРЕВІРКИ для СТАРОЇ ролі ---
                pre_check_errors = []
                if old_role_name == 'Manager':
                    can_change, msg = _check_last_manager_in_department(user)
                    if not can_change: pre_check_errors.append(msg)
                
                if old_role_name == 'Worker':
                    can_change, msg = _check_worker_competency_replacement(user)
                    if not can_change: pre_check_errors.append(msg)

                if pre_check_errors:
                    for error in pre_check_errors:
                        flash(error, "danger")
                    # Важливо! Скасовуємо транзакцію і повертаємося на сторінку редагування
                    db.session.rollback() 
                    return redirect(url_for('admin_views.edit_user', user_id=user_id))
                
                print(f"Перевірки для деактивації ролі '{old_role_name}' пройдено.")

                # --- ФАЗА 2: ДІЇ по деактивації СТАРОЇ ролі ---
                if old_role_name == 'Manager':
                    _action_reassign_subordinates(user)
                
                if old_role_name == 'Worker':
                    _action_reassign_worker_tasks(user, admin_id=current_user.id)
                    
                if old_role_name == 'Customer':
                    _action_create_device_return_tasks(user, admin_id=current_user.id)
                    _action_reassign_customer_tickets(user)
                
                print(f"Дії по деактивації ролі '{old_role_name}' виконано.")

                # --- ФАЗА 3: ФІНАЛІЗАЦІЯ - деактивуємо стару роль і створюємо нову ---
                current_role_record.end_date = datetime.utcnow().date()
                current_role_record.status = HistoryStatusEnum.INACTIVE
                
                new_role_link = WorkerRole(
                    worker=user,
                    role_id=new_role_id,
                    status=HistoryStatusEnum.ACTIVE
                )
                db.session.add(new_role_link)
            

            db.session.commit()
            flash('Дані користувача успішно оновлено.', 'success')
            return redirect(url_for('admin_views.admin_dashboard'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Помилка при оновленні: {e}", "danger")
            return redirect(url_for('admin_views.edit_user', user_id=user_id))
    
    # ... (Ваш код для GET-запиту залишається без змін) ...
    departments = Department.query.order_by(Department.name).all()
    roles = Role.query.order_by(Role.name).all()
    status_options = list(WorkerStatusEnum) 
    
    return render_template('admin/edit_user.html',
                           user=user,
                           roles=roles,
                           departments=departments,
                           current_department_record=current_dept_record,
                           current_role_record=current_role_record,
                           status_options=status_options)
# disable user
@admin_views.route('/deactivate_user/<int:user_id>', methods=['POST'])
@login_required
@role_required('Admin')
def deactivate_user(user_id):
    user_to_deactivate = Worker.query.get_or_404(user_id)
    print(user_to_deactivate)

    # Заборона деактивації самого себе
    if user_to_deactivate.worker_id == current_user.id:
        flash("Ви не можете деактивувати власний обліковий запис.", "danger")
        return redirect(url_for('admin_views.admin_dashboard'))

    active_roles = {record.role.name for record in user_to_deactivate.roles_history.filter_by(status=HistoryStatusEnum.ACTIVE)}
    
    # --- ФАЗА 1: ПЕРЕВІРКИ ---
    pre_check_errors = []
    if 'Admin' in active_roles:
        can_deactivate, msg = _check_last_admin()
        if not can_deactivate: pre_check_errors.append(msg)
    
    if 'Manager' in active_roles:
        can_deactivate, msg = _check_last_manager_in_department(user_to_deactivate)
        if not can_deactivate: pre_check_errors.append(msg)
        
    if 'Worker' in active_roles:
        can_deactivate, msg = _check_worker_competency_replacement(user_to_deactivate)
        if not can_deactivate: pre_check_errors.append(msg)

    if pre_check_errors:
        for error in pre_check_errors:
            flash(error, "danger")
        return redirect(url_for('admin_views.admin_dashboard'))

    # --- ФАЗА 2: ДІЇ ТА ФІНАЛІЗАЦІЯ ---
    try:
        if 'Manager' in active_roles:
            _action_reassign_subordinates(user_to_deactivate)
            # Завдання самого менеджера перепризначаться нижче, якщо він має роль 'Worker'
        
        if 'Worker' in active_roles:
            _action_reassign_worker_tasks(user_to_deactivate, admin_id=current_user.id)
            
        if 'Customer' in active_roles:
            _action_create_device_return_tasks(user_to_deactivate, admin_id=current_user.id)
            _action_reassign_customer_tickets(user_to_deactivate)
            
        # Загальна процедура деактивації для всіх
        _action_perform_standard_deactivation(user_to_deactivate)

        db.session.commit()
        flash(f'Користувача {user_to_deactivate.full_name} успішно деактивовано. Усі пов\'язані процеси оброблено.', 'success')

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        flash(f"Критична помилка під час деактивації: {e}", "danger")

    return redirect(url_for('admin_views.admin_dashboard'))


def _check_last_admin():
    admin_role = Role.query.filter_by(name='Admin').first()
    if not admin_role: return False, "Системна роль 'Admin' не знайдена."
    
    active_admin_count = WorkerRole.query.filter_by(role_id=admin_role.role_id, status=HistoryStatusEnum.ACTIVE).count()
    if active_admin_count <= 1:
        return False, "Не можна деактивувати останнього адміністратора в системі."
    return True, ""

def _check_last_manager_in_department(manager):
    department = manager.current_department
    if not department: return True, "" 

    manager_role = Role.query.filter_by(name='Manager').first()
    if not manager_role: return False, "Системна роль 'Manager' не знайдена."

    other_managers_count = db.session.query(Worker.worker_id).join(WorkerDepartment).join(WorkerRole).filter(
        Worker.worker_id != manager.worker_id,
        WorkerDepartment.department_id == department.department_id,
        WorkerDepartment.status == HistoryStatusEnum.ACTIVE,
        WorkerRole.role_id == manager_role.role_id,
        WorkerRole.status == HistoryStatusEnum.ACTIVE
    ).count()
    
    if other_managers_count == 0:
        return False, f"Неможливо деактивувати, оскільки це єдиний менеджер у відділі '{department.name}'."
    return True, ""

def _check_worker_competency_replacement(worker):
    active_competencies = worker.task_type_competencies.filter_by(status=HistoryStatusEnum.ACTIVE).all()
    for competency in active_competencies:
        replacements_count = WorkerTaskType.query.filter(
            WorkerTaskType.tasktype_id == competency.tasktype_id,
            WorkerTaskType.status == HistoryStatusEnum.ACTIVE,
            WorkerTaskType.worker_id != worker.worker_id
        ).count()
        if replacements_count == 0:
            return False, f"Неможливо деактивувати: для типу завдань '{competency.task_type.name}' немає інших виконавців."
    return True, ""

# --- Функції дій ---
def _action_reassign_subordinates(manager):
    department = manager.current_department
    manager_role = Role.query.filter_by(name='Manager').first()
    
    # Знаходимо всіх інших менеджерів у цьому відділі
    replacement_managers = Worker.query.join(WorkerDepartment).join(WorkerRole).filter(
        Worker.worker_id != manager.worker_id,
        WorkerDepartment.department_id == department.department_id,
        WorkerDepartment.status == HistoryStatusEnum.ACTIVE,
        WorkerRole.role_id == manager_role.role_id,
        WorkerRole.status == HistoryStatusEnum.ACTIVE
    ).all()

    if not replacement_managers: return # 

    replacement_manager = random.choice(replacement_managers)
    
    subordinates = Worker.query.filter_by(manager_id=manager.worker_id).all()
    for subordinate in subordinates:
        subordinate.manager_id = replacement_manager.worker_id
        print(f"Перепризначено {subordinate.full_name} новому менеджеру {replacement_manager.full_name}")

def _action_reassign_worker_tasks(worker, admin_id):
    active_assignments = worker.assigned_tasks.filter_by(status=WorkerTaskStatusEnum.ACTIVE).all()
    
    for assignment in active_assignments:
        task = assignment.task
        
        # 1. Деактивуємо старе призначення
        assignment.status = WorkerTaskStatusEnum.REASSIGNED
        assignment.unassigned_at = datetime.utcnow()
        assignment.unassigned_by_id = admin_id
        
        # 2. Викликаємо оновлену функцію вибору
        assignment_result = choose_worker(task=task, ignore_max_load=True)

        if assignment_result:
            # 3. Створюємо нове призначення, використовуючи результат
            new_worker_id = assignment_result['worker_id']
            assignment_method = assignment_result['method']
            
            new_assignment = WorkerTask(
                task_id=task.id,
                worker_id=new_worker_id,
                assign_method=assignment_method, # Зберігаємо метод призначення!
                assigned_by_id=admin_id,
                status=WorkerTaskStatusEnum.ACTIVE
            )
            db.session.add(new_assignment)
            print(f"Завдання #{task.id} перепризначено з {worker.full_name} на працівника ID:{new_worker_id} (метод: {assignment_method})")
        else:
            # Цей блок тепер спрацює тільки в крайньому випадку, якщо навіть менеджера не знайдено
            print(f"ПОПЕРЕДЖЕННЯ: Не вдалося знайти заміну або менеджера для завдання #{task.id}. Завдання залишилось без виконавця.")
            # Тут можна додати логіку сповіщення головного адміністратора системи

def _action_create_device_return_tasks(user, admin_id):
    return_task_type = TaskType.query.filter_by(name='DeviceReturn').first()
    if not return_task_type:
        print("ПОПЕРЕДЖЕННЯ: Не знайдено тип завдання 'DeviceReturn'. Завдання на повернення не створено.")
        return

    active_device_assignments = user.device_assignment_history.filter_by(status=AssignmentStatusEnum.ACTIVE).all()
    
    for assignment in active_device_assignments:
        device = assignment.device
        device.status = DeviceStatusEnum.IN_TRANSIT
        
        new_task = Task(
            text=f"Повернення пристрою: {device.name} (SN: {device.serial_number}) від користувача {user.full_name}.",
            priority=3, # Повернення пристроїв - високий пріоритет
            customer_id=user.worker_id, # Заявка формально від користувача
            device_id=device.id,
            status='new'
        )
        # Логіка для зв'язку Task та Task_TaskType (як при створенні нового завдання)
        # ...
        db.session.add(new_task)
        print(f"Створено завдання на повернення пристрою ID:{device.id} від {user.full_name}")

def _action_reassign_customer_tickets(user):
    if not user.manager_id: return # Якщо у користувача немає менеджера

    open_tickets = Task.query.filter(
        Task.customer_id == user.worker_id,
        Task.status.in_([TaskStatusEnum.NEW, TaskStatusEnum.IN_PROGRESS, TaskStatusEnum.ON_HOLD])
    ).all()
    
    for ticket in open_tickets:
        ticket.customer_id = user.manager_id
        print(f"Заявку #{ticket.id} передано менеджеру (ID:{user.manager_id})")

def _action_perform_standard_deactivation(user):
    today = date.today()
    
    # 1. Основний статус
    user.worker_status = WorkerStatusEnum.INACTIVE
    
    # 2. Закриття всіх активних "контрактів"
    for record in user.departments_history.filter_by(status=HistoryStatusEnum.ACTIVE):
        record.status = HistoryStatusEnum.INACTIVE
        record.end_date = today
        
    for record in user.roles_history.filter_by(status=HistoryStatusEnum.ACTIVE):
        record.status = HistoryStatusEnum.INACTIVE
        record.end_date = today
        
    for record in user.task_type_competencies.filter_by(status=HistoryStatusEnum.ACTIVE):
        record.status = HistoryStatusEnum.INACTIVE
        record.end_date = today

@admin_views.route('/api/managers/<int:department_id>')
@login_required
@role_required('Admin')
def get_managers_for_department(department_id):
    """
    API-ендпоінт для отримання списку менеджерів у конкретному відділі.
    Повертає JSON для використання у JavaScript.
    """
    manager_role = Role.query.filter_by(name='Manager').first()
    if not manager_role:
        return jsonify([]) # Повертаємо порожній список, якщо роль не знайдена

    managers = db.session.query(
        Worker.worker_id, Worker.name, Worker.surname
    ).join(WorkerRole).join(WorkerDepartment).filter(
        WorkerRole.role_id == manager_role.role_id,
        WorkerDepartment.department_id == department_id,
        WorkerRole.status == HistoryStatusEnum.ACTIVE,
        WorkerDepartment.status == HistoryStatusEnum.ACTIVE
    ).all()

    # Перетворюємо результат у список словників, зручний для JSON
    managers_list = [{'id': m.worker_id, 'full_name': f"{m.name} {m.surname}"} for m in managers]
    return jsonify(managers_list)
