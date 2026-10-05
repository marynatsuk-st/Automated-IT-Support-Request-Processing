from app import db
from datetime import datetime
from flask_login import UserMixin
import enum

############# ENUM FOR STATUS ##################

class WorkerStatusEnum(enum.Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    ON_VACATION = 'on_vacation'
    ON_SICK_LEAVE = 'on_sick_leave'

class HistoryStatusEnum(enum.Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'

class TaskStatusEnum(enum.Enum):
    NEW = 'new'
    IN_PROGRESS = 'in_progress'
    ON_HOLD = 'on_hold'
    CLOSED = 'closed'
    CANCELLED = 'cancelled'

class TaskDetectionMethodEnum(enum.Enum):
    NLP_AUTO = 'nlp_auto'
    MANUAL_OVERRIDE = 'manual_override'

class WorkerTaskStatusEnum(enum.Enum):
    ACTIVE = 'active'
    FINISHED = 'finished'
    REASSIGNED = 'reassigned'
    CANCELLED = 'cancelled'
    ESCALATED_TO_IT_MANAGER = 'escalated_to_it_manager'


class WorkerTaskAssignmentMethodEnum(enum.Enum):
    AUTOMATIC = 'automatic'
    MANUAL = 'manual'
    ESCALATED_TO_IT_MANAGER = 'escalated_to_it_manager'
    RETURNED_FOR_REVIEW = 'returned_for_review'


class DeviceStatusEnum(enum.Enum):
    AVAILABLE = 'available'
    IN_USE = 'in_use'
    UNDER_REPAIR = 'under_repair'
    IN_TRANSIT = 'in_transit'
    DECOMMISSIONED = 'decommissioned'

class AssignmentStatusEnum(enum.Enum):
    ACTIVE = 'active'
    RETURNED = 'returned'

#######################################################

class Department(db.Model):
    __tablename__ = 'department' 
    department_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    workers_history = db.relationship('WorkerDepartment', back_populates='department')

    def __repr__(self):
        return f'<Department {self.name}>'


class WorkerDepartment(db.Model):
    __tablename__ = "worker_department_conn"
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.department_id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.Enum(HistoryStatusEnum), nullable=False, default=HistoryStatusEnum.ACTIVE)
    title = db.Column(db.String(100), nullable=False) 

    worker = db.relationship('Worker', back_populates='departments_history')
    department = db.relationship('Department', back_populates='workers_history')
    def __repr__(self):
        return f'<WorkerDepartment worker_id={self.worker_id} dept_id={self.department_id}>'


class Role(db.Model):
    __tablename__ = 'role'
    role_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    workers_history = db.relationship('WorkerRole', back_populates='role')

    def __repr__(self):
        return f'<Role {self.name}>'




 
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
    worker_status = db.Column(db.Enum(WorkerStatusEnum), default=WorkerStatusEnum.ACTIVE)
    unavailable_until = db.Column(db.Date, nullable=True)
    max_load = db.Column(db.Integer, nullable=True)

    # --- Relationships ---
    departments_history = db.relationship('WorkerDepartment', back_populates='worker', lazy='dynamic')
    task_type_competencies = db.relationship('WorkerTaskType', back_populates='worker', lazy='dynamic')
    roles_history = db.relationship('WorkerRole', back_populates='worker', lazy='dynamic')



    # Self-referencing relationship для менеджера
    manager = db.relationship(
        'Worker',
        remote_side=[worker_id],
        backref='subordinates'
    )

    # --- Properties ---
    @property
    def id(self):
        return self.worker_id

    @property
    def full_name(self):
        return f"{self.name} {self.surname}"

    @property
    def current_department_record(self):
        """Повертає поточний активний ЗАПИС про роботу у відділі (об'єкт WorkerDepartment)."""
        return self.departments_history.filter_by(status=HistoryStatusEnum.ACTIVE).first()

    @property
    def current_department(self):
        """Повертає поточний активний відділ працівника (об'єкт Department)."""
        record = self.current_department_record
        return record.department if record else None
    
    @property
    def current_role_record(self):
        """Повертає поточний активний ЗАПИС про роль (об'єкт WorkerRole)."""
        return self.roles_history.filter_by(status=HistoryStatusEnum.ACTIVE).first()

    @property
    def current_role(self):
        """Повертає поточну активну роль працівника."""
        active_role_record = self.roles_history.filter_by(status=HistoryStatusEnum.ACTIVE).first()
        return active_role_record.role if active_role_record else None

    def __repr__(self):
        return f'<Worker {self.id}: {self.full_name}>'

class WorkerRole(db.Model):
    __tablename__ = "worker_role_conn"
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.role_id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.Enum(HistoryStatusEnum), nullable=False, default=HistoryStatusEnum.ACTIVE)
    
    worker = db.relationship('Worker', back_populates='roles_history')
    role = db.relationship('Role', back_populates='workers_history')
    
    def __repr__(self):
        return f'<WorkerRole worker_id={self.worker_id} role_id={self.role_id}>'   

