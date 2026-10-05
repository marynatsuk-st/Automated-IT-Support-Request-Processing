from flask import Blueprint, jsonify
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
# from .role_dec import role_required
from .models import Worker, Department, Role, WorkerDepartment, WorkerRole
from . import db
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import asc, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
import traceback
from .decorators import role_required 

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
            .all()
        )
        
        roles = Role.query.all()
        departments = Department.query.all()


    except SQLAlchemyError as e:
        print(f"SQLAlchemy Error: {e}")
        return "Database connection or query error", 500
    
    return render_template("admin/admin_dashboard.html", users=users, roles=roles, departments=departments)

# create a new user
@admin_views.route('/create_user', methods=['GET', 'POST'])
# @login_required
# @role_required([1]) #Admin
def create_user():

    if request.method == 'POST':
        print("FORM DATA:", request.form)
        try:
            surname = request.form['firstName']
            name = request.form['lastName']
            email = request.form['email']
            phone = request.form['phone']
            date_of_birth = datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date()
            department_id = int(request.form['department_id'])
            role_id = int(request.form['role'])
            username = request.form['username']
            password1 = request.form['password1']
            title = request.form['title']

            if len(surname) < 2:
                flash('First name must be greater than 1 character.', 'error')
            elif len(name) < 2:
                flash('Last name must be greater than 1 character.', 'error')
            elif len(password1) < 7:
                flash('Password must be at least 7 characters.', 'error')
            else:
                user = Worker.query.filter_by(email=email).first()
                if user:
                    flash('This user already exists.', 'error')
                else:

                    new_user = Worker(
                        surname=surname,
                        name=name,
                        email=email,
                        phone=phone,
                        date_of_birth=date_of_birth,
                        username=username,
                        password_hash=generate_password_hash(password1, method='pbkdf2:sha256'),
                        worker_status = 'active'
                    )



                    db.session.add(new_user)
                    db.session.flush()
                    print(">>> New user ID:", new_user.worker_id)


                    department_link = WorkerDepartment(
                        worker_id=new_user.worker_id,
                        department_id=department_id,
                        start_date=datetime.utcnow().date(),
                        status='active',
                        title = title
                    )
                    role_link = WorkerRole(
                        worker_id=new_user.worker_id,
                        role_id=role_id,
                        start_date=datetime.utcnow().date(),
                        status='active'
                    )

                    db.session.add_all([department_link, role_link])
                    db.session.commit()
                    flash("Користувача створено", "success")

        except SQLAlchemyError as e:
            db.session.rollback()
            traceback.print_exc()
            print("DB ERROR DETAILS:", str(e.__dict__.get("orig")))
            flash(f"Помилка в БД: {str(e)}", "danger")
        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Інша помилка: {str(e)}", "danger")

        return redirect(url_for('admin_views.admin_dashboard'))

    roles = Role.query.all()
    departments = Department.query.all()

    department_id = request.args.get('department_id', type=int)
    managers = []

    if department_id:
        manager_role = Role.query.filter_by(name='Manager').first()
        if manager_role:
            managers = db.session.query(Worker).join(WorkerRole).join(WorkerDepartment).filter(
                WorkerRole.role_id == manager_role.role_id,
                WorkerDepartment.department_id == department_id,
                WorkerRole.status == 'active',
                WorkerDepartment.status == 'active'
            ).all()

    return render_template("admin/create_user.html", user=current_user, departments=departments, roles=roles, managers=managers)


