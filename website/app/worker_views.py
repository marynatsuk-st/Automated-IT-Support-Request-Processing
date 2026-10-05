from flask import Blueprint, render_template, url_for
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import desc
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify 
from datetime import datetime
import traceback
import re
from .worker_assign import choose_worker
from werkzeug.security import generate_password_hash

from . import db
from .models import (WorkerTask, Task, Worker, WorkerDepartment, TaskType, Task_TaskType, 
                      TaskStatusEnum, WorkerTaskStatusEnum, Device, DeviceType, DeviceStatusEnum,
                      DeviceWorker, DeviceDepartment, AssignmentStatusEnum, TaskDetectionMethodEnum,
                      WorkerTaskAssignmentMethodEnum)
from .decorators import role_required

worker_views = Blueprint('worker_views', __name__)

@worker_views.route('/dashboard')
@login_required
@role_required('Worker') # Гарантує, що доступ мають лише працівники
def worker_dashboard():
    """
    Відображає список усіх завдань, коли-небудь призначених поточному працівнику,
    включаючи активні, завершені та перепризначені.
    """
    
    # --- ЕФЕКТИВНИЙ ЗАПИТ З ВИКОРИСТАННЯМ RELATIONSHIPS ---
    # Ми запитуємо призначення WorkerTask і "жадібно" завантажуємо всі пов'язані дані.
    my_assignments = (
        WorkerTask.query
        .filter_by(worker_id=current_user.worker_id)
        .options(
            # Жадібно завантажуємо об'єкт 'task', а з нього - об'єкт 'customer'.
            # На цьому зупиняємося. Відділ буде завантажено "ліниво" за потреби.
            joinedload(WorkerTask.task)
            .joinedload(Task.customer)
        )
        .order_by(desc(WorkerTask.assigned_at))
        .all()
    )

    # Передаємо Enum у шаблон для використання у фільтрах
    status_options = list(WorkerTaskStatusEnum)

    return render_template(
        "worker/worker_dashboard.html", 
        assignments=my_assignments,
        statuses=status_options
    )