class TaskType(db.Model):
    __tablename__ = 'tasktype'
    tasktype_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=1)

    # Relationships
    worker_competencies = db.relationship('WorkerTaskType', back_populates='task_type')
    task_history = db.relationship('Task_TaskType', back_populates='task_type')

    def __repr__(self):
        return f'<TaskType {self.tasktype_id}: {self.name}>'
    

class WorkerTaskType(db.Model):
    __tablename__ = 'worker_tasktype'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=False)
    tasktype_id = db.Column(db.Integer, db.ForeignKey('tasktype.tasktype_id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.Enum(HistoryStatusEnum), nullable=False, default=HistoryStatusEnum.ACTIVE)
    expertise = db.Column(db.Integer, nullable=True, default=1)

    # Двосторонні зв'язки
    worker = db.relationship("Worker", back_populates="task_type_competencies") 
    task_type = db.relationship("TaskType", back_populates="worker_competencies")

    def __repr__(self):
        return f'<WorkerTaskType worker_id={self.worker_id} type_id={self.tasktype_id}>'

class Task(db.Model):
    __tablename__ = 'task' 
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum(TaskStatusEnum), default=TaskStatusEnum.NEW, nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=True)

    # --- Relationships ---
    customer = db.relationship('Worker', foreign_keys=[customer_id], backref='created_tasks')
    device = db.relationship('Device', backref='related_tasks')
    
    task_types_history = db.relationship('Task_TaskType', back_populates='task', lazy='dynamic', cascade="all, delete-orphan")
    assignments_history = db.relationship('WorkerTask', back_populates='task', lazy='dynamic', cascade="all, delete-orphan")

    # --- Properties ---
    @property
    def active_task_type_record(self):
        """Повертає поточний активний запис про тип завдання (об'єкт Task_TaskType)."""
        return self.task_types_history.filter_by(is_active=True).first()

    @property
    def active_task_type(self):
        """Повертає поточний активний тип завдання (об'єкт TaskType)."""
        record = self.active_task_type_record
        return record.task_type if record else None
    
    @property
    def current_assignment(self):
        """Повертає поточне активне призначення (об'єкт WorkerTask)."""
        return self.assignments_history.filter_by(status=WorkerTaskStatusEnum.ACTIVE).first()
        
    @property
    def current_worker(self):
        """Повертає поточного виконавця завдання (об'єкт Worker)."""
        assignment = self.current_assignment
        return assignment.worker if assignment else None

    def __repr__(self):
        return f'<Task {self.id} (Status: {self.status.name})>'

class Task_TaskType(db.Model):
    __tablename__ = 'task_tasktype'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    tasktype_id = db.Column(db.Integer, db.ForeignKey('tasktype.tasktype_id'), nullable=False)
    detection_method = db.Column(db.Enum(TaskDetectionMethodEnum), nullable=False)
    probability = db.Column(db.Float, nullable=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    task = db.relationship('Task', back_populates='task_types_history')
    task_type = db.relationship('TaskType', back_populates='task_history')
    assigned_by = db.relationship('Worker', foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f'<Task_TaskType task_id={self.task_id} type_id={self.tasktype_id} active={self.is_active}>'

class WorkerTask(db.Model):
    __tablename__ = 'worker_task' 
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assign_method = db.Column(db.Enum(WorkerTaskAssignmentMethodEnum))
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=False)
    unassigned_at = db.Column(db.DateTime, nullable=True)
    unassigned_by_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=True)
    status = db.Column(db.Enum(WorkerTaskStatusEnum), default=WorkerTaskStatusEnum.ACTIVE)
    finished_at = db.Column(db.DateTime, nullable=True)
    comment = db.Column(db.String(255), nullable=True)

    # Relationships
    worker = db.relationship('Worker', foreign_keys=[worker_id], backref='assigned_tasks')
    task = db.relationship('Task', back_populates='assignments_history')
    assigned_by = db.relationship('Worker', foreign_keys=[assigned_by_id])
    unassigned_by = db.relationship('Worker', foreign_keys=[unassigned_by_id])

    def __repr__(self):
        return f'<WorkerTask task_id={self.task_id} worker_id={self.worker_id} status={self.status.name}>'



class DeviceAttribute(db.Model):
    __tablename__ = 'device_attribute'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    data_type = db.Column(db.String(50), nullable=False, default='string')
    
    def __repr__(self):
        return f'<DeviceAttribute {self.id}: {self.name}>'

class DeviceTypeAttribute(db.Model):
    __tablename__ = 'devicetype_attribute_conn'
    id = db.Column(db.Integer, primary_key=True)
    devicetype_id = db.Column(db.Integer, db.ForeignKey('devicetype.id'), nullable=False)
    attribute_id = db.Column(db.Integer, db.ForeignKey('device_attribute.id'), nullable=False)
    weight = db.Column(db.Float, default=1.0)
    
    device_type = db.relationship('DeviceType', back_populates='relevant_attributes')
    attribute = db.relationship('DeviceAttribute')
    
    def __repr__(self):
        return f'<DeviceTypeAttribute type_id={self.devicetype_id} attr_id={self.attribute_id}>'

class DeviceAttributeValue(db.Model):
    __tablename__ = 'device_attribute_value'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    attribute_id = db.Column(db.Integer, db.ForeignKey('device_attribute.id'), nullable=False)
    value = db.Column(db.String(255), nullable=False)
    
    device = db.relationship("Device", back_populates="attributes")
    attribute = db.relationship("DeviceAttribute")

    def __repr__(self):
        return f'<DeviceAttributeValue device_id={self.device_id} attr_id={self.attribute_id} value="{self.value}">'

class DeviceType(db.Model):
    __tablename__ = 'devicetype'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=1)


    devices = db.relationship('Device', back_populates='device_type')
    relevant_attributes = db.relationship('DeviceTypeAttribute', back_populates='device_type')

    def __repr__(self):
        return f'<DeviceType {self.id}: {self.name}>'