@admin_views.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    user = Worker.query.get_or_404(user_id)
    roles = Role.query.all()
    departments = Department.query.all()
    
    current_department = db.session.query(WorkerDepartment).filter_by(worker_id=user.worker_id, status='active').first()
    current_role = db.session.query(WorkerRole).filter_by(worker_id=user.worker_id, status='active').first()

    
    selected_department_id = current_department.department_id if current_department else None
    selected_role_id = current_role.role_id if current_role else None
    selected_manager_id = user.manager_id

    # Менеджери
    manager_role = Role.query.filter_by(name='Manager').first()
    managers = []
    if manager_role and selected_department_id:
        managers = Worker.query.join(WorkerRole).join(WorkerDepartment).filter(
            WorkerRole.role_id == manager_role.role_id,
            WorkerDepartment.department_id == selected_department_id,
            Worker.worker_id != user.worker_id,  # виключити себе
            WorkerRole.status == 'active',
            WorkerDepartment.status == 'active'
        ).all()

    if request.method == 'POST':
        try:
            updated = False
            form = request.form

            # Основні поля
            if user.name != form['lastName']:
                user.name = form['lastName']
                updated = True
            if user.surname != form['firstName']:
                user.surname = form['firstName']
                updated = True
            if user.email != form['email']:
                user.email = form['email']
                updated = True
            if user.phone != form['phone']:
                user.phone = form['phone']
                updated = True
            if user.username != form['username']:
                user.username = form['username']
                updated = True

            # Дата народження
            new_dob = datetime.strptime(form['date_of_birth'], '%Y-%m-%d').date()
            if user.date_of_birth != new_dob:
                user.date_of_birth = new_dob
                updated = True

            # Пароль
            if form['password1']:
                new_hash = generate_password_hash(form['password1'], method='pbkdf2:sha256')
                if user.password_hash != new_hash:
                    user.password_hash = new_hash
                    updated = True

            # Посада та роль
            new_title = form['title']
            if new_title != current_department.title:
                current_department.title = new_title
                
            new_role_id = int(form['role'])
            new_department_id = int(form['department_id']) if form['department_id'] else None

            if current_role and current_role.role_id != new_role_id:
                current_role.role_id = new_role_id
                updated = True

            if current_department:
                if current_department.department_id != new_department_id:
                    current_department.department_id = new_department_id
                    updated = True
                if current_department.title != new_title:
                    current_department.title = new_title
                    updated = True

            new_manager_id = form.get('manager')
            if new_manager_id:
                new_manager_id = int(new_manager_id)
                if user.manager_id != new_manager_id:
                    user.manager_id = new_manager_id
                    updated = True

            new_worker_status = form.get("worker_status")
            if new_worker_status:
                if new_worker_status != user.worker_status:
                    user.worker_status = new_worker_status
                    updated = True

            unavailable_until_str = request.form.get("unavailable_until")
            if unavailable_until_str:
                user.unavailable_until = datetime.strptime(unavailable_until_str, "%Y-%m-%d").date()
                updated = True
            else:
                user.unavailable_until = None

            if updated:
                db.session.commit()
                flash('User updated successfully.', 'success')
            else:
                flash('No changes detected.', 'info')

            return redirect(url_for('admin_views.admin_dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error while updating: {str(e)}", "danger")
            return redirect(url_for('admin_views.admin_dashboard'))
    
    status_options = ["active", "terminated", "maternity_leave", "vacation_leave", "sick_leave"]

    return render_template('admin/edit_user.html',
                           user=user,
                           roles=roles,
                           departments=departments,
                           managers=managers,
                           selected_department_id=selected_department_id,
                           selected_role_id=selected_role_id,
                           selected_manager_id = selected_manager_id,
                           status_options=status_options,
                           current_department=current_department)

# disable user
@admin_views.route('/delete_user/<int:user_id>', methods=['POST'])
# @login_required
# @role_required([1]) # Admin
def delete_user(user_id):
    # user = Worker.query.get_or_404(user_id)
    # user.status = 'inactive'

    # #find all devices from this user and make them available
    # devices = Device.query.join(DeviceWorker).filter(DeviceWorker.worker_id == user_id).all()
    # for device in devices:
    #     device.status = 'Available'
    
    # #delete all requests by this user that are not completed
    # Task.query.filter(Task.created_by == user_id, Task.status != 'Completed').delete(synchronize_session=False)

    # #delete all tasktype worker connections for this worker
    # TaskTypeWorker.query.filter_by(worker_id=user_id).delete()

    # #delete all device worker connections for this worker
    # DeviceWorker.query.filter_by(worker_id=user_id).delete()


    # try:
    #     db.session.commit()
    #     flash('User #{} was successfully disactivated.'.format(str(user_id)), 'success')
    # except Exception as e:
    #     db.session.rollback()
    #     print('An error occurred while deleting tasks: {}'.format(str(e)))

    return redirect(url_for('admin_views.admin_dashboard'))



