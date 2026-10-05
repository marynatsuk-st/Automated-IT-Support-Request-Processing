from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from os import path

# 1. Створюємо екземпляри розширень на глобальному рівні.
#    Тепер models.py може безпечно робити 'from . import db'.
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app():
    """
    Фабрика для створення екземпляра додатку Flask.
    """
    app = Flask(__name__)
    
    # Конфігурація
    app.config['SECRET_KEY'] = 'lqiefuvnlsdfvbuIU34FJVF'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:12345@localhost:5432/itportal'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False

    # 2. Ініціалізуємо розширення з екземпляром додатку
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # Налаштування LoginManager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Будь ласка, увійдіть, щоб отримати доступ до цієї сторінки."
    login_manager.login_message_category = "info"

    # 3. ІМПОРТИ ВАШИХ МОДУЛІВ ТЕПЕР ТУТ, ВСЕРЕДИНІ ФУНКЦІЇ!
    #    Це розриває циклічну залежність.
    from .models import Worker
    from .admin_views import admin_views
    from .auth import auth
    from .manager_views import manager_views
    from .user_views import user_views
    from .worker_views import worker_views
    from .asset_views import asset_views
    from .scheduler import check_and_update_vacation_status

    # Реєстрація blueprints
    app.register_blueprint(auth, url_prefix='/')
    app.register_blueprint(admin_views, url_prefix='/admin')
    app.register_blueprint(manager_views, url_prefix='/manager')
    app.register_blueprint(user_views, url_prefix='/user')
    app.register_blueprint(worker_views, url_prefix='/worker')
    app.register_blueprint(asset_views, url_prefix='/assets')

    # Налаштування завантажувача користувача для Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return Worker.query.get(int(user_id))

    # Створюємо всі таблиці бази даних, якщо вони ще не існують
    with app.app_context():
        db.create_all()

    # Налаштування та запуск планувальника
    if not hasattr(app, 'scheduler'):
        app.scheduler = BackgroundScheduler(daemon=True)
        app.scheduler.add_job(check_and_update_vacation_status, 'cron', hour=3, minute=0, args=[app])
        app.scheduler.start()
        print("Планувальник завдань запущено.")

    return app