class Device(db.Model):
    __tablename__ = 'device'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(100), unique=True, nullable=False)
    #inventory_number = db.Column(db.String(100), unique=True, nullable=True) # Додано інвентарний номер
    device_type_id = db.Column(db.Integer, db.ForeignKey('devicetype.id'), nullable=False)
    status = db.Column(db.Enum(DeviceStatusEnum), default=DeviceStatusEnum.AVAILABLE, nullable=False)
    
    # --- Relationships ---
    device_type = db.relationship("DeviceType", back_populates="devices")
    attributes = db.relationship("DeviceAttributeValue", back_populates="device", cascade="all, delete-orphan", lazy='joined')
    worker_assignment_history = db.relationship('DeviceWorker', back_populates='device', lazy='dynamic')
    department_assignment_history = db.relationship('DeviceDepartment', back_populates='device', lazy='dynamic')
    
    # --- Properties ---
    @property
    def specs_dict(self):
        """Повертає характеристики пристрою у вигляді зручного словника."""
        return {attr_val.attribute.name: attr_val.value for attr_val in self.attributes}

    @property
    def current_worker(self):
        """Повертає працівника, за яким зараз закріплений пристрій (об'єкт Worker)."""
        active_assignment = self.worker_assignment_history.filter_by(status=AssignmentStatusEnum.ACTIVE).first()
        return active_assignment.worker if active_assignment else None

    @property
    def current_department(self):
        """Повертає відділ, за яким зараз закріплений пристрій (об'єкт Department)."""
        active_assignment = self.department_assignment_history.filter_by(status=AssignmentStatusEnum.ACTIVE).first()
        return active_assignment.department if active_assignment else None

    def __repr__(self):
        return f'<Device {self.id}: {self.name} (SN: {self.serial_number})>'

class DeviceWorker(db.Model):
    __tablename__ = 'device_worker_conn'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.worker_id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    returned_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.Enum(AssignmentStatusEnum), default=AssignmentStatusEnum.ACTIVE, nullable=False)
    
    # Двосторонні зв'язки
    device = db.relationship('Device', back_populates='worker_assignment_history')
    worker = db.relationship('Worker', backref='device_assignment_history')

    def __repr__(self):
        return f'<DeviceWorker device_id={self.device_id} worker_id={self.worker_id} status={self.status.name}>'

class DeviceDepartment(db.Model):
    __tablename__ = 'device_department_conn'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.department_id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    returned_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.Enum(AssignmentStatusEnum), default=AssignmentStatusEnum.ACTIVE, nullable=False)

    # Двосторонні зв'язки
    device = db.relationship('Device', back_populates='department_assignment_history')
    department = db.relationship('Department', backref='device_assignment_history')
    
    def __repr__(self):
        return f'<DeviceDepartment device_id={self.device_id} dept_id={self.department_id} status={self.status.name}>'
