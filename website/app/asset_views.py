from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
from sqlalchemy.exc import IntegrityError
import traceback
from sqlalchemy.orm import joinedload

from . import db
from .models import Device, DeviceType, DeviceAttribute, TaskType, Department, Role, DeviceAttributeValue, WorkerTaskType, Task_TaskType, DeviceTypeAttribute, DeviceStatusEnum
from .decorators import role_required

asset_views = Blueprint('asset_views', __name__)

# ====================== ASSET MANAGEMENT =====================================

@asset_views.route('/devices')
@login_required
@role_required('Admin')
def view_devices():
    """Сторінка для перегляду всього парку техніки."""
    all_devices = Device.query.order_by(Device.id).all()
    return render_template('assets/device/devices.html', devices=all_devices, DeviceStatusEnum=DeviceStatusEnum)

@asset_views.route('/decommission_device/<int:device_id>', methods=['POST'])
@login_required
@role_required('Admin')
def decommission_device(device_id):
    """
    Обробник для зміни статусу пристрою на 'decommissioned' (списаний).
    """
    device_to_decommission = Device.query.get_or_404(device_id)

    # --- КЛЮЧОВА ПЕРЕВІРКА ---
    # Перевіряємо, чи пристрій зараз використовується або вже списаний.
    if device_to_decommission.status == DeviceStatusEnum.IN_USE:
        flash(f"Неможливо списати пристрій '{device_to_decommission.name}', оскільки він зараз використовується працівником.", 'danger')
        return redirect(url_for('asset_views.view_devices'))

    if device_to_decommission.status == DeviceStatusEnum.DECOMMISSIONED:
        flash(f"Пристрій '{device_to_decommission.name}' вже має статус 'списаний'.", 'info')
        return redirect(url_for('asset_views.view_devices'))

    # --- ЗМІНА СТАТУСУ ---
    try:
        device_to_decommission.status = DeviceStatusEnum.DECOMMISSIONED
        
        db.session.commit()
        flash(f"Пристрій '{device_to_decommission.name}' успішно списано.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Помилка під час списання пристрою: {e}", "danger")

    return redirect(url_for('asset_views.view_devices'))

