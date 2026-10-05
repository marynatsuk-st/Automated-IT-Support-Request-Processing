from datetime import date
from .models import Worker, WorkerStatusEnum
from . import db

def check_and_update_vacation_status(app):
    """
    Знаходить всіх працівників, чия відпустка закінчилася,
    і автоматично змінює їх статус на ACTIVE.
    Приймає екземпляр 'app' для доступу до контексту.
    """
    with app.app_context():
        today = date.today()
        
        workers_to_activate = Worker.query.filter(
            Worker.worker_status == WorkerStatusEnum.ON_VACATION,
            Worker.unavailable_until < today
        ).all()

        if not workers_to_activate:
            print(f"[{today}] Планувальник: Не знайдено працівників для активації.")
            return

        print(f"[{today}] Планувальник: Знайдено {len(workers_to_activate)} працівників для активації...")
        
        for worker in workers_to_activate:
            print(f" -> Активуємо {worker.full_name} (ID: {worker.worker_id})")
            worker.worker_status = WorkerStatusEnum.ACTIVE
            worker.unavailable_until = None

        db.session.commit()
        print("Планувальник: Оновлення статусів завершено.")