import random
from sqlalchemy.orm import aliased
from sqlalchemy import func

from . import db
from .models import (
    Worker, Role, TaskType, WorkerTaskType, WorkerTask,
    WorkerStatusEnum, HistoryStatusEnum, WorkerTaskStatusEnum, WorkerRole, Task,
    WorkerTaskAssignmentMethodEnum, WorkerDepartment, Department
)

def choose_worker(task: Task, ignore_max_load: bool = False, exclude_worker_id: int = None):
    """
    Вибирає найкращого виконавця або ескалює завдання на менеджера.

    :param task: Об'єкт завдання, для якого шукаємо виконавця.
    :param ignore_max_load: Якщо True, ігнорує максимальне навантаження.
    :return: Словник {'worker_id': ID, 'method': '...'} або None.
    """
    task_type = task.active_task_type
    if not task_type:
        print(f"ПОМИЛКА: Не вдалося визначити активний тип для завдання #{task.id}")
        return None
    
    task_priority = task_type.priority

    # ... (код для пошуку eligible_workers залишається таким самим) ...
    worker_role_obj = Role.query.filter_by(name='Worker').first()
    if not worker_role_obj: return None

    # --- B-) ОНОВЛЕНИЙ ЗАПИТ ДЛЯ ПОШУКУ ПРАЦІВНИКІВ ---
    query = (
        Worker.query
        .join(Worker.roles_history)
        .filter(WorkerRole.role_id == worker_role_obj.role_id, WorkerRole.status == HistoryStatusEnum.ACTIVE)
        .join(Worker.task_type_competencies)
        .filter(WorkerTaskType.tasktype_id == task_type.tasktype_id, WorkerTaskType.status == HistoryStatusEnum.ACTIVE)
        .filter(Worker.worker_status == WorkerStatusEnum.ACTIVE)
    )

    # Додаємо фільтр виключення, якщо ID передано
    if exclude_worker_id:
        query = query.filter(Worker.worker_id != exclude_worker_id)
        # Альтернативний варіант з 'not_':
        # query = query.filter(not_(Worker.worker_id == exclude_worker_id))

    eligible_workers = query.all()
    # --- КІНЕЦЬ ОНОВЛЕНОГО ЗАПИТУ ---

    candidates = []
    if eligible_workers:
        for worker in eligible_workers:
            # ... (код для розрахунку score залишається таким самим) ...
            current_load = db.session.query(func.count(WorkerTask.id)).filter(
                WorkerTask.worker_id == worker.worker_id,
                WorkerTask.status == WorkerTaskStatusEnum.ACTIVE
            ).scalar() or 0
            
            is_overloaded = worker.max_load is not None and current_load >= worker.max_load
            if is_overloaded and task_priority < 3 and not ignore_max_load:
                continue

            competency = worker.task_type_competencies.filter_by(tasktype_id=task_type.tasktype_id, status=HistoryStatusEnum.ACTIVE).first()
            expertise = competency.expertise if competency and competency.expertise is not None else 1

            score = (expertise * 10) - current_load
            candidates.append((worker, score))

    # --- ГОЛОВНА ЗМІНА: ЛОГІКА ЕСКАЛАЦІЇ ---
    if candidates:
        max_score = max(score for _, score in candidates)
        top_candidates = [w for w, s in candidates if s == max_score]
        chosen_worker = random.choice(top_candidates)
        return {
            'worker_id': chosen_worker.worker_id,
            'method': WorkerTaskAssignmentMethodEnum.AUTOMATIC
        }
    else:
        # Кандидатів не знайдено, шукаємо IT-менеджера
        print(f"Кандидатів-виконавців не знайдено для завдання #{task.id}. Спроба ескалації на IT-менеджера.")

        # B-) Припускаємо, що IT відділ має назву 'IT Department' (змініть за потреби)
        it_department = Department.query.filter(Department.name.ilike('%IT%')).first() 
        manager_role = Role.query.filter_by(name='Manager').first()

        if not it_department or not manager_role:
            print(f"КРИТИЧНА ПОМИЛКА: Не знайдено IT відділ ('%IT%') або роль 'Manager'. Неможливо ескалувати завдання #{task.id}")
            return None

        # Знаходимо активного менеджера в IT відділі
        it_manager = (
            Worker.query
            .join(WorkerDepartment, Worker.worker_id == WorkerDepartment.worker_id)
            .join(WorkerRole, Worker.worker_id == WorkerRole.worker_id)
            .filter(
                WorkerDepartment.department_id == it_department.department_id,
                WorkerDepartment.status == HistoryStatusEnum.ACTIVE,
                WorkerRole.role_id == manager_role.role_id,
                WorkerRole.status == HistoryStatusEnum.ACTIVE,
                Worker.worker_status == WorkerStatusEnum.ACTIVE
            )
            .first() # Беремо першого знайденого
        )

        if it_manager:
            print(f"Ескалація завдання #{task.id} до IT-менеджера ID:{it_manager.worker_id} ({it_manager.full_name})")
            return {
                'worker_id': it_manager.worker_id,
                'method': WorkerTaskAssignmentMethodEnum.ESCALATED_TO_IT_MANAGER # B-) Новий метод
            }
        else:
            # Критична ситуація: немає активного IT-менеджера
            print(f"КРИТИЧНА ПОМИЛКА: Не знайдено активного IT-менеджера у відділі '{it_department.name}' для ескалації завдання #{task.id}")
            # TODO: Можливо, сповістити головного адміністратора системи
            return None
        

        