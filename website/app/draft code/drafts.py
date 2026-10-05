# ## get all data from user/users

# WD = aliased(WorkerDepartment)
# WR = aliased(WorkerRole)
# WT = aliased(WorkerTaskType)

# profile_data = (
#     db.session.query(
#         Worker.worker_id,
#         Worker.surname,
#         Worker.name,
#         Worker.username,
#         Worker.email,
#         Worker.phone,
#         Worker.date_of_birth,
#         Worker.manager_id,
        
#         # Department
#         Department.department_id,
#         Department.name.label("department_name"),
#         WD.start_date.label("department_start_date"),
#         WD.end_date.label("department_end_date"),
#         WD.status.label("department_status"),
#         WD.title.label("department_title"),

#         # Role
#         Role.role_id,
#         Role.name.label("role_name"),
#         WR.start_date.label("role_start_date"),
#         WR.end_date.label("role_end_date"),
#         WR.status.label("role_status"),

#         # TaskType
#         TaskType.tasktype_id,
#         TaskType.name.label("tasktype_name"),
#         WT.start_date.label("tasktype_start_date"),
#         WT.end_date.label("tasktype_end_date"),
#         WT.status.label("tasktype_status"),
#     )
#     .outerjoin(WD, Worker.worker_id == WD.worker_id)
#     .outerjoin(Department, WD.department_id == Department.department_id)
#     .outerjoin(WR, Worker.worker_id == WR.worker_id)
#     .outerjoin(Role, WR.role_id == Role.role_id)
#     .outerjoin(WT, Worker.worker_id == WT.worker_id)
#     .outerjoin(TaskType, WT.tasktype_id == TaskType.tasktype_id)
#     .filter(Worker.worker_id == current_user.worker_id)
#     .all()
# )