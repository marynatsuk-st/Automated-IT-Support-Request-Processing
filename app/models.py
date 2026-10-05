from app import db
from datetime import datetime
from flask_login import UserMixin


class Department(db.Model):
    department_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class WorkerDepartment(db.Model):
    __tablename__ = "worker_department_conn"
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'))
    department_id = db.Column(db.Integer, db.ForeignKey('department.department_id'))
    start_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='active')
    title = db.Column(db.String(50), nullable=False)

class Role(db.Model):
    role_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class WorkerRole(db.Model):
    __tablename__ = "worker_role_conn"
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'))
    role_id = db.Column(db.Integer, db.ForeignKey('role.role_id'))
    start_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='active')
   
class Worker(db.Model, UserMixin):
    __tablename__ = 'worker'
    worker_id = db.Column(db.Integer, primary_key=True)
    surname = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(120), unique=True, nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    worker_status = db.Column(db.String(50), default="active") 
    unavailable_until = db.Column(db.Date, nullable=True)  
    max_load = db.Column(db.Integer, nullable=True)
    @property
    def id(self):
        return self.worker_id
    
class TaskType(db.Model):
    __tablename__ = 'tasktype'
    tasktype_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))

class WorkerTaskType(db.Model):
    __tablename__ = 'worker_tasktype'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'))
    tasktype_id = db.Column(db.Integer, db.ForeignKey('tasktype.tasktype_id'))
    start_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='active')
    tasktype = db.relationship("TaskType", backref="worker_tasktypes")
    expertise = db.Column(db.Integer, nullable = True)




# class Device(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100))
#     type = db.Column(db.String(50))
#     serial_number = db.Column(db.String(100), unique=True)
#     specifications = db.Column(db.Text)

# class DeviceWorker(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     device_id = db.Column(db.Integer, db.ForeignKey('device.id'))
#     worker_id = db.Column(db.Integer, db.ForeignKey('user.id'))
#     status = db.Column(db.String(50))
#     started_at = db.Column(db.DateTime, default=datetime.utcnow)
#     ended_at = db.Column(db.DateTime, nullable=True)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    #title = db.Column(db.String(200))
    text = db.Column(db.Text)
    status = db.Column(db.String(50), default='active')
    priority = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, default=None)
    customer_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'))
    #assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    tasktype_id = db.Column(db.Integer, db.ForeignKey('tasktype.tasktype_id'))

class WorkerTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'))
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'))
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.String(50))
    unassigned_at = db.Column(db.DateTime, default=None)
    unassigned_by = db.Column(db.Integer, default=None)
    status = db.Column(db.String(50), default='active')
    finished_at = db.Column(db.DateTime, default=None)
    priority = db.Column(db.Integer, default=None)
    comment = db.Column(db.String(100), default=None)