@asset_views.route('/add_device', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def add_device():
    """Сторінка для додавання нового пристрою в систему."""
    if request.method == 'POST':
        form_data = request.form
        
        # --- Валідація основних полів ---
        serial_number = form_data.get('serial_number')
        if Device.query.filter_by(serial_number=serial_number).first():
            flash(f"Пристрій з серійним номером '{serial_number}' вже існує.", 'danger')
            # Повертаємо на форму, щоб користувач міг виправити помилку
            device_types = DeviceType.query.order_by(DeviceType.name).all()
            return render_template('assets/add_device.html', device_types=device_types)

        try:
            # --- Створення основного об'єкта Device ---
            new_device = Device(
                name=form_data.get('name'),
                serial_number=serial_number,
                device_type_id=int(form_data.get('device_type_id')),
                status=DeviceStatusEnum.AVAILABLE # Нові пристрої завжди доступні
            )
            db.session.add(new_device)
            # Виконуємо flush, щоб отримати new_device.id для збереження атрибутів
            db.session.flush()

            # --- Збереження динамічних атрибутів ---
            # request.form містить всі поля, включаючи 'attr_<id>'
            for key, value in form_data.items():
                if key.startswith('attr_'):
                    # Витягуємо ID атрибута з назви поля (напр., з 'attr_5')
                    attribute_id = int(key.split('_')[1])
                    if value: # Зберігаємо тільки якщо поле не порожнє
                        attr_value = DeviceAttributeValue(
                            device_id=new_device.id,
                            attribute_id=attribute_id,
                            value=value.strip()
                        )
                        db.session.add(attr_value)

            db.session.commit()
            flash(f"Пристрій '{new_device.name}' успішно додано!", 'success')
            return redirect(url_for('asset_views.view_devices'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Непередбачувана помилка при додаванні пристрою: {e}", "danger")

    # --- GET-запит: готуємо дані для форми ---
    device_types = DeviceType.query.order_by(DeviceType.name).all()
    return render_template('assets/device/add_device.html', device_types=device_types)


@asset_views.route('/edit_device/<int:device_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_device(device_id):
    """Сторінка для редагування існуючого пристрою."""
    device_to_edit = Device.query.get_or_404(device_id)

    if request.method == 'POST':
        form_data = request.form
        
        # --- Валідація унікальності серійного номера ---
        new_serial = form_data.get('serial_number')
        existing_device = Device.query.filter(Device.serial_number == new_serial, Device.id != device_id).first()
        if existing_device:
            flash(f"Пристрій з серійним номером '{new_serial}' вже існує.", 'danger')
            return redirect(url_for('asset_views.edit_device', device_id=device_id))

        try:
            # --- Оновлення основних полів ---
            device_to_edit.name = form_data.get('name')
            device_to_edit.serial_number = new_serial
            device_to_edit.inventory_number = form_data.get('inventory_number')
            device_to_edit.device_type_id = int(form_data.get('device_type_id'))

            # --- Оновлення/створення/видалення атрибутів ---
            # 1. Збираємо всі атрибути, що прийшли з форми
            form_attributes = {int(k.split('_')[1]): v.strip() for k, v in form_data.items() if k.startswith('attr_')}

            # 2. Отримуємо всі існуючі атрибути цього пристрою
            existing_values = DeviceAttributeValue.query.filter_by(device_id=device_id).all()
            existing_values_map = {val.attribute_id: val for val in existing_values}

            # 3. Проходимо по атрибутам з форми і оновлюємо/створюємо
            for attr_id, new_value in form_attributes.items():
                existing_val_obj = existing_values_map.get(attr_id)
                
                if existing_val_obj: # Якщо значення вже існує
                    if new_value:
                        existing_val_obj.value = new_value # Оновлюємо
                    else:
                        db.session.delete(existing_val_obj) # Видаляємо, якщо поле стало порожнім
                elif new_value: # Якщо значення не існувало, але з'явилося
                    new_attr_value = DeviceAttributeValue(
                        device_id=device_id, attribute_id=attr_id, value=new_value
                    )
                    db.session.add(new_attr_value)
            
            db.session.commit()
            flash(f"Пристрій '{device_to_edit.name}' успішно оновлено!", 'success')
            return redirect(url_for('asset_views.view_devices'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Помилка при оновленні пристрою: {e}", "danger")
            return redirect(url_for('asset_views.edit_device', device_id=device_id))

    # --- GET-запит: готуємо дані для відображення ---
    all_device_types = DeviceType.query.order_by(DeviceType.name).all()
    # Створюємо словник {attribute_id: value} для передачі в JavaScript
    current_attribute_values = {val.attribute_id: val.value for val in device_to_edit.attributes}
    
    return render_template(
        'assets/device/edit_device.html', 
        device=device_to_edit,
        all_device_types=all_device_types,
        current_attribute_values=current_attribute_values
    )
# ====================== SYSTEM CATALOGS MANAGEMENT ===========================

@asset_views.route('/device_types', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def manage_device_types():
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_priority_str = request.form.get('priority')

        if new_name:
            new_name = new_name.strip()
            print(new_name)

        if not new_name or len(new_name) < 2:
            flash('Назва типу пристрою має містити щонайменше 2 символи.', 'danger')
        elif not new_priority_str:
            print('Пріоритет є обов\'язковим полем.')
        else:
            # --- B-) НОВА, НАДІЙНА ЛОГІКА ---
            # 1. Спочатку шукаємо, чи такий запис вже існує
            existing_type = DeviceType.query.filter_by(name=new_name).first()
            print(existing_type)
            
            if existing_type:
                # 2. Якщо існує, видаємо помилку
                print(f"Тип пристрою з назвою '{new_name}' вже існує.")
            else:
                # 3. Якщо не існує, ТІЛЬКИ ТОДІ створюємо і зберігаємо
                try:
                    new_priority = int(new_priority_str)
                    print
                    new_device_type = DeviceType(name=new_name, priority=new_priority)
                    db.session.add(new_device_type)
                    db.session.commit()
                    flash(f"Тип пристрою '{new_name}' успішно створено!", 'success')
                except Exception as e:
                    db.session.rollback()
                    traceback.print_exc()
                    flash(f"Непередбачувана помилка при збереженні: {e}", "danger")
        
        return redirect(url_for('asset_views.manage_device_types'))

    all_device_types = (
        DeviceType.query
        .options(
            joinedload(DeviceType.relevant_attributes)  # Завантажуємо зв'язки DeviceTypeAttribute
            .joinedload(DeviceTypeAttribute.attribute) # З кожного зв'язку завантажуємо сам атрибут
        )
        .order_by(DeviceType.name)
        .all()
    )
    
    return render_template('assets/devicetype/device_types.html', device_types=all_device_types)


@asset_views.route('/edit_device_type/<int:type_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_device_type(type_id):
    """Сторінка для редагування типу пристрою та його релевантних атрибутів."""
    device_type_to_edit = DeviceType.query.get_or_404(type_id)

    if request.method == 'POST':
        # --- Оновлення базових полів (назва, пріоритет) ---
        device_type_to_edit.name = request.form.get('name').strip()
        device_type_to_edit.priority = int(request.form.get('priority'))

        # --- B-) ЛОГІКА ОНОВЛЕННЯ ЗВ'ЯЗКІВ З АТРИБУТАМИ ---
        try:
            # 1. Отримуємо ID атрибутів, які були вибрані у формі
            # request.form.getlist('attribute_ids') поверне список значень усіх вибраних чекбоксів
            selected_attribute_ids = set(request.form.getlist('attribute_ids', type=int))

            # 2. Отримуємо ID атрибутів, які ВЖЕ прив'язані до цього типу
            current_attribute_ids = {link.attribute_id for link in device_type_to_edit.relevant_attributes}

            # 3. Знаходимо, які зв'язки потрібно видалити
            ids_to_delete = current_attribute_ids - selected_attribute_ids
            if ids_to_delete:
                DeviceTypeAttribute.query.filter(
                    DeviceTypeAttribute.devicetype_id == type_id,
                    DeviceTypeAttribute.attribute_id.in_(ids_to_delete)
                ).delete(synchronize_session=False)

            # 4. Знаходимо, які зв'язки потрібно додати
            ids_to_add = selected_attribute_ids - current_attribute_ids
            for attr_id in ids_to_add:
                new_link = DeviceTypeAttribute(devicetype_id=type_id, attribute_id=attr_id)
                db.session.add(new_link)

            db.session.commit()
            flash(f"Тип пристрою '{device_type_to_edit.name}' та його атрибути успішно оновлено!", 'success')
            return redirect(url_for('asset_views.manage_device_types'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Помилка при оновленні зв'язків з атрибутами: {e}", "danger")
            return redirect(url_for('asset_views.edit_device_type', type_id=type_id))

    # --- GET-запит: готуємо дані для відображення форми ---
    all_attributes = DeviceAttribute.query.order_by(DeviceAttribute.name).all()
    # Створюємо set з ID вже прив'язаних атрибутів для швидкої перевірки в шаблоні
    linked_attribute_ids = {link.attribute_id for link in device_type_to_edit.relevant_attributes}
    
    return render_template(
        'assets/devicetype/edit_device_type.html', 
        device_type=device_type_to_edit,
        all_attributes=all_attributes,
        linked_attribute_ids=linked_attribute_ids
    )

@asset_views.route('/delete_device_type/<int:type_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def delete_device_type(type_id):
    """Обробник для видалення атрибуту пристрою."""
    type_to_delete = DeviceType.query.get_or_404(type_id)
    print(type_to_delete)

    try:
        db.session.delete(type_to_delete)
        db.session.commit()
        flash(f"Тип '{type_to_delete.name}' успішно видалено.", 'success')
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        flash(f"Помилка під час видалення типу: {e}", "danger")

    return redirect(url_for('asset_views.manage_device_types'))



@asset_views.route('/device_attributes', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def manage_device_attributes():
    """Сторінка для керування атрибутами (характеристиками) пристроїв."""
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_data_type = request.form.get('data_type')

        # Очищуємо пробіли на початку/кінці назви
        if new_name:
            new_name = new_name.strip()

        # --- Валідація ---
        if not new_name or len(new_name) < 2:
            flash('Назва атрибуту має містити щонайменше 2 символи.', 'danger')
        elif not new_data_type:
            flash('Необхідно обрати тип даних для атрибуту.', 'danger')
        else:
            # Перевірка, чи такий атрибут вже існує
            existing_attribute = DeviceAttribute.query.filter_by(name=new_name).first()
            if existing_attribute:
                flash(f"Атрибут з назвою '{new_name}' вже існує.", 'danger')
            else:
                try:
                    new_attribute = DeviceAttribute(name=new_name, data_type=new_data_type)
                    db.session.add(new_attribute)
                    db.session.commit()
                    flash(f"Атрибут '{new_name}' успішно створено!", 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f"Непередбачувана помилка при збереженні: {e}", "danger")
        
        return redirect(url_for('asset_views.manage_device_attributes'))

    # --- GET-запит ---
    all_attributes = DeviceAttribute.query.order_by(DeviceAttribute.id).all()
    # Список можливих типів даних для випадаючого списку у формі
    data_type_options = ['string', 'integer', 'decimal', 'boolean']
    
    return render_template(
        'assets/deviceattribute/device_attributes.html', 
        attributes=all_attributes,
        data_type_options=data_type_options
    )

@asset_views.route('/delete_device_attribute/<int:attribute_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_device_attribute(attribute_id):
    """Обробник для видалення атрибуту пристрою."""
    attribute_to_delete = DeviceAttribute.query.get_or_404(attribute_id)

    # B-) --- КЛЮЧОВА ПЕРЕВІРКА ---
    # Перевіряємо, чи використовується цей атрибут хоча б в одному пристрої.
    usage_check = DeviceAttributeValue.query.filter_by(attribute_id=attribute_id).first()

    if usage_check:
        # Якщо атрибут використовується, видалення заборонено
        flash(f"Неможливо видалити атрибут '{attribute_to_delete.name}', оскільки він використовується в існуючих пристроях.", 'danger')
    else:
        # Якщо атрибут не використовується, видаляємо його
        try:
            db.session.delete(attribute_to_delete)
            db.session.commit()
            flash(f"Атрибут '{attribute_to_delete.name}' успішно видалено.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Помилка під час видалення атрибуту: {e}", "danger")

    return redirect(url_for('asset_views.manage_device_attributes'))

@asset_views.route('/edit_device_attribute/<int:attribute_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_device_attribute(attribute_id):
    """Сторінка для редагування існуючого атрибуту пристрою."""
    attribute_to_edit = DeviceAttribute.query.get_or_404(attribute_id)
    data_type_options = ['string', 'integer', 'decimal', 'boolean']

    if request.method == 'POST':
        # B-) --- ЛОГІКА ОНОВЛЕННЯ ---
        new_name = request.form.get('name')
        new_data_type = request.form.get('data_type')

        if new_name:
            new_name = new_name.strip()

        # --- Валідація ---
        error = False
        if not new_name or len(new_name) < 2:
            flash('Назва атрибуту має містити щонайменше 2 символи.', 'danger')
            error = True
        
        # Перевіряємо унікальність, але ігноруємо поточний запис, який редагуємо
        existing_attribute = DeviceAttribute.query.filter(
            DeviceAttribute.name == new_name, 
            DeviceAttribute.id != attribute_id
        ).first()

        if existing_attribute:
            flash(f"Атрибут з назвою '{new_name}' вже існує.", 'danger')
            error = True
            
        if not new_data_type or new_data_type not in data_type_options:
            flash('Необхідно обрати коректний тип даних.', 'danger')
            error = True

        if error:
            # Якщо є помилка, просто перезавантажуємо сторінку, не зберігаючи зміни
            # Форма залишиться заповненою тими даними, які ввів користувач
            return render_template(
                'assets/deviceattribute/edit_device_attribute.html', 
                attribute={'name': new_name, 'data_type': new_data_type, 'id': attribute_id}, # Передаємо введені дані
                data_type_options=data_type_options
            )

        # --- Збереження змін ---
        try:
            attribute_to_edit.name = new_name
            attribute_to_edit.data_type = new_data_type
            db.session.commit()
            flash(f"Атрибут '{new_name}' успішно оновлено!", 'success')
            return redirect(url_for('asset_views.manage_device_attributes'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Непередбачувана помилка при оновленні: {e}", "danger")

    # --- GET-запит: показуємо форму з поточними даними ---
    return render_template(
        'assets/deviceattribute/edit_device_attributes.html', 
        attribute=attribute_to_edit,
        data_type_options=data_type_options
    )




@asset_views.route('/task_types', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def manage_task_types():
    """Сторінка для керування типами завдань."""
    if request.method == 'POST':
        # --- ЛОГІКА СТВОРЕННЯ НОВОГО ТИПУ ЗАВДАННЯ ---
        new_name = request.form.get('name')
        new_priority_str = request.form.get('priority')

        if new_name:
            new_name = new_name.strip()

        # --- Валідація ---
        if not new_name or len(new_name) < 3:
            flash('Назва типу завдання має містити щонайменше 3 символи.', 'danger')
        elif not new_priority_str:
            flash('Пріоритет є обов\'язковим полем.', 'danger')
        else:
            # Перевіряємо, чи такий тип завдання вже існує
            existing_task_type = TaskType.query.filter_by(name=new_name).first()
            if existing_task_type:
                flash(f"Тип завдання з назвою '{new_name}' вже існує.", 'danger')
            else:
                try:
                    new_priority = int(new_priority_str)
                    new_task_type = TaskType(name=new_name, priority=new_priority)
                    db.session.add(new_task_type)
                    db.session.commit()
                    flash(f"Тип завдання '{new_name}' успішно створено!", 'success')
                except ValueError:
                    flash('Пріоритет має бути числом.', 'danger')
                except Exception as e:
                    db.session.rollback()
                    flash(f"Непередбачувана помилка: {e}", "danger")
        
        return redirect(url_for('asset_views.manage_task_types'))

    # --- GET-запит: отримуємо всі типи для відображення ---
    all_task_types = TaskType.query.order_by(TaskType.tasktype_id).all()
    return render_template('assets/tasktypes/task_types.html', task_types=all_task_types)


@asset_views.route('/delete_task_type/<int:tasktype_id>', methods=['POST'])
@login_required
@role_required('Admin')
def delete_task_type(tasktype_id):
    """Обробник для видалення типу завдання."""
    tasktype_to_delete = TaskType.query.get_or_404(tasktype_id)

    # --- КЛЮЧОВА ПЕРЕВІРКА ---
    # Перевіряємо, чи використовується цей тип завдання в компетенціях працівників або в самих завданнях.
    usage_check_worker = WorkerTaskType.query.filter_by(tasktype_id=tasktype_id).first()
    usage_check_task = Task_TaskType.query.filter_by(tasktype_id=tasktype_id).first()

    if usage_check_worker or usage_check_task:
        # Якщо тип використовується, видалення заборонено
        flash(f"Неможливо видалити тип завдання '{tasktype_to_delete.name}', оскільки він вже використовується в системі (призначений працівникам або завданням).", 'danger')
    else:
        # Якщо тип не використовується, видаляємо його
        try:
            db.session.delete(tasktype_to_delete)
            db.session.commit()
            # B-) Виправлене повідомлення
            flash(f"Тип завдання '{tasktype_to_delete.name}' успішно видалено.", 'success')
        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            # B-) Виправлене повідомлення
            flash(f"Помилка під час видалення типу завдання: {e}", "danger")

    return redirect(url_for('asset_views.manage_task_types'))

@asset_views.route('/edit_task_type/<int:tasktype_id>', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def edit_task_type(tasktype_id):
    """Сторінка для редагування існуючого типу завдання."""
    task_type_to_edit = TaskType.query.get_or_404(tasktype_id)

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_priority_str = request.form.get('priority')

        if new_name:
            new_name = new_name.strip()

        # --- Валідація ---
        error = False
        if not new_name or len(new_name) < 3:
            flash('Назва типу завдання має містити щонайменше 3 символи.', 'danger')
            error = True
        
        # Перевіряємо унікальність, ігноруючи поточний запис
        existing_type = TaskType.query.filter(
            TaskType.name == new_name, 
            TaskType.tasktype_id != tasktype_id
        ).first()
        if existing_type:
            flash(f"Тип завдання з назвою '{new_name}' вже існує.", 'danger')
            error = True
            
        if not new_priority_str:
            flash('Пріоритет є обов\'язковим полем.', 'danger')
            error = True

        if error:
            # Якщо є помилка, повертаємося на сторінку редагування
            return redirect(url_for('asset_views.edit_task_type', tasktype_id=tasktype_id))

        # --- Збереження змін ---
        try:
            task_type_to_edit.name = new_name
            task_type_to_edit.priority = int(new_priority_str)
            db.session.commit()
            flash(f"Тип завдання '{new_name}' успішно оновлено!", 'success')
            return redirect(url_for('asset_views.manage_task_types'))

        except Exception as e:
            db.session.rollback()
            flash(f"Непередбачувана помилка при оновленні: {e}", "danger")
            return redirect(url_for('asset_views.edit_task_type', tasktype_id=tasktype_id))

    # --- GET-запит: показуємо форму з поточними даними ---
    return render_template('assets/tasktypes/edit_task_type.html', task_type=task_type_to_edit)

# ====================== ANALYTICS & REPORTING ================================

@asset_views.route('/analytics')
@login_required
@role_required('Admin')
def analytics_dashboard():
    """Сторінка з аналітикою та звітами."""
    # TODO: Додати логіку для збору статистики
    return render_template('assets/analytics.html')


##################################################
@asset_views.route('/api/attributes/<int:device_type_id>')
@login_required
@role_required('Admin', 'Manager', 'User')
def get_attributes_for_device_type(device_type_id):
    """
    API-ендпоінт, що повертає список атрибутів для конкретного типу пристрою.
    """
    # Знаходимо всі зв'язки між типом пристрою та атрибутами
    type_attributes = DeviceTypeAttribute.query.filter_by(devicetype_id=device_type_id).all()
    
    attributes_list = []
    for type_attr in type_attributes:
        # Для кожного зв'язку отримуємо дані самого атрибута
        attribute = type_attr.attribute
        attributes_list.append({
            'id': attribute.id,
            'name': attribute.name,
            'data_type': attribute.data_type
        })
        
    return jsonify(attributes_list)