from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from .decorators import role_required 
from .models import Worker, Department, Role, WorkerDepartment, WorkerTaskType, TaskType, WorkerRole
from . import db
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect, asc, desc
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased
from datetime import datetime

manager_views = Blueprint('manager_views', __name__, template_folder='manager')

@manager_views.route('/dashboard', methods=['GET', 'POST'])
@login_required
@role_required('Manager') #Manager
def manager_dashboard():

    # tasks = Task.query \
    #         .join(Worker, Task.created_by == Worker.id) \
    #         .outerjoin(TaskType) \
    #         .order_by(desc(Task.id)) \
    #         .all()
    # tasktypes = TaskType.query.all()

    # status_column = inspect(Task).columns.status
    # statuses = status_column.type.enums
    return render_template("manager/manager_dashboard.html")

# @manager_views.route('/edit_request/<int:task_id>', methods=['GET', 'POST'])
# @login_required
# @role_required([2]) # Manager
# def edit_request(task_id):
#     task = Task.query.get_or_404(task_id)
#     workers = Worker.query \
#         .join(Role, Worker.role_id == Role.id) \
#         .join(TaskTypeWorker, TaskTypeWorker.worker_id == Worker.id)\
#         .filter(Worker.department_id == current_user.department_id) \
#         .filter(Role.name == 'Worker')\
#         .filter(Worker.id != task.created_by)\
#         .filter(Worker.status == 'active') \
#         .filter(TaskTypeWorker.tasktype_id == task.task_type.id) \
#         .all()
    
#     tasktypes = TaskType.query.all()
#     if request.method == 'POST':
#         new_worker_id = request.form['worker']
#         new_type = request.form['taskType']

#         if new_worker_id != task.worker_id:
#             task.worker_id = new_worker_id
#         if new_type != task.type_id:
#             task.type_id = new_type

#         db.session.commit()
#         flash('Task edited successfully.', 'success') 
#         return redirect(url_for('manager_views.manager_dashboard'))

#     return render_template("manager/edit_request.html", task=task, workers=workers, tasktypes=tasktypes)


@manager_views.route('/profile', methods=['GET', 'POST'])
@login_required
@role_required('Manager')
def manager_profile():
    if request.method == 'POST':
        new_phone = request.form.get('phone')
        new_email = request.form.get('email')
        new_password = request.form.get('password')
        confirm_password = request.form.get('password2')

        # --- EMAIL ---
        if new_email:
            if len(new_email) < 6:
                flash('Email must be at least 6 characters.', 'error')
            elif new_email != current_user.email:
                if Worker.query.filter_by(email=new_email).first():
                    flash('Цей email вже використовується.', 'error')
                else:
                    current_user.email = new_email

        # --- PHONE ---
        if new_phone:
            if not new_phone.isdigit():
                flash('Phone number should contain only numbers.', 'error')
            elif new_phone != current_user.phone:
                current_user.phone = new_phone

        # --- PASSWORD ---
        if new_password or confirm_password:
            if new_password != confirm_password:
                flash('Паролі не співпадають.', 'error')
            elif len(new_password) < 7:
                flash('Password must be at least 7 characters.', 'error')
            else:
                current_user.password_hash = generate_password_hash(
                    new_password, method='pbkdf2:sha256'
                )

        db.session.commit()
        flash('Дані успішно оновлені ✅', 'success')
        return redirect(url_for('manager_views.manager_profile'))

    # ---- JOIN для поточного користувача ----
    try:
        WD = aliased(WorkerDepartment)

        profile_data = (
            db.session.query(
                Worker.worker_id,
                Worker.surname,
                Worker.name,
                Worker.username,
                Worker.email,
                Worker.phone,
                Worker.date_of_birth,
                Department.name.label("department_name"),
                WD.title.label("title")
            )
            .join(WD, Worker.worker_id == WD.worker_id)
            .join(Department, WD.department_id == Department.department_id)
            .filter(Worker.worker_id == current_user.worker_id)
            .all()
        )

    except SQLAlchemyError as e:
        print(f"SQLAlchemy Error: {e}")
        return "Database connection or query error", 500

    return render_template("manager/manager_profile.html", user=current_user, profile_data=profile_data)




# @manager_views.route('/user_profile/<user_id>', methods=['GET', 'POST'])
# @login_required
# @role_required([2]) 
# def view_profile(user_id):
#     user = Worker.query.get_or_404(user_id)
   
