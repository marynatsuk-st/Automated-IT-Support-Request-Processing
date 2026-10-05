from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify 
from flask_login import login_required, current_user
from .decorators import role_required 
import traceback

from .worker_assign import choose_worker

from .models import (
    Worker, Department, Role, WorkerDepartment, WorkerRole, WorkerTaskType,
    Task, TaskType, WorkerTask, Device, DeviceWorker, DeviceDepartment,
    DeviceType, DeviceAttribute, DeviceAttributeValue, DeviceTypeAttribute,
    Task_TaskType,
    WorkerStatusEnum, HistoryStatusEnum, TaskStatusEnum, TaskDetectionMethodEnum,
    WorkerTaskStatusEnum, WorkerTaskAssignmentMethodEnum, DeviceStatusEnum, AssignmentStatusEnum
)
from . import db
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect, asc, desc
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import subqueryload 
import re

manager_views = Blueprint('manager_views', __name__, template_folder='manager')

@manager_views.route('/dashboard', methods=['GET', 'POST'])
@login_required
@role_required('Manager') #Manager
def manager_dashboard():
    """
    Головна панель менеджера. Показує всі призначення завдань
    для працівників, які є підлеглими поточного менеджера.
    """
    
    # --- B-) НОВИЙ, ЕФЕКТИВНИЙ ЗАПИТ ---
    # Ми запитуємо WorkerTask (призначення) і одразу "жадібно" завантажуємо 
    # пов'язані об'єкти, щоб уникнути "N+1" запитів у шаблоні.
    assignments = (
        WorkerTask.query
        .join(WorkerTask.worker) # Приєднуємо таблицю Worker для фільтрації
        .filter(Worker.manager_id == current_user.worker_id) # Головний фільтр: тільки мої підлеглі
        .options(
            joinedload(WorkerTask.worker), # Завантажуємо дані виконавця
            joinedload(WorkerTask.task).joinedload(Task.customer) # Завантажуємо завдання та його замовника
        )
        .order_by(desc(WorkerTask.assigned_at)) # Сортуємо за датою призначення
        .all()
    )

    # Готуємо дані для фільтрів у шаблоні
    task_types_for_filter = TaskType.query.order_by(TaskType.name).all()
    status_options_for_filter = list(TaskStatusEnum)

    return render_template(
        "manager/manager_dashboard.html", 
        assignments=assignments,
        task_types=task_types_for_filter,
        statuses=status_options_for_filter
    )

@manager_views.route('/manager_new_requests', methods=['GET', 'POST'])
@login_required
@role_required('Manager') #Manager
def manage_new_requests():

    
    # --- B-) НОВИЙ, ЕФЕКТИВНИЙ ЗАПИТ ---
    # Ми запитуємо WorkerTask (призначення) і одразу "жадібно" завантажуємо 
    # пов'язані об'єкти, щоб уникнути "N+1" запитів у шаблоні.
    assignments = (
        WorkerTask.query
        .join(WorkerTask.worker) # Приєднуємо таблицю Worker для фільтрації
        .filter(Worker.worker_id == current_user.worker_id) # Головний фільтр: тільки мої підлеглі
        .options(
            joinedload(WorkerTask.worker), # Завантажуємо дані виконавця
            joinedload(WorkerTask.task).joinedload(Task.customer) # Завантажуємо завдання та його замовника
        )
        .order_by(desc(WorkerTask.assigned_at)) # Сортуємо за датою призначення
        .all()
    )

    # Готуємо дані для фільтрів у шаблоні
    task_types_for_filter = TaskType.query.order_by(TaskType.name).all()
    status_options_for_filter = list(TaskStatusEnum)

    traceback.print_exc()

    return render_template(
        "manager/manage_new_requests.html", 
        assignments=assignments,
        task_types=task_types_for_filter,
        statuses=status_options_for_filter
    )

