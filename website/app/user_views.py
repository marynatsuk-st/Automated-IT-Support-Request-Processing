from flask import Blueprint, render_template, url_for, flash, redirect, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import desc

from . import db
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect, asc, desc
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import subqueryload 
import re, traceback

from . import db
from .models import (
    Worker, Department, Role, WorkerDepartment, WorkerRole, WorkerTaskType,
    Task, TaskType, WorkerTask, Device, DeviceWorker, DeviceDepartment,
    DeviceType, DeviceAttribute, DeviceAttributeValue, DeviceTypeAttribute,
    Task_TaskType,
    WorkerStatusEnum, HistoryStatusEnum, TaskStatusEnum, TaskDetectionMethodEnum,
    WorkerTaskStatusEnum, WorkerTaskAssignmentMethodEnum, DeviceStatusEnum, AssignmentStatusEnum
)# Імпортуємо необхідні моделі та Enum
from .decorators import role_required
from .status_utils import predict
from .worker_assign import choose_worker

user_views = Blueprint('user_views', __name__)

@user_views.route('/dashboard')
@login_required
@role_required('User')
def user_dashboard():
    my_tasks = (
        Task.query
        .filter_by(customer_id=current_user.worker_id)
        # B-) ВИДАЛЕНО options(joinedload...) для спрощення
        .order_by(desc(Task.created_at))
        .all()
    )
    status_options = list(TaskStatusEnum)

    return render_template(
        "user/user_dashboard.html",
        tasks=my_tasks,
        statuses=status_options,
        TaskStatusEnum=TaskStatusEnum,
        db=db, # B-) Передаємо об'єкт db
        WorkerTask=WorkerTask # B-) Передаємо клас WorkerTask
    )

@user_views.route('/cancel_request/<int:task_id>', methods=['POST'])
@login_required
def cancel_request(task_id):
    """Обробник для скасування заявки користувачем."""
    task_to_cancel = Task.query.get_or_404(task_id)

    # Перевірка: чи користувач є власником заявки і чи заявка ще не закрита/скасована
    if task_to_cancel.customer_id != current_user.worker_id:
        flash("Ви не можете скасувати цю заявку.", "danger")
    elif task_to_cancel.status in [TaskStatusEnum.CLOSED, TaskStatusEnum.CANCELLED]:
        flash("Цю заявку вже закрито або скасовано.", "info")
    else:
        try:
            task_to_cancel.status = TaskStatusEnum.CANCELLED
            
            # Також деактивуємо поточне призначення виконавця, якщо воно є
            current_assignment = task_to_cancel.current_assignment
            if current_assignment:
                current_assignment.status = WorkerTaskStatusEnum.CANCELLED # Або інший статус для скасованих
                current_assignment.comment = f"Завдання скасовано замовником ({current_user.full_name})."
                
            db.session.commit()
            flash("Заявку успішно скасовано.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Помилка при скасуванні заявки: {e}", "danger")
            
    return redirect(url_for('user_views.user_dashboard'))

@user_views.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('User')
def user_profile():
    # B-) Замість складного запиту, ми просто беремо об'єкт з сесії.
    # Для зміни даних краще отримати "свіжий" об'єкт з бази.
    user_to_update = db.session.get(Worker, current_user.worker_id)

    if request.method == 'POST':
        form_data = request.form
        errors = []
        updated = False

        # --- 1. Валідація ВСІХ полів перед збереженням ---
        
        # Телефон
        new_phone = form_data.get('phone')
        if not re.match(r'^\+380\d{9}$', new_phone):
            errors.append('Номер телефону має бути у форматі +380XXXXXXXXX.')
        
        # Email
        new_email = form_data.get('email')
        if new_email != user_to_update.email:
            if Worker.query.filter_by(email=new_email).first():
                errors.append('Цей email вже використовується іншим користувачем.')

        # Пароль
        new_password = form_data.get('password')
        confirm_password = form_data.get('password2')
        if new_password: # Перевіряємо пароль, тільки якщо поле заповнене
            if new_password != confirm_password:
                errors.append('Паролі не співпадають.')
            elif len(new_password) < 7:
                errors.append('Новий пароль має містити щонайменше 7 символів.')

        # --- 2. Збереження, якщо немає помилок ---
        if errors:
            for error in errors:
                flash(error, 'danger')
        else:
            # Якщо валідація пройдена, застосовуємо зміни
            if user_to_update.phone != new_phone:
                user_to_update.phone = new_phone
                updated = True
            
            if user_to_update.email != new_email:
                user_to_update.email = new_email
                updated = True

            if new_password:
                user_to_update.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
                updated = True
            
            if updated:
                db.session.commit()
                flash('Ваші дані успішно оновлено!', 'success')
            else:
                flash('Ви не внесли жодних змін.', 'info')
        
        return redirect(url_for('user_views.user_profile'))

    # --- GET-запит: просто передаємо поточного користувача в шаблон ---
    # Всю інформацію про відділ/роль ми отримаємо через relationships прямо в HTML
    return render_template("user/user_profile.html", user=current_user)


# TODO: Додати маршрути для new_request, user_devices, profile, questions


@user_views.route('/new_request', methods=['GET', 'POST'])
@login_required
@role_required('User')
def new_request():
    """Сторінка для створення нової текстової заявки."""
    if request.method == 'POST':
        request_text = request.form.get('request_text')

        if not request_text or len(request_text.strip()) < 10:
            flash('Будь ласка, опишіть вашу проблему більш детально (мінімум 10 символів).', 'warning')
            return redirect(url_for('user_views.new_request'))

        try:
            # --- 1. Визначення типу завдання за допомогою NLP ---
            # Припускаємо, що predict повертає (id, name, probability)
            predicted_type_id, _, probability = predict(request_text)
            
            # Перевіряємо, чи існує такий тип завдання
            predicted_task_type = TaskType.query.get(predicted_type_id)
            if not predicted_task_type:
                 flash(f"Не вдалося розпізнати тип завдання. Спробуйте перефразувати.", "warning")
                 return redirect(url_for('user_views.new_request'))

            # --- 2. Створення основного завдання (Task) ---
            new_task = Task(
                text=request_text.strip(),
                priority=predicted_task_type.priority, # Пріоритет береться з типу
                customer_id=current_user.worker_id,
                status=TaskStatusEnum.NEW # Початковий статус
            )
            db.session.add(new_task)
            db.session.flush() # Отримуємо ID для наступних кроків

            # --- 3. Створення запису Task_TaskType ---
            new_task_type_link = Task_TaskType(
                task_id=new_task.id,
                tasktype_id=predicted_task_type.tasktype_id,
                detection_method=TaskDetectionMethodEnum.NLP_AUTO,
                probability=probability,
                assigned_by_id=None, # Бо визначено автоматично
                is_active=True
            )
            db.session.add(new_task_type_link)

            # --- 4. Визначення та призначення виконавця ---
            assignment_result = choose_worker(task=new_task)
            print(assignment_result)

            if assignment_result:
                new_assignment = WorkerTask(
                    task_id=new_task.id,
                    worker_id=assignment_result['worker_id'],
                    assign_method=assignment_result['method'],
                    assigned_by_id=current_user.id, # Ініційовано системою/користувачем
                    status=WorkerTaskStatusEnum.ACTIVE
                )
                db.session.add(new_assignment)
                flash_msg = "Вашу заявку прийнято та призначено виконавця!"
                flash_category = "success"
            else:
                # Якщо choose_worker повернув None (навіть менеджера не знайдено)
                flash_msg = "Вашу заявку прийнято, але не вдалося знайти виконавця. Зверніться до вашого менеджера."
                flash_category = "warning"
            
            # --- 5. Збереження ---
            db.session.commit()
            flash(flash_msg, flash_category)
            return redirect(url_for('user_views.user_dashboard'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Сталася непередбачувана помилка при створенні заявки: {e}", "danger")

    # --- GET-запит ---
    return render_template("user/new_request.html")


@user_views.route('/my_devices')
@login_required
@role_required('User')
def user_devices():
    """Відображає список пристроїв, закріплених за поточним користувачем."""
    
    # Знаходимо всі активні призначення пристроїв для поточного користувача
    my_device_assignments = (
        DeviceWorker.query
        .filter_by(worker_id=current_user.worker_id)
        .options(
            joinedload(DeviceWorker.device).joinedload(Device.device_type) # Завантажуємо дані пристрою та його типу
        )
        .all()
    )
    
    return render_template(
        "user/user_devices.html", 
        assignments=my_device_assignments,
        DeviceStatusEnum=DeviceStatusEnum # Передаємо Enum для перевірок у шаблоні
    )


@user_views.route('/return_device/<int:device_worker_id>', methods=['POST'])
@login_required
@role_required('User')
def return_device(device_worker_id):
    """
    Обробляє запит користувача на повернення ОСОБИСТОГО пристрою.
    Змінює статус пристрою, створює завдання 'DeviceReturn' та призначає виконавця.
    """
    # B-) Змінено модель на DeviceWorker
    assignment_to_return = DeviceWorker.query.get_or_404(device_worker_id)
    device = assignment_to_return.device

    # --- Перевірка прав та статусу ---
    # B-) Перевіряємо, чи це пристрій поточного користувача
    if assignment_to_return.worker_id != current_user.worker_id:
        flash("Ви не можете повернути цей пристрій.", "danger")
        return redirect(url_for('user_views.user_devices'))

    if device.status != DeviceStatusEnum.IN_USE:
        flash(f"Пристрій '{device.name}' не має статусу 'In Use'. Повернення неможливе.", "warning")
        return redirect(url_for('user_views.user_devices'))

    return_task_type = TaskType.query.filter_by(name='Device Return').first()
    if not return_task_type:
        flash("Критична помилка: тип завдання 'DeviceReturn' не знайдено.", "danger")
        return redirect(url_for('user_views.user_devices'))

    try:
        # --- 1. Зміна статусу пристрою ---
        device.status = DeviceStatusEnum.IN_TRANSIT

        # --- 2. Створення завдання (Task) ---
        task_text = (
            f"Завдання на повернення пристрою від користувача.\n" # B-) Змінено текст
            f"Пристрій: {device.name} (SN: {device.serial_number})\n"
            f"Користувач: {current_user.full_name}" # B-) Змінено текст
        )
        new_task = Task(
            text=task_text,
            priority=return_task_type.priority,
            customer_id=current_user.id, # Замовник - користувач
            device_id=device.id
        )
        db.session.add(new_task)
        db.session.flush()

        # --- 3. Створення Task_TaskType ---
        new_task_type_link = Task_TaskType(
            task_id=new_task.id,
            tasktype_id=return_task_type.tasktype_id,
            detection_method=TaskDetectionMethodEnum.MANUAL_OVERRIDE,
            assigned_by_id=current_user.id
        )
        db.session.add(new_task_type_link)

        # --- 4. Призначення виконавця ---
        assignment_result = choose_worker(task=new_task)
        flash_msg = f"Ініційовано повернення пристрою '{device.name}'. Створено завдання для IT-відділу."
        flash_category = "success"
        if assignment_result:
            new_assignment = WorkerTask(
                task_id=new_task.id,
                worker_id=assignment_result['worker_id'],
                assign_method=assignment_result['method'],
                assigned_by_id=current_user.id,
                status=WorkerTaskStatusEnum.ACTIVE
            )
            db.session.add(new_assignment)
            flash_msg += " Завдання призначено."
        else:
            flash_msg = f"Ініційовано повернення пристрою '{device.name}', але не вдалося знайти виконавця. Зверніться до IT-відділу."
            flash_category = "warning"

        # --- 5. Збереження ---
        db.session.commit()
        flash(flash_msg, flash_category)

    except Exception as e:
        db.session.rollback()
        flash(f"Сталася помилка при ініціації повернення: {e}", "danger")
        traceback.print_exc()

    return redirect(url_for('user_views.user_devices'))

@user_views.route('/new_personal_device_request', methods=['GET', 'POST'])
@login_required
@role_required('User')
def new_personal_device_request():
    """Сторінка для створення заявки на новий особистий пристрій."""

    if request.method == 'POST':
        try:
            form_data = request.form
            device_type_id = form_data.get('device_type_id')
            justification = form_data.get('justification')

            if not device_type_id or not justification:
                flash("Будь ласка, оберіть тип пристрою та вкажіть обґрунтування.", "danger")
                return redirect(url_for('user_views.new_personal_device_request'))

            device_type = DeviceType.query.get(device_type_id)
            # Використовуємо той самий тип завдання 'DeviceRequest'
            request_task_type = TaskType.query.filter_by(name='Device Management').first()
            if not request_task_type:
                flash("Критична помилка: тип завдання 'Device Request' не знайдено.", "danger")
                return redirect(url_for('user_views.new_personal_device_request'))

            # Збираємо бажані характеристики
            desired_specs = []
            for key, value in form_data.items():
                if key.startswith('attr_') and value.strip():
                    attribute_id = int(key.split('_')[1])
                    attribute = DeviceAttribute.query.get(attribute_id)
                    if attribute:
                        desired_specs.append(f"- {attribute.name}: {value.strip()}")

            specs_text = "\n\n--- Бажані характеристики ---\n" + "\n".join(desired_specs) if desired_specs else ""
            task_text = (
                f"Запит на новий ОСОБИСТИЙ пристрій.\n"
                f"Тип пристрою: {device_type.name}.\n"
                # B-) Додаємо ID у текст
                f"Призначення: для працівника ID:{current_user.id} ({current_user.full_name}).\n\n"
                f"Обґрунтування: {justification}"
                f"{specs_text}"
            )

            # Створення Task та Task_TaskType
            new_task = Task(text=task_text, priority=request_task_type.priority, customer_id=current_user.id)
            db.session.add(new_task)
            db.session.flush()

            new_task_type_link = Task_TaskType(
                task_id=new_task.id,
                tasktype_id=request_task_type.tasktype_id,
                detection_method=TaskDetectionMethodEnum.MANUAL_OVERRIDE,
                assigned_by_id=current_user.id # Ініційовано користувачем
            )
            db.session.add(new_task_type_link)

            # Призначення виконавця
            assignment_result = choose_worker(task=new_task)
            flash_msg = "Заявку на новий пристрій успішно створено!"
            flash_category = "success"
            if assignment_result:
                new_assignment = WorkerTask(
                    task_id=new_task.id,
                    worker_id=assignment_result['worker_id'],
                    assign_method=assignment_result['method'],
                    assigned_by_id=current_user.id,
                    status=WorkerTaskStatusEnum.ACTIVE
                )
                db.session.add(new_assignment)
                flash_msg += " Виконавця призначено."
            else:
                flash_msg += " Не вдалося знайти виконавця. Зверніться до IT-відділу."
                flash_category = "warning"

            db.session.commit()
            flash(flash_msg, flash_category)
            # Перенаправляємо на сторінку "Мої заявки"
            return redirect(url_for('user_views.user_dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f"Сталася помилка при створенні заявки: {e}", "danger")
            traceback.print_exc()

    # --- GET-запит ---
    # Передаємо типи пристроїв, які користувач може замовити (можна додати фільтрацію за потребою)
    available_device_types = DeviceType.query.order_by(DeviceType.name).all()
    return render_template("user/new_personal_device_request.html", device_types=available_device_types)

@user_views.route('/request_repair/<int:device_id>', methods=['POST'])
@login_required
@role_required('User')
def request_repair(device_id):
    """Обробляє запит користувача на ремонт пристрою."""
    device_to_repair = Device.query.get_or_404(device_id)
    current_assignment = DeviceWorker.query.filter_by(
        device_id=device_id, worker_id=current_user.worker_id, status=AssignmentStatusEnum.ACTIVE
    ).first()

    # --- Перевірки безпеки та статусу ---
    if not current_assignment:
        flash("Ви не можете створити запит на ремонт для цього пристрою.", "danger")
        return redirect(url_for('user_views.user_devices'))
    if device_to_repair.status != DeviceStatusEnum.IN_USE:
        flash(f"Пристрій '{device_to_repair.name}' не має статусу 'In Use'. Запит неможливий.", "warning")
        return redirect(url_for('user_views.user_devices'))

    repair_task_type = TaskType.query.filter_by(name='Device Repair').first()
    if not repair_task_type:
        flash("Критична помилка: тип завдання 'DeviceRepair' не знайдено.", "danger")
        return redirect(url_for('user_views.user_devices'))

    # --- B-) Отримуємо опис проблеми з форми ---
    problem_description = request.form.get('problem_description')
    if not problem_description or len(problem_description.strip()) < 10:
         flash("Будь ласка, детально опишіть проблему (мін. 10 символів).", "warning")
         # Повертаємося на ту саму сторінку, щоб користувач міг виправити
         return redirect(url_for('user_views.user_devices'))

    try:
        # --- 1. Створення завдання (Task) ---
        # B-) Додаємо опис проблеми до тексту завдання
        task_text = (
            f"Запит на ремонт пристрою.\n"
            f"Пристрій: {device_to_repair.name} (SN: {device_to_repair.serial_number})\n"
            f"Користувач: {current_user.full_name}\n\n"
            f"Опис проблеми: {problem_description.strip()}"
        )
        new_task = Task(
            text=task_text,
            priority=repair_task_type.priority, # Високий пріоритет для ремонтів
            customer_id=current_user.id,
            device_id=device_to_repair.id # Пов'язуємо з пристроєм
        )
        db.session.add(new_task)
        db.session.flush()

        # --- 2. Створення Task_TaskType ---
        new_task_type_link = Task_TaskType(
            task_id=new_task.id,
            tasktype_id=repair_task_type.tasktype_id,
            detection_method=TaskDetectionMethodEnum.MANUAL_OVERRIDE,
            assigned_by_id=current_user.id
        )
        db.session.add(new_task_type_link)

        # --- 3. Призначення виконавця ---
        assignment_result = choose_worker(task=new_task)
        flash_msg = f"Запит на ремонт пристрою '{device_to_repair.name}' створено."
        flash_category = "success"
        if assignment_result:
            new_assignment = WorkerTask(
                task_id=new_task.id,
                worker_id=assignment_result['worker_id'],
                assign_method=assignment_result['method'],
                assigned_by_id=current_user.id,
                status=WorkerTaskStatusEnum.ACTIVE
            )
            db.session.add(new_assignment)
            flash_msg += " Виконавця призначено."
        else:
            flash_msg += " Не вдалося знайти виконавця. Зверніться до IT-відділу."
            flash_category = "warning"

        # --- 4. Збереження ---
        db.session.commit()
        flash(flash_msg, flash_category)

    except Exception as e:
        db.session.rollback()
        flash(f"Сталася помилка при створенні запиту на ремонт: {e}", "danger")
        traceback.print_exc()

    return redirect(url_for('user_views.user_devices'))

# # @user_views.route('/user_requests', methods=['GET', 'POST'])
# # @login_required
# # @role_required([3]) #User
# # def user_requests():
# #     tasks = Task.query.join(Worker, Task.created_by == Worker.id) \
# #                 .filter(Task.created_by == current_user.id) \
# #                 .all()  
# #     status_column = inspect(Task).columns.status
# #     statuses = status_column.type.enums
# #     return render_template("user/user_requests.html", user=current_user, tasks = tasks, statuses=statuses)



# @user_views.route('/cancel_request/<int:task_id>', methods=['POST'])
# @login_required
# @role_required('User') 
# def cancel_request(task_id):
#     task = Task.query.get_or_404(task_id)
#     workertask = (
#         db.session.query(WorkerTask)
#         .filter(WorkerTask.task_id == task_id)
#         .filter(WorkerTask.status == 'active')
#         .first()
#     )

#     if request.method == 'POST':
#         task.status = 'canceled'
#         task.finished_at = datetime.utcnow()

#         workertask.status = 'canceled'
#         workertask.finished_at = datetime.utcnow()

#         db.session.commit()


#     # device_request = DeviceRequest.query.filter(DeviceRequest.task_id == task_id).first()

#     # if task.status == 'Not started':
#     #     if task.type_id == 5:
#     #         device_request = DeviceRequest.query.filter(DeviceRequest.task_id == task_id).first()
        
#     #         if device_request:
#     #             db.session.delete(device_request)
#     #             db.session.commit()
#     #     db.session.delete(task)
#     #     db.session.commit()
#     #     flash('Task deleted successfully.', 'success')

#     return redirect(url_for('user_views.user_dashboard'))

# # #MANAGE PROFILES

# @user_views.route('/profile', methods=['GET', 'POST'])
# @login_required
# @role_required('User') 
# def user_profile():
#     if request.method == 'POST':
#         new_phone = request.form.get('phone')
#         new_email = request.form.get('email')
#         new_password = request.form.get('password')
#         confirm_password = request.form.get('password2')

#         # --- EMAIL ---
#         if new_email:
#             if len(new_email) < 6:
#                 flash('Email must be at least 6 characters.', 'error')
#             elif new_email != current_user.email:
#                 if Worker.query.filter_by(email=new_email).first():
#                     flash('Цей email вже використовується.', 'error')
#                 else:
#                     current_user.email = new_email

#         # --- PHONE ---
#         if new_phone:
#             if not new_phone.isdigit():
#                 flash('Phone number should contain only numbers.', 'error')
#             elif new_phone != current_user.phone:
#                 current_user.phone = new_phone

#         # --- PASSWORD ---
#         if new_password or confirm_password:
#             if new_password != confirm_password:
#                 flash('Паролі не співпадають.', 'error')
#             elif len(new_password) < 7:
#                 flash('Password must be at least 7 characters.', 'error')
#             else:
#                 current_user.password_hash = generate_password_hash(
#                     new_password, method='pbkdf2:sha256'
#                 )

#         db.session.commit()
#         flash('Дані успішно оновлені ✅', 'success')
#         return redirect(url_for('user_views.user_profile'))

#     # ---- JOIN для поточного користувача ----
#     try:
#         WD = aliased(WorkerDepartment)

#         profile_data = (
#             db.session.query(
#                 Worker.worker_id,
#                 Worker.surname,
#                 Worker.name,
#                 Worker.username,
#                 Worker.email,
#                 Worker.phone,
#                 Worker.date_of_birth,
#                 Department.name.label("department_name"),
#                 WD.title.label("title")
#             )
#             .join(WD, Worker.worker_id == WD.worker_id)
#             .join(Department, WD.department_id == Department.department_id)
#             .filter(Worker.worker_id == current_user.worker_id)
#             .all()
#         )

#     except SQLAlchemyError as e:
#         print(f"SQLAlchemy Error: {e}")
#         return "Database connection or query error", 500
     
#     return render_template("user/user_profile.html", user=current_user, profile_data=profile_data)


# # @user_views.route('/user_profile/<user_id>', methods=['GET', 'POST'])
# # @login_required
# # @role_required([3]) 
# # def view_profile(user_id):
# #     user = Worker.query \
# #                 .join(Department) \
# #                 .filter(Worker.id == user_id) \
# #                 .first()
     
# #     return render_template("user/view_profile.html", user=user)

# # #REVIEW TASKS

# # @user_views.route('/review_request/<task_id>', methods=['GET', 'POST'])
# # @login_required
# # @role_required([3]) 
# # def review_request(task_id):
# #     task = Task.query.get_or_404(task_id)
# #     task_type = TaskType.query.get_or_404(task.type_id).name
# #     status_column = inspect(Task).columns.status
# #     statuses = status_column.type.enums
    

# #     if task_type == 'Device issue':
# #         return redirect(url_for('user_views.review_device_request', task_id=task_id))
    
# #     if task_type == 'Device return':
# #         return redirect(url_for('user_views.return_device_request', task_id=task_id))
    
# #     if request.method == 'POST':
# #         new_status = request.form.get('status')
# #         task_type = TaskType.query.get_or_404(task.type_id).name

# #         if new_status and new_status in ['Not started', 'In progress', 'Completed', 'Frozen']:
# #             if new_status == 'Completed' and not task.completed_time:
# #                     task.completed_time = datetime.now()              
# #             elif new_status != 'Completed':
# #                 task.completed_time = None
# #             task.status = new_status
# #             db.session.commit()
# #             return redirect(url_for('user_views.review_request', task_id=task_id))


# #     return render_template("user/review_request.html", task=task, statuses=statuses)

# # @user_views.route('/reassign_request/<task_id>', methods=['GET', 'POST'])
# # @login_required
# # @role_required([3]) 
# # def reassign_request(task_id):
# #     task = Task.query.get_or_404(task_id)

# #     if request.method == 'POST':
# #         workers = TaskTypeWorker.query \
# #                 .join(Worker) \
# #                 .filter(Worker.role_id == 3) \
# #                 .filter(TaskTypeWorker.tasktype_id == int(task.task_type)) \
# #                 .filter(Worker.id != current_user.id) \
# #                 .filter(Worker.status == 'active') \
# #                 .all()

# #         if workers:       
# #             random_worker = random.choice(workers)

# #         task.worker_id = random_worker
# #         task.status = 'Not started'
# #         db.session.commit()
# #         flash("You reassigned task id: {}".format(str(task_id)), 'success')
# #         return redirect(url_for('user_views.user_dashboard'))

# #     return render_template("user/user_dashboard.html", task=task)

# # #MANAGE DEVICES (USER)

# # @user_views.route('/user_devices', methods=['GET', 'POST'])
# # @login_required
# # @role_required([3])
# # def user_devices():
# #     user_devices = DeviceWorker.query \
# #         .join(DeviceRequest, DeviceWorker.request_id == DeviceRequest.id) \
# #         .join(Device, DeviceWorker.device_id == Device.device_id) \
# #         .join(DeviceBrand, Device.device_brand_id == DeviceBrand.id) \
# #         .join(DeviceType, Device.device_type_id == DeviceType.id) \
# #         .filter(DeviceWorker.created_by_id == current_user.id) \
# #         .all()
    
# #     devicetypes = DeviceType.query.all()
# #     devicebrands = DeviceBrand.query.all()
# #     status_column = inspect(DeviceWorker).columns.status
# #     statuses = status_column.type.enums

# #     for user_device in user_devices:
# #         print(user_device.device.device_name)
# #         print(user_device.status)

    
# #     return render_template("user/user_devices.html", user=current_user, user_devices = user_devices, devicetypes=devicetypes, devicebrands=devicebrands, statuses=statuses)

# # @user_views.route('/request_new_device', methods=['GET', 'POST'])
# # @login_required
# # @role_required([3])
# # def request_new_device():
# #     device_types = DeviceType.query.all()

# #     managers = Worker.query \
# #         .join(Department) \
# #         .filter(Worker.role_id == 2) \
# #         .filter(Department.id == current_user.department_id) \
# #         .filter(Worker.status == 'active') \
# #         .all()
# #     random_manager = random.choice(managers)

# #     workers = TaskTypeWorker.query \
# #         .join(Worker) \
# #         .filter(Worker.role_id == 3) \
# #         .filter(TaskTypeWorker.tasktype_id == 5) \
# #         .filter(Worker.id != current_user.id) \
# #         .filter(Worker.status == 'active') \
# #         .all()
    
# #     random_worker = random.choice(workers)

    
# #     if request.method == 'POST':
# #         device_id = request.form['device_type']
# #         notes = request.form['additional_notes']

# #         device = DeviceType.query.get_or_404(device_id)
# #         device_name = device.name

# #         task_text = f"New device request. Type: {device_name}. Notes: {notes}"

# #         task = Task(created_by=current_user.id, status="Not started", text=task_text, manager_id=random_manager.id, type_id = 5, worker_id = random_worker.worker_id)
# #         db.session.add(task)
# #         db.session.commit()

# #         # Create and add a new DeviceRequest instance
# #         device_request = DeviceRequest(created_by_id=int(current_user.id), created_date=datetime.now(), device_type_id=int(device_id), notes=notes, task_id=task.id)
# #         db.session.add(device_request)

# #         db.session.commit()
# #         flash('You created a new device request.', 'success')
# #         return redirect(url_for('user_views.user_requests'))
    
# #     return render_template("user/request_new_device.html", user=current_user, device_types=device_types)



# # @user_views.route('/confirm_device/<int:device_id>', methods=['POST'])
# # @login_required
# # @role_required([3])
# # def confirm_device(device_id):
# #     device = Device.query.get_or_404(device_id)
# #     device_worker = DeviceWorker.query.filter(DeviceWorker.device_id == device_id).filter(DeviceWorker.created_by_id == current_user.id).first_or_404()
# #     dv_task = DeviceWorker.query \
# #         .join(DeviceRequest, DeviceWorker.request_id == DeviceRequest.id) \
# #         .with_entities(DeviceRequest.task_id) \
# #         .first()
# #     task = Task.query.filter(Task.id == dv_task.task_id).first()

# #     device.status = 'Occupied'
# #     device_worker.status = 'In progress'
# #     device_worker.received_date = datetime.now()
# #     task.status = 'Completed'
#     task.completed_time = datetime.now()
    
#     db.session.commit()

#     return redirect(url_for('user_views.user_devices', user=current_user))


# @user_views.route('/return_device/<int:device_id>', methods=['GET', 'POST'])
# @login_required
# @role_required([3])
# def return_device(device_id):
#     managers = Worker.query \
#         .join(Department) \
#         .filter(Worker.role_id == 2) \
#         .filter(Department.id == current_user.department_id) \
#         .filter(Worker.status == 'active') \
#         .all()
#     random_manager = random.choice(managers)

#     workers = TaskTypeWorker.query \
#         .join(Worker) \
#         .filter(Worker.role_id == 3) \
#         .filter(TaskTypeWorker.tasktype_id == 6) \
#         .filter(Worker.id != current_user.id) \
#         .filter(Worker.status == 'active') \
#         .all()
    
#     random_worker = random.choice(workers)

#     device_worker = DeviceWorker.query.filter(DeviceWorker.device_id == device_id).filter(DeviceWorker.created_by_id == current_user.id).first_or_404()

#     if request.method == 'POST':
#         device = Device.query.get_or_404(device_id)
#         device.status = 'Returned'

#         device_worker.status = 'Finished'
#         device_worker.returned_date = datetime.now() 

#         task_text = f"Return device. Name: {device.device_name}. Serial number: {device.serial_number}"

#         task = Task(created_by = current_user.id, created_time = datetime.now(), status='Not started', type_id = 6, manager_id = random_manager.id, text = task_text, worker_id = random_worker.worker_id)
#         db.session.add(task)
#         db.session.commit()

#         device_return_request = DeviceReturnRequest(created_by_id=int(current_user.id), device_id=device.device_id, notes=task_text, task_id=task.id)
#         db.session.add(device_return_request)
       
#         db.session.commit()

#         return redirect(url_for('user_views.user_devices'))


#     return render_template("user/user_devices.html", user=current_user)



# # MANAGE DEVICES (WORKER)
# @user_views.route('/review_device_request/<task_id>', methods=['GET', 'POST'])
# @login_required
# @role_required([3]) 
# def review_device_request(task_id):
#     task = Task.query.get_or_404(task_id)
#     status_column = inspect(Task).columns.status
#     statuses = status_column.type.enums
#     device_request = DeviceRequest.query.filter(DeviceRequest.task_id == task.id).first()
#     # WORK IN PROGRESS
#     print(device_request)
#     avail_devices = Device.query.filter(Device.device_type_id == device_request.device_type_id).filter(Device.status == 'Available').all()


#     if request.method == 'POST':
#         device_id = request.form['device']
#         device = Device.query.get_or_404(device_id)

#         device.status = 'Sent'
#         device_request.status = 'Processing'
#         task.status = 'In progress'

#         new_deviceworker = DeviceWorker(device_id=device_id, created_by_id=device_request.created_by_id, request_id=device_request.id, status='Processing', worker_id=current_user.id)
#         db.session.add(new_deviceworker)
#         db.session.commit()
#         return redirect(url_for('user_views.user_dashboard', task_id=task_id))
        

#     return render_template("user/review_device_request.html", user=current_user, task=task, devices=avail_devices, statuses=statuses)

# @user_views.route('/return_device_request/<task_id>', methods=['GET', 'POST'])
# @login_required
# @role_required([3]) 
# def return_device_request(task_id):
#     task = Task.query.get_or_404(task_id)
#     status_column = inspect(Task).columns.status
#     statuses = status_column.type.enums
    

#     device_request = DeviceReturnRequest.query \
#         .join(Task, Task.id == DeviceReturnRequest.task_id) \
#         .filter(Task.id == task_id) \
#         .first()


#     device = Device.query.get_or_404(device_request.device_id)

#     workers = TaskTypeWorker.query \
#         .join(Worker) \
#         .filter(Worker.role_id == 3) \
#         .filter(TaskTypeWorker.tasktype_id == 7) \
#         .filter(Worker.id != current_user.id) \
#         .filter(Worker.status == 'active') \
#         .all()
    
#     random_worker = random.choice(workers)

#     managers = Worker.query \
#         .join(Department) \
#         .filter(Worker.role_id == 2) \
#         .filter(Department.id == current_user.department_id) \
#         .filter(Worker.status == 'active') \
#         .all()
#     random_manager = random.choice(managers)

#     user_devices = DeviceWorker.query \
#         .filter(DeviceWorker.device_id == device_request.device_id) \
#         .first()
#     print(user_devices)

#     if request.method == 'POST':
#         device_status = request.form['deviceStatus']
#         notes = request.form['repairNotes']

#         task.status = 'Completed'
#         task.completed_time = datetime.now()
#         user_devices.returned_date = datetime.now()
#         user_devices.status = 'Finished'

#         db.session.commit()

#         if device_status == 'In repairs':

#             task_text = f"Repair device. Name: {device.device_name}. Serial number: {device.serial_number} Notes: {notes}"

#             task = Task(created_by = current_user.id, created_time = datetime.now(), status='Not started', type_id = 7, manager_id = random_manager.id, text = task_text, worker_id = random_worker.worker_id)
#             db.session.add(task)
#             db.session.commit()

#             repair_request =  RepairRequest(created_by_id=int(current_user.id), device_id=device.device_id, task_id=task.id)
#             db.session.add(repair_request)
#             db.session.commit()
#         else:
#             device.status = 'Available'

#         db.session.commit()
#         return redirect(url_for('user_views.user_dashboard', task_id=task_id))
        

#     return render_template("user/return_device_request.html", user=current_user, task=task, device=device, statuses = statuses)



# @user_views.route('/questions', methods=['GET', 'POST'])
# @login_required
# @role_required([3])
# def questions():
#     return render_template("user/questions.html")