#     tasktypes = TaskType.query.all()
#     worker_tasktypes = TaskTypeWorker.query.filter(TaskTypeWorker.worker_id == user_id).all()
#     worker_tasktype_ids = [tasktype.tasktype_id for tasktype in worker_tasktypes]

#     return render_template("manager/view_profile.html", user=user, tasktypes=tasktypes, worker_tasktype_ids=worker_tasktype_ids, worker_tasktypes=worker_tasktypes)


# @manager_views.route('/manage_devices', methods=['GET', 'POST'])
# @login_required
# @role_required([2]) #Manager
# def manage_devices():
#     device_workers = DeviceWorker.query \
#         .join(Device, DeviceWorker.device_id == Device.device_id) \
#         .join(DeviceBrand, Device.device_brand_id == DeviceBrand.id) \
#         .join(DeviceType, Device.device_type_id == DeviceType.id) \
#         .order_by(asc(DeviceWorker.id)) \
#         .all()
    

#     devicetypes = DeviceType.query.all()
#     devicebrands = DeviceBrand.query.all()

#     status_column = inspect(DeviceWorker).columns.status
#     statuses = status_column.type.enums
#     return render_template("manager/manage_devices.html", user=current_user, device_workers=device_workers, statuses=statuses, devicetypes=devicetypes, devicebrands=devicebrands )


# @manager_views.route('/add_new_device', methods=['GET', 'POST'])
# @login_required
# @role_required([2]) #Manager
# def add_new_device():

#     devices = DeviceWorker.query.join(Device).join(DeviceBrand).join(DeviceType).all()
#     device_types = DeviceType.query.all()
#     device_brands = DeviceBrand.query.all()
#     if request.method == 'POST':
#         device_name = request.form['device_name']
#         device_type = request.form['device_type']
#         device_brand = request.form['device_brand']
#         serial_number = request.form['serial_number']

#         try: 
#             new_device = Device(device_name = device_name, device_type_id = device_type, device_brand_id = device_brand, serial_number=serial_number)
#             db.session.add(new_device)
#             db.session.commit()
#             flash('Device was successfully added', 'success')
#             return redirect(url_for('manager_views.view_devices_list', user_id=current_user.id))
#         except IntegrityError as e:
#             flash('Serial number already exists. Please choose a different serial number.', 'error')
#             return redirect(url_for('manager_views.add_new_device'))


#     return render_template("manager/add_new_device.html", user=current_user, devices=devices, device_types=device_types, device_brands=device_brands)

# @manager_views.route('/view_devices_list', methods=['GET', 'POST'])
# @login_required
# @role_required([2]) #Manager
# def view_devices_list():
#     device_list = Device.query \
#         .join(DeviceBrand, Device.device_brand_id == DeviceBrand.id) \
#         .join(DeviceType, Device.device_type_id == DeviceType.id) \
#         .order_by(asc(Device.device_id)) \
#         .all()
    
#     devicetypes = DeviceType.query.all()
#     devicebrands = DeviceBrand.query.all()
#     status_column = inspect(Device).columns.status
#     statuses = status_column.type.enums

#     return render_template("manager/view_devices_list.html", device_list=device_list, devicetypes=devicetypes, devicebrands=devicebrands, statuses=statuses)


# @manager_views.route('/make_not_available/<int:device_id>', methods=['POST'])
# @login_required
# @role_required([2]) 
# def make_not_available(device_id):
#     device = Device.query.get_or_404(device_id)

#     device.status = '6'
#     db.session.commit()
#     flash('Device #{} is now not available.'.format(str(device_id)), 'success')
#     return redirect(url_for('manager_views.view_devices_list'))


@manager_views.route('/manage_workers', methods=['GET', 'POST'])
@login_required
@role_required('Manager') #Manager
def manage_workers():
    WD = aliased(WorkerDepartment)
    WR = aliased(WorkerRole)

    users = (
        db.session.query(
            Worker,
            Department.name.label("department_name"),
            Role.name.label("role_name"),
            WD.status.label("work_status"),
            WD.title.label("title")
        )
        .join(WD, Worker.worker_id == WD.worker_id)
        .join(Department, WD.department_id == Department.department_id)
        .join(WR, Worker.worker_id == WR.worker_id)
        .join(Role, WR.role_id == Role.role_id)
        .filter(Worker.manager_id == current_user.worker_id)
        .all()
    )
    roles = Role.query.all()
    departments = Department.query.all()
    responsibilities = WorkerTaskType.query.join(TaskType).filter(WorkerTaskType.status == "active").all()

    tasktypes = TaskType.query.all()
    return render_template("manager/manager_workers.html", users = users, roles=roles, departments=departments, responsibilities = responsibilities, tasktypes=tasktypes)


@manager_views.route('/edit_worker_profile/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('Manager') 
def edit_worker_profile(user_id):
    
    WD = aliased(WorkerDepartment)
    WT = aliased(WorkerTaskType)
    

    user = (
        db.session.query(
            Worker.worker_id,
            Worker.surname,
            Worker.name,
            Worker.username,
            Worker.email,
            Worker.phone,
            Worker.date_of_birth,
            Worker.manager_id,
            Worker.worker_status,
            Worker.unavailable_until,
            # Department
            Department.department_id,
            Department.name.label("department_name"),
            WD.start_date.label("department_start_date"),
            WD.end_date.label("department_end_date"),
            WD.status.label("department_status"),
            WD.title.label("department_title"),

            # TaskType
            TaskType.tasktype_id,
            TaskType.name.label("tasktype_name"),
            WT.start_date.label("tasktype_start_date"),
            WT.end_date.label("tasktype_end_date"),
            WT.status.label("tasktype_status"),
        )
        .outerjoin(WD, Worker.worker_id == WD.worker_id)
        .outerjoin(Department, WD.department_id == Department.department_id)
        .outerjoin(WT, Worker.worker_id == WT.worker_id)
        .outerjoin(TaskType, WT.tasktype_id == TaskType.tasktype_id)
        .filter(Worker.worker_id == user_id)
        .first()
    )
   
    tasktypes = TaskType.query.all()
    worker_tasktypes = WorkerTaskType.query.filter_by(worker_id=user_id, status="active").all()
    worker_tasktype_ids = [tasktype.tasktype_id for tasktype in worker_tasktypes]

    
    if request.method == 'POST':
        user = Worker.query.get_or_404(user_id)  # ⚡️ ORM об'єкт
        
        selected_tasktypes = set()
        updated = False
        
        for tasktype_id in request.form.getlist('tasktypes[]'):
            if tasktype_id.strip():
                selected_tasktypes.add(int(tasktype_id))

        # Додати нові TaskTypes → active
        for tasktype_id in selected_tasktypes - set(worker_tasktype_ids):
            new_tasktype_worker = WorkerTaskType(
                worker_id=user_id,
                tasktype_id=tasktype_id,
                status="active",
                start_date=datetime.utcnow(),
                end_date=None
            )
            db.session.add(new_tasktype_worker)
            updated = True  # ⚡️ тепер commit піде

        # Завершити ті, що зняли → finished
        for tasktype_id in set(worker_tasktype_ids) - selected_tasktypes:
            wtt = WorkerTaskType.query.filter_by(
                worker_id=user_id, tasktype_id=tasktype_id, status="active"
            ).first()
            if wtt:
                wtt.status = "finished"
                wtt.end_date = datetime.utcnow()
                updated = True  # ⚡️ теж змінились дані

        # worker_status
        new_worker_status = request.form.get("worker_status")
        if new_worker_status and new_worker_status != user.worker_status:
            user.worker_status = new_worker_status
            updated = True

        # unavailable_until
        if user.worker_status == "active":
            # якщо працівник активний → не може бути unavailable_until
            user.unavailable_until = None
        else:
            unavailable_until_str = request.form.get("unavailable_until")
            if unavailable_until_str:
                user.unavailable_until = datetime.strptime(
                    unavailable_until_str, "%Y-%m-%d"
                ).date()
                updated = True
            else:
                user.unavailable_until = None

        try:
            if updated:
                db.session.commit()
                flash(f'User #{user_id} tasktypes were successfully updated.', 'success')
            else:
                flash('No changes detected.', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while updating user info: {e}', 'error')

        return redirect(url_for('manager_views.edit_worker_profile', user_id=user.worker_id))

    
    status_options = ["active", "terminated", "maternity_leave", "vacation_leave", "sick_leave"]

    return render_template("manager/edit_worker_profile.html", user=user,
                            tasktypes=tasktypes,
                            worker_tasktype_ids=worker_tasktype_ids,
                            worker_tasktypes=worker_tasktypes,
                            status_options=status_options)


# @manager_views.route('/questions', methods=['GET', 'POST'])
# @login_required
# @role_required([2])
# def questions():
#     return render_template("manager/questions.html")