@manager_views.route('/request/<int:workertask_id>', methods=['GET', 'POST'])
@login_required
@role_required('Manager')
def edit_request(workertask_id):
    assignment = WorkerTask.query.get_or_404(workertask_id)
    task = assignment.task

    # if assignment.worker.manager_id != current_user.worker_id:
    #     flash("Ви не маєте права редагувати це призначення.", "danger")
    #     return redirect(url_for('manager_views.manager_dashboard'))

    if request.method == 'POST':
        try:
            changes_made = False
            redirect_target_id = workertask_id

            # --- 1. Обробка зміни ТИПУ ЗАВДАННЯ ---
            new_tasktype_id = int(request.form.get("tasktype_id"))
            active_type_record = task.active_task_type_record
            
            type_has_changed = False
            if active_type_record:
                if active_type_record.tasktype_id != new_tasktype_id:
                    active_type_record.is_active = False
                    type_has_changed = True
            elif new_tasktype_id: # Якщо раніше типу не було
                type_has_changed = True

            if type_has_changed:
                new_type_link = Task_TaskType(
                    task_id=task.id,
                    tasktype_id=new_tasktype_id,
                    detection_method=TaskDetectionMethodEnum.MANUAL_OVERRIDE,
                    assigned_by_id=current_user.id,
                    is_active=True
                )
                db.session.add(new_type_link)
                changes_made = True

            # --- 2. Обробка зміни ВИКОНАВЦЯ ---
            new_worker_id = int(request.form.get("worker_id"))
            if assignment.worker_id != new_worker_id:
                assignment.status = WorkerTaskStatusEnum.REASSIGNED
                assignment.unassigned_at = datetime.utcnow()
                assignment.unassigned_by_id = current_user.id

                new_assignment = WorkerTask(
                    task_id=task.id,
                    worker_id=new_worker_id,
                    assigned_by_id=current_user.id,
                    assign_method=WorkerTaskAssignmentMethodEnum.MANUAL,
                    status=WorkerTaskStatusEnum.ACTIVE
                )
                db.session.add(new_assignment)
                changes_made = True
                
                # Потрібно отримати ID нового призначення для редіректу
                db.session.flush() 
                redirect_target_id = new_assignment.id

            # --- 3. ЄДИНИЙ COMMIT в кінці ---
            if changes_made:
                db.session.commit()
                flash("Зміни успішно збережено!", "success")
            else:
                flash("Ви не внесли жодних змін.", "info")

            return redirect(url_for("manager_views.edit_request", workertask_id=redirect_target_id))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Сталася помилка: {e}", "danger")
            return redirect(url_for("manager_views.edit_request", workertask_id=workertask_id))

    # ... (Ваш код для GET-запиту залишається без змін) ...
    all_task_types = TaskType.query.order_by(TaskType.name).all()

    return render_template(
        "manager/edit_request.html",
        assignment=assignment,
        all_task_types=all_task_types
    )


@manager_views.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('Manager')
def manager_profile():
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
        
        return redirect(url_for('manager_views.manager_profile'))

    # --- GET-запит: просто передаємо поточного користувача в шаблон ---
    # Всю інформацію про відділ/роль ми отримаємо через relationships прямо в HTML
    return render_template("manager/manager_profile.html", user=current_user)




@manager_views.route('/manage_workers')
@login_required
@role_required('Manager')
def manage_workers():
    """
    Сторінка для перегляду списку підлеглих працівників поточного менеджера.
    """
    
    # B-) --- СПРОЩЕНИЙ ЗАПИТ БЕЗ EAGER LOADING ---
    # Ми просто отримуємо список підлеглих. Всі пов'язані дані (компетенції, типи завдань)
    # будуть завантажуватися автоматично в шаблоні, коли до них буде звернення.
    subordinates = (
        Worker.query
        .filter(Worker.manager_id == current_user.worker_id)
        .order_by(Worker.surname, Worker.name)
        .all()
    )
    
    # Дані для фільтрів
    task_types_for_filter = TaskType.query.order_by(TaskType.name).all()

    return render_template(
        "manager/manager_workers.html",
        subordinates=subordinates,
        task_types=task_types_for_filter,
        HistoryStatusEnum=HistoryStatusEnum
    )

@manager_views.route('/edit_worker/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('Manager')
def edit_worker_profile(user_id):
    """
    Сторінка для менеджера для редагування профілю та компетенцій підлеглого.
    """
    worker_to_edit = Worker.query.get_or_404(user_id)

    # --- Ключова перевірка безпеки ---
    # Переконуємося, що менеджер редагує саме свого підлеглого.
    if worker_to_edit.manager_id != current_user.worker_id:
        flash("Ви не маєте права редагувати профіль цього працівника.", "danger")
        return redirect(url_for('manager_views.manage_workers'))

    if request.method == 'POST':
        try:
            # --- 1. Обробка зміни КОМПЕТЕНЦІЙ ---
            selected_ids = set(request.form.getlist('tasktypes', type=int))
            current_competencies = worker_to_edit.task_type_competencies.filter_by(status=HistoryStatusEnum.ACTIVE).all()
            current_ids = {c.tasktype_id for c in current_competencies}

            # а) Додаємо нові компетенції
            ids_to_add = selected_ids - current_ids
            for tasktype_id in ids_to_add:
                new_competency = WorkerTaskType(
                    worker=worker_to_edit,
                    tasktype_id=tasktype_id,
                    status=HistoryStatusEnum.ACTIVE
                )
                db.session.add(new_competency)

            # б) Деактивуємо зняті компетенції
            ids_to_remove = current_ids - selected_ids
            if ids_to_remove:
                # Ефективно оновлюємо кілька записів одним запитом
                WorkerTaskType.query.filter(
                    WorkerTaskType.worker_id == user_id,
                    WorkerTaskType.tasktype_id.in_(ids_to_remove),
                    WorkerTaskType.status == HistoryStatusEnum.ACTIVE
                ).update({
                    'status': HistoryStatusEnum.INACTIVE,
                    'end_date': datetime.utcnow()
                }, synchronize_session=False)

            # --- 2. Обробка зміни СТАТУСУ та ДАТИ НЕДОСТУПНОСТІ ---
            new_status = WorkerStatusEnum(request.form['worker_status'])
            unavailable_until_str = request.form.get("unavailable_until")
            
            # (Використовуємо ту саму надійну логіку, що й на сторінці адміна)
            if new_status == WorkerStatusEnum.ACTIVE:
                worker_to_edit.worker_status = WorkerStatusEnum.ACTIVE
                worker_to_edit.unavailable_until = None
            elif new_status == WorkerStatusEnum.ON_VACATION:
                if unavailable_until_str:
                    worker_to_edit.worker_status = WorkerStatusEnum.ON_VACATION
                    worker_to_edit.unavailable_until = datetime.strptime(unavailable_until_str, "%Y-%m-%d").date()
                else:
                    flash("Для статусу 'On Vacation' необхідно вказати дату.", "danger")
                    # Повертаємося без збереження, щоб менеджер виправив помилку
                    return redirect(url_for('manager_views.edit_worker_profile', user_id=user_id))
            else:
                worker_to_edit.worker_status = new_status
                worker_to_edit.unavailable_until = None
            
            db.session.commit()
            flash(f"Дані працівника {worker_to_edit.full_name} успішно оновлено!", "success")
            return redirect(url_for('manager_views.manage_workers'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Сталася помилка при оновленні: {e}", "danger")

    # --- GET-запит: готуємо дані для відображення форми ---
    all_task_types = TaskType.query.order_by(TaskType.name).all()
    
    # Створюємо set з ID поточних активних компетенцій для легкої перевірки в шаблоні
    current_competency_ids = {
        c.tasktype_id for c in worker_to_edit.task_type_competencies.filter_by(status=HistoryStatusEnum.ACTIVE)
    }
    
    status_options = list(WorkerStatusEnum)
    
    return render_template(
        "manager/edit_worker_profile.html",
        worker=worker_to_edit,
        all_task_types=all_task_types,
        current_competency_ids=current_competency_ids,
        status_options=status_options
    )


@manager_views.route('/manage_devices', methods=['GET', 'POST'])
@login_required
@role_required('Manager')
def manage_devices():
    manager_dept_record = current_user.current_department_record
    if not manager_dept_record:
        flash("Ваш відділ не налаштовано. Неможливо виконати дію.", "warning")
        # Передаємо порожні списки, щоб уникнути помилок у шаблоні
        return render_template("manager/manager_devices.html", personal_assignments=[], department_assignments=[], device_types=[])

    if request.method == 'POST':
        try:
            form_data = request.form
            device_type_id = form_data.get('device_type_id')
            justification = form_data.get('justification')

            if not device_type_id or not justification:
                flash("Будь ласка, заповніть поля 'Тип пристрою' та 'Обґрунтування'.", "danger")
                return redirect(url_for('manager_views.manage_devices'))

            device_type = DeviceType.query.get(device_type_id)
            request_task_type = TaskType.query.filter_by(name='Device Management').first()
            if not request_task_type:
                flash("Критична помилка: системний тип завдання 'Device Management' не знайдено.", "danger")
                return redirect(url_for('manager_views.manage_devices'))

            # B-) Збираємо всі бажані характеристики з динамічних полів
            desired_specs = []
            for key, value in form_data.items():
                if key.startswith('attr_') and value.strip(): # Зберігаємо тільки якщо поле не порожнє
                    attribute_id = int(key.split('_')[1])
                    attribute = DeviceAttribute.query.get(attribute_id)
                    if attribute:
                        desired_specs.append(f"- {attribute.name}: {value.strip()}")

            # B-) Формуємо розширений, детальний текст заявки
            specs_text = "\n\n--- Бажані характеристики ---\n" + "\n".join(desired_specs) if desired_specs else ""
            task_text = (
                f"Запит на новий пристрій для відділу '{current_user.current_department.name}'.\n"
                f"Тип пристрою: {device_type.name}.\n\n"
                f"Обґрунтування від менеджера: {justification}"
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
                assigned_by_id=current_user.id
            )
            print(new_task_type_link)
            db.session.add(new_task_type_link)
            
            assignment_result = choose_worker(task=new_task)
            
            if assignment_result:
                # 4. Якщо виконавця знайдено, створюємо запис WorkerTask
                new_assignment = WorkerTask(
                    task_id=new_task.id,
                    worker_id=assignment_result['worker_id'],
                    assign_method=assignment_result['method'],
                    # "Призначено" від імені системи, але ініційовано менеджером
                    assigned_by_id=current_user.id, 
                    status=WorkerTaskStatusEnum.ACTIVE
                )
                db.session.add(new_assignment)
                flash("Заявку створено та автоматично призначено виконавця!", "success")
            else:
                # Цей випадок спрацює, якщо навіть менеджера для ескалації не знайдено
                # Ми все одно створюємо заявку, але вона залишиться без виконавця
                flash("Заявку створено, але не вдалося автоматично знайти виконавця. Будь ласка, зверніться до адміністратора.", "warning")
            
            db.session.commit()
            traceback.print_exc()
            flash("Заявку на новий пристрій успішно створено!", "success")

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Сталася помилка при створенні заявки: {e}", "danger")
            traceback.print_exc()

        return redirect(url_for('manager_views.manage_devices'))

    # GET-запит
    personal_assignments = DeviceWorker.query.filter(
        DeviceWorker.worker_id.in_([sub.id for sub in current_user.subordinates]),
        DeviceWorker.status == AssignmentStatusEnum.ACTIVE
    ).all()
    
    department_assignments = DeviceDepartment.query.filter(
        DeviceDepartment.department_id == manager_dept_record.department_id,
        DeviceDepartment.status == AssignmentStatusEnum.ACTIVE
    ).all()
    
    device_types = DeviceType.query.order_by(DeviceType.name).all()
    
    return render_template(
        "manager/manager_devices.html",
        personal_assignments=personal_assignments,
        department_assignments=department_assignments,
        device_types=device_types,
        subordinates=current_user.subordinates,
        DeviceStatusEnum=DeviceStatusEnum
    )


@manager_views.route('/return_department_device/<int:device_department_id>', methods=['POST'])
@login_required
@role_required('Manager')
def return_department_device(device_department_id):
    """
    Обробляє запит на повернення пристрою відділу.
    Змінює статус пристрою, створює завдання 'DeviceReturn' та призначає виконавця.
    """
    assignment_to_return = DeviceDepartment.query.get_or_404(device_department_id)
    device = assignment_to_return.device
    
    # --- Перевірка прав та статусу ---
    if assignment_to_return.department_id != current_user.current_department.department_id:
        flash("Ви не маєте права керувати пристроями цього відділу.", "danger")
        return redirect(url_for('manager_views.manage_devices'))

    if device.status != DeviceStatusEnum.IN_USE:
        flash(f"Пристрій '{device.name}' не має статусу 'In Use'. Повернення неможливе.", "warning")
        return redirect(url_for('manager_views.manage_devices'))
        
    return_task_type = TaskType.query.filter_by(name='Device Return').first()
    if not return_task_type:
        flash("Критична помилка: системний тип завдання 'DeviceReturn' не знайдено.", "danger")
        return redirect(url_for('manager_views.manage_devices'))

    try:
        # --- 1. Зміна статусу пристрою ---
        device.status = DeviceStatusEnum.IN_TRANSIT

        # --- 2. Створення завдання (Task) ---
        task_text = (
            f"Завдання на повернення пристрою відділу.\n"
            f"Пристрій: {device.name} (SN: {device.serial_number})\n"
            f"Відділ: {assignment_to_return.department.name}\n"
            f"Ініційовано менеджером: {current_user.full_name}"
        )
        new_task = Task(
            text=task_text,
            priority=return_task_type.priority, # Високий пріоритет для повернень
            customer_id=current_user.id, # Формально, замовник - менеджер
            device_id=device.id # Пов'язуємо завдання з пристроєм
        )
        db.session.add(new_task)
        db.session.flush()

        # --- 3. Створення Task_TaskType ---
        new_task_type_link = Task_TaskType(
            task_id=new_task.id,
            tasktype_id=return_task_type.tasktype_id,
            detection_method=TaskDetectionMethodEnum.MANUAL_OVERRIDE, # Створено вручну
            assigned_by_id=current_user.id
        )
        db.session.add(new_task_type_link)

        # --- 4. Призначення виконавця ---
        assignment_result = choose_worker(task=new_task)
        if assignment_result:
            new_assignment = WorkerTask(
                task_id=new_task.id,
                worker_id=assignment_result['worker_id'],
                assign_method=assignment_result['method'],
                assigned_by_id=current_user.id, # Призначено менеджером (ініціатором)
                status=WorkerTaskStatusEnum.ACTIVE
            )
            db.session.add(new_assignment)
            flash_msg = f"Пристрій '{device.name}' відправлено на повернення. Завдання призначено."
        else:
            # Малоймовірно, але можливо
            flash_msg = f"Пристрій '{device.name}' відправлено на повернення, але не вдалося знайти виконавця. Зверніться до адміністратора."
            flash_category = "warning"

        # --- 5. Збереження ---
        db.session.commit()
        flash(flash_msg, "success" if assignment_result else flash_category)

    except Exception as e:
        db.session.rollback()
        flash(f"Сталася помилка при ініціації повернення: {e}", "danger")
        traceback.print_exc()

    return redirect(url_for('manager_views.manage_devices'))


@manager_views.route('/api/workers_for_type/<int:tasktype_id>')
@login_required
@role_required('Manager')
def get_workers_for_type(tasktype_id):
    """
    API-ендпоінт, що повертає JSON-список працівників, які є підлеглими
    менеджера і мають компетенцію для заданого типу завдання.
    """
    available_workers = (
        Worker.query
        .join(Worker.task_type_competencies)
        .filter(
            WorkerTaskType.tasktype_id == tasktype_id,
            WorkerTaskType.status == HistoryStatusEnum.ACTIVE,
            # Важливий фільтр: тільки підлеглі поточного менеджера
            Worker.manager_id == current_user.worker_id
        ).all()
    )
    
    # Перетворюємо результат у список словників, зручний для JSON
    workers_list = [{'id': worker.worker_id, 'full_name': worker.full_name} for worker in available_workers]
    return jsonify(workers_list)