@worker_views.route('/task/<int:task_id>', methods=['GET', 'POST'])
@login_required
@role_required('Worker')
def view_task(task_id):
    task = Task.query.get_or_404(task_id)
    assignment = task.current_assignment # Використовуємо property для отримання активного призначення


    task_type_name = task.active_task_type.name if task.active_task_type else None

    if task_type_name == 'Device Management':
        if request.method == 'POST':
            try:
                device_id_to_assign = int(request.form.get('device_id'))
                target_info_str = request.form.get('target_info') # 'worker:ID' or 'department'
                
                device = Device.query.get(device_id_to_assign)
                if not device:
                    flash("Обраний пристрій не знайдено (можливо, його видалили).", "danger")
                    return redirect(url_for('worker_views.view_task', task_id=task_id))
                
                if device.status != DeviceStatusEnum.AVAILABLE:
                    flash("Обраний пристрій вже недоступний (його статус змінився). Оновіть сторінку.", "danger")
                    return redirect(url_for('worker_views.view_task', task_id=task_id))
                
                # Призначаємо пристрій
                if target_info_str.startswith('worker:'):
                    try:
                        worker_id = int(target_info_str.split(':')[1])
                        # Перевіряємо, чи існує такий працівник
                        target_worker = Worker.query.get(worker_id)
                        if not target_worker:
                            raise ValueError(f"Працівника з ID {worker_id} не знайдено.")
                        
                        new_device_assignment = DeviceWorker(
                            device_id=device.id, 
                            worker_id=worker_id,
                            status=AssignmentStatusEnum.ACTIVE # B-) Використовуємо Enum
                        )
                        db.session.add(new_device_assignment)
                        assignment_target_msg = f"працівнику {target_worker.full_name}"
                    except (ValueError, IndexError) as e:
                        raise ValueError(f"Некоректний формат цілі призначення для працівника: {target_info_str}. Помилка: {e}")
                    
                elif target_info_str == 'department':
                    department_id = task.customer.current_department.department_id
                    if not department_id:
                         raise ValueError(f"Не вдалося визначити відділ для призначення пристрою (замовник ID: {task.customer_id}).")
                         
                    new_device_assignment = DeviceDepartment(
                        device_id=device.id, 
                        department_id=department_id,
                        status=AssignmentStatusEnum.ACTIVE # B-) Використовуємо Enum
                    )
                    db.session.add(new_device_assignment)
                    assignment_target_msg = f"відділу {task.customer.current_department.name}"
                else:
                    raise ValueError(f"Невідомий тип цілі призначення: {target_info_str}")

                device.status = DeviceStatusEnum.IN_USE

                # Закриваємо завдання
                task.status = TaskStatusEnum.CLOSED
                task.finished_at = datetime.utcnow()

                assignment.status = WorkerTaskStatusEnum.FINISHED
                assignment.finished_at = datetime.utcnow()

                db.session.commit()
                traceback.print_exc()
                flash(f"Пристрій '{device.name}' успішно призначено!", "success")
                return redirect(url_for('worker_views.worker_dashboard'))

            except Exception as e:
                db.session.rollback()
                flash(f"Сталася помилка при призначенні пристрою: {e}", "danger")
                traceback.print_exc()

        # --- GET-запит: логіка рекомендацій ---
        desired_specs = _parse_desired_specs(task.text)
        
        # Визначаємо тип пристрою з тексту
        device_type_name_match = re.search(r"Тип пристрою: (.*?)\.", task.text)
        if not device_type_name_match:
            flash("Не вдалося визначити тип пристрою з тексту заявки.", "warning")
            return render_template('worker/task_device_request.html', task=task, assignment=assignment, recommendations=[])

        device_type = DeviceType.query.filter_by(name=device_type_name_match.group(1)).first()
        print(device_type.name)
        
        recommendations = []
        if device_type:
            available_devices = Device.query.filter_by(
                device_type_id=device_type.id,
                status=DeviceStatusEnum.AVAILABLE
            ).all()
            
            for device in available_devices:
                score = 0
                actual_specs = device.specs_dict
                for spec_name, desired_value in desired_specs.items():
                    # Просте порівняння рядків (можна розширити логіку для числових значень)
                    if str(actual_specs.get(spec_name, '')).strip() == str(desired_value).strip():
                        score += 1
                
                recommendations.append({'device': device, 'score': score})
            
            # Сортуємо: спочатку за найвищим балом, потім за назвою
            recommendations.sort(key=lambda x: (-x['score'], x['device'].name))

        # Визначаємо, кому призначити пристрій
        target_info = _parse_assignment_target(task.text) 
        print(target_info)

        
        target_info_str = f"worker:{target_info['id']}" if target_info.get('type') == 'worker' else 'department'
        print(target_info_str)

        return render_template(
            'worker/task_device_request.html', 
            task=task,
            assignment=assignment,
            recommendations=recommendations,
            total_score=len(desired_specs),
            target_info_str=target_info_str
        )
    elif task_type_name == 'Device Return':
        # --- Логіка для завдання на повернення пристрою ---
        device_to_return = task.device # Отримуємо пристрій, пов'язаний із завданням
        if not device_to_return:
             flash("Помилка: Не вдалося знайти пристрій, пов'язаний з цим завданням.", "danger")
             return redirect(url_for('worker_views.worker_dashboard'))

        if request.method == 'POST':
            try:
                # Визначаємо новий статус, обраний працівником
                new_status_str = request.form.get('new_status')
                if new_status_str == 'available':
                    final_device_status = DeviceStatusEnum.AVAILABLE
                elif new_status_str == 'under_repair':
                    final_device_status = DeviceStatusEnum.UNDER_REPAIR
                else:
                    raise ValueError("Некоректний статус обрано.")

                # --- 1. Оновлюємо статус пристрою ---
                device_to_return.status = final_device_status

                # --- 2. Деактивуємо зв'язок DeviceWorker / DeviceDepartment ---
                # Знаходимо запис, який був активним до повернення
                device_worker_link = DeviceWorker.query.filter_by(device_id=device_to_return.id, status=AssignmentStatusEnum.ACTIVE).first()
                device_department_link = DeviceDepartment.query.filter_by(device_id=device_to_return.id, status=AssignmentStatusEnum.ACTIVE).first()
                
                if device_worker_link:
                    device_worker_link.status = AssignmentStatusEnum.RETURNED
                    device_worker_link.returned_at = datetime.utcnow()
                elif device_department_link:
                    device_department_link.status = AssignmentStatusEnum.RETURNED
                    device_department_link.returned_at = datetime.utcnow()
                # (Якщо пристрій був IN_TRANSIT, активного зв'язку може і не бути)

                # --- 3. Закриваємо завдання (Task) ---
                task.status = TaskStatusEnum.CLOSED
                task.finished_at = datetime.utcnow()
                
                # --- 4. Завершуємо призначення (WorkerTask) ---
                assignment.status = WorkerTaskStatusEnum.FINISHED
                assignment.finished_at = datetime.utcnow()
                assignment.comment = f"Пристрій отримано. Новий статус: {final_device_status.value}."


                repair_task_created_msg = ""
                if final_device_status == DeviceStatusEnum.UNDER_REPAIR:
                    repair_task_type = TaskType.query.filter_by(name='Device Repair').first()
                    if repair_task_type:
                        # Створюємо нове завдання на ремонт
                        repair_task_text = (
                            f"Завдання на ремонт пристрою.\n"
                            f"Пристрій: {device_to_return.name} (SN: {device_to_return.serial_number})\n"
                            f"Попередній власник/відділ: {task.customer.full_name if task.customer else 'Невідомо'}\n"
                            f"Виявлено потребу в ремонті працівником: {current_user.full_name}"
                        )
                        new_repair_task = Task(
                            text=repair_task_text,
                            priority=repair_task_type.priority, # Пріоритет з типу завдання
                            customer_id=current_user.id, # Формально, замовник - працівник, що виявив поломку
                            device_id=device_to_return.id # Пов'язуємо з пристроєм
                        )
                        db.session.add(new_repair_task)
                        db.session.flush()

                        # Створюємо Task_TaskType
                        repair_task_type_link = Task_TaskType(
                            task_id=new_repair_task.id,
                            tasktype_id=repair_task_type.tasktype_id,
                            detection_method=TaskDetectionMethodEnum.MANUAL_OVERRIDE, # Створено автоматично за логікою
                            assigned_by_id=current_user.id # Ініційовано працівником
                        )
                        db.session.add(repair_task_type_link)

                        # Призначаємо виконавця для ремонту
                        repair_assignment_result = choose_worker(task=new_repair_task)
                        if repair_assignment_result:
                            new_repair_assignment = WorkerTask(
                                task_id=new_repair_task.id,
                                worker_id=repair_assignment_result['worker_id'],
                                assign_method=repair_assignment_result['method'],
                                assigned_by_id=current_user.id,
                                status=WorkerTaskStatusEnum.ACTIVE
                            )
                            db.session.add(new_repair_assignment)
                            repair_task_created_msg = "Створено нове завдання на ремонт та призначено виконавця."
                        else:
                            repair_task_created_msg = "Створено нове завдання на ремонт, але не вдалося знайти виконавця."
                    else:
                        repair_task_created_msg = "ПОМИЛКА: Тип завдання 'Device Repair' не знайдено, завдання на ремонт не створено!"

                # --- 5. Зберігаємо всі зміни ---
                db.session.commit()
                flash(f"Пристрій '{device_to_return.name}' успішно опрацьовано. Новий статус: {final_device_status.value}.", "success")
                return redirect(url_for('worker_views.worker_dashboard'))

            except Exception as e:
                db.session.rollback()
                flash(f"Сталася помилка при опрацюванні повернення: {e}", "danger")
                traceback.print_exc()
        
        # --- GET-запит: передаємо дані в шаблон ---
        return render_template(
            'worker/task_device_return.html', 
            task=task,
            assignment=assignment,
            device=device_to_return
        )
    elif task_type_name == 'Device Repair':
        device_to_repair = task.device
        if not device_to_repair:
             flash("Помилка: Не вдалося знайти пристрій, пов'язаний з цим завданням на ремонт.", "danger")
             return redirect(url_for('worker_views.worker_dashboard'))

        if request.method == 'POST':
            try:
                # Отримуємо новий статус, встановлений після ремонту
                repair_outcome = request.form.get('repair_outcome')
                comment = request.form.get('comment') # Коментар про виконаний ремонт

                if repair_outcome == 'fixed':
                    final_device_status = DeviceStatusEnum.AVAILABLE
                elif repair_outcome == 'decommissioned':
                    final_device_status = DeviceStatusEnum.DECOMMISSIONED
                else:
                    raise ValueError("Некоректний результат ремонту обрано.")

                # --- 1. Оновлюємо статус пристрою ---
                device_to_repair.status = final_device_status

                device_worker_link = DeviceWorker.query.filter_by(
                    device_id=device_to_repair.id, 
                    status=AssignmentStatusEnum.ACTIVE
                ).first()
                device_department_link = DeviceDepartment.query.filter_by(
                    device_id=device_to_repair.id, 
                    status=AssignmentStatusEnum.ACTIVE
                ).first()
                
                assignment_closed_msg = ""
                if device_worker_link:
                    device_worker_link.status = AssignmentStatusEnum.RETURNED
                    device_worker_link.returned_at = datetime.utcnow()
                    assignment_closed_msg = "Попереднє призначення працівнику закрито."
                    print(f"Деактивовано DeviceWorker ID: {device_worker_link.id}")
                elif device_department_link:
                    device_department_link.status = AssignmentStatusEnum.RETURNED
                    device_department_link.returned_at = datetime.utcnow()
                    assignment_closed_msg = "Попереднє призначення відділу закрито."
                    print(f"Деактивовано DeviceDepartment ID: {device_department_link.id}")

                # --- 2. Закриваємо завдання (Task) ---
                task.status = TaskStatusEnum.CLOSED
                task.finished_at = datetime.utcnow()

                # --- 3. Завершуємо призначення (WorkerTask) ---
                assignment.status = WorkerTaskStatusEnum.FINISHED
                assignment.finished_at = datetime.utcnow()
                assignment.comment = f"Ремонт завершено. Результат: {final_device_status.value}. {comment or ''}".strip()

                # --- 4. Зберігаємо всі зміни ---
                db.session.commit()
                flash(f"Ремонт пристрою '{device_to_repair.name}' завершено. Новий статус: {final_device_status.value}.", "success")
                return redirect(url_for('worker_views.worker_dashboard'))

            except Exception as e:
                db.session.rollback()
                flash(f"Сталася помилка при завершенні ремонту: {e}", "danger")
                traceback.print_exc()

        # --- GET-запит: передаємо дані в шаблон ---
        return render_template(
            'worker/task_device_repair.html',
            task=task,
            assignment=assignment,
            device=device_to_repair
        )
    else:
        if request.method == 'POST':
            try:
                new_status_value = request.form.get('assignment_status')
                comment = request.form.get('comment')

                if not new_status_value:
                    flash("Необхідно обрати новий статус.", "warning")
                    return redirect(url_for('worker_views.view_task', task_id=task_id))

                new_status = WorkerTaskStatusEnum(new_status_value)

                # Оновлюємо статус призначення
                assignment.status = new_status
                assignment.comment = comment # Додаємо коментар працівника

                # Якщо статус 'FINISHED', оновлюємо час завершення
                if new_status == WorkerTaskStatusEnum.FINISHED:
                    assignment.finished_at = datetime.utcnow()
                    assignment.task.status = TaskStatusEnum.CLOSED

                db.session.commit()
                flash("Статус завдання успішно оновлено!", "success")
                return redirect(url_for('worker_views.worker_dashboard')) # Повертаємо на список завдань

            except Exception as e:
                db.session.rollback()
                flash(f"Сталася помилка при оновленні статусу: {e}", "danger")
                traceback.print_exc()

        # --- GET-запит ---
        # Визначаємо, які статуси може встановити працівник
        # (Наприклад, не може сам собі перепризначити)
        available_statuses = [
            WorkerTaskStatusEnum.ACTIVE,
            WorkerTaskStatusEnum.FINISHED
        ]
        
        return render_template(
            'worker/task_generic.html',
            task=task,
            assignment=assignment,
            available_statuses=available_statuses,
            WorkerTaskStatusEnum = WorkerTaskStatusEnum # Передаємо список статусів у шаблон
        )
    
@worker_views.route('/worker_profile', methods=['GET', 'POST'])
@login_required
@role_required('Worker')
def worker_profile():
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
        
        return redirect(url_for('worker_views.worker_profile'))

    # --- GET-запит: просто передаємо поточного користувача в шаблон ---
    # Всю інформацію про відділ/роль ми отримаємо через relationships прямо в HTML
    return render_template("worker/worker_profile.html", user=current_user)

@worker_views.route('/return_task_to_manager/<int:workertask_id>', methods=['POST'])
@login_required
@role_required('Worker')
def return_task_to_manager(workertask_id):
    """
    Обробляє повернення завдання менеджеру для перевірки типу.
    """
    assignment = WorkerTask.query.get_or_404(workertask_id)
    task = assignment.task

    # Перевірки безпеки
    if assignment.worker_id != current_user.worker_id:
        flash("Це не ваше призначення.", "danger")
        return redirect(url_for('worker_views.worker_dashboard'))
    if assignment.status != WorkerTaskStatusEnum.ACTIVE:
        flash("Повернути можна лише активне призначення.", "warning")
        return redirect(url_for('worker_views.view_task', task_id=task.id))

    manager = current_user.manager
    if not manager:
        flash("Неможливо повернути завдання: у вас не вказано менеджера.", "danger")
        return redirect(url_for('worker_views.view_task', task_id=task.id))

    reason = request.form.get('return_reason', '').strip()
    if not reason:
         flash("Будь ласка, вкажіть причину повернення.", "warning")
         return redirect(url_for('worker_views.view_task', task_id=task.id))

    try:
        # 1. Деактивуємо поточне призначення
        assignment.status = WorkerTaskStatusEnum.REASSIGNED # Позначаємо як перепризначене
        assignment.unassigned_at = datetime.utcnow()
        assignment.unassigned_by_id = current_user.id # Ініційовано працівником
        assignment.comment = f"Повернуто менеджеру. Причина: {reason}"

        # 2. Створюємо НОВЕ призначення для менеджера
        manager_assignment = WorkerTask(
            task_id=task.id,
            worker_id=manager.worker_id, # Призначаємо менеджеру
            assigned_by_id=current_user.id, # Ініційовано працівником
            assign_method=WorkerTaskAssignmentMethodEnum.RETURNED_FOR_REVIEW, # Новий метод
            status=WorkerTaskStatusEnum.ACTIVE # Завдання стає активним для менеджера
        )
        db.session.add(manager_assignment)

        # 3. (Опціонально) Змінюємо статус самого завдання на "On Hold"
        task.status = TaskStatusEnum.ON_HOLD

        db.session.commit()
        flash("Завдання повернено менеджеру для перевірки типу.", "success")
        return redirect(url_for('worker_views.worker_dashboard'))

    except Exception as e:
        db.session.rollback()
        flash(f"Сталася помилка при поверненні завдання: {e}", "danger")
        traceback.print_exc()
        return redirect(url_for('worker_views.view_task', task_id=task.id))


@worker_views.route('/reject_task/<int:workertask_id>', methods=['POST'])
@login_required
@role_required('Worker')
def reject_task(workertask_id):
    """
    Обробляє відмову від завдання з автоматичним перепризначенням іншому виконавцю.
    """
    assignment = WorkerTask.query.get_or_404(workertask_id)
    task = assignment.task


    # Перевірки безпеки
    # if assignment.worker_id != current_user.worker_id:
    #     flash("Це не ваше призначення.", "danger")
    #     return redirect(url_for('worker_views.worker_dashboard'))
    if assignment.status != WorkerTaskStatusEnum.ACTIVE:
        flash("Відмовитись можна лише від активного призначення.", "warning")
        return redirect(url_for('worker_views.view_task', task_id=task.id))

    reject_reason = request.form.get('reject_reason', '').strip()
    if not reject_reason:
         flash("Будь ласка, вкажіть причину відмови.", "warning")
         return redirect(url_for('worker_views.view_task', task_id=task.id))

    try:
        # 1. Деактивуємо поточне призначення
        assignment.status = WorkerTaskStatusEnum.REASSIGNED
        assignment.unassigned_at = datetime.utcnow()
        assignment.unassigned_by_id = current_user.id # Ініційовано працівником
        assignment.comment = f"Відмова від виконання. Причина: {reject_reason}"


        assignment_result = choose_worker(task=task, exclude_worker_id=current_user.id)

        if assignment_result:
             # 3. Створюємо нове призначення
            new_assignment = WorkerTask(
                task_id=task.id,
                worker_id=assignment_result['worker_id'],
                assign_method=assignment_result['method'],
                assigned_by_id=current_user.id, # Ініційовано системою (через відмову)
                status=WorkerTaskStatusEnum.ACTIVE
            )
            db.session.add(new_assignment)
            flash_msg = "Ви відмовились від завдання. Його передано іншому виконавцю."
            flash_category = "success"
        else:
            flash_msg = "Ви відмовились від завдання, але не вдалося знайти заміну. Зверніться до менеджера."
            flash_category = "warning"

        db.session.commit()
        flash(flash_msg, flash_category)
        return redirect(url_for('worker_views.worker_dashboard'))

    except Exception as e:
        db.session.rollback()
        flash(f"Сталася помилка при відмові від завдання: {e}", "danger")
        traceback.print_exc()
        return redirect(url_for('worker_views.view_task', task_id=task.id))
    
def _parse_desired_specs(task_text: str) -> dict:
    """Парсить текст завдання і повертає словник бажаних характеристик."""
    specs = {}
    specs_block_marker = "--- Бажані характеристики ---"
    if specs_block_marker in task_text:
        # Беремо частину тексту після маркера
        specs_part = task_text.split(specs_block_marker, 1)[1]
        for line in specs_part.strip().split('\n'):
            if ':' in line:
                # Розділяємо рядок "- Назва: Значення" на дві частини
                parts = line.split(':', 1)
                # Очищуємо назву атрибута від дефісів та пробілів
                key = parts[0].strip().lstrip('-').strip()
                value = parts[1].strip()
                specs[key] = value
    return specs

def _parse_assignment_target(task_text: str) -> dict:
    """
    Визначає ціль призначення пристрою (конкретний працівник чи відділ) з тексту завдання.
    """
    # Шукаємо патерн "працівника ID:число"
    worker_match = re.search(r"працівника ID:(\d+)", task_text)
    if worker_match:
        # Якщо знайдено, витягуємо ID (це група 1 у регулярному виразі)
        worker_id = int(worker_match.group(1))
        return {'type': 'worker', 'id': worker_id}
        
    # Якщо ID працівника не знайдено, перевіряємо наявність фрази "для відділу"
    elif "для відділу" in task_text:
        return {'type': 'department'}
        
    # Якщо не знайдено ані ID, ані згадки про відділ (малоймовірно)
    else:
        print(f"ПОПЕРЕДЖЕННЯ: Не вдалося визначити ціль призначення з тексту: {task_text}")
        return {} # Повертаємо порожній словник