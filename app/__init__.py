import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name='default'):
    """Flask application factory."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from app.routes import dashboard, services, traces
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(services.bp)
    app.register_blueprint(traces.bp)

    # Initialize background scheduler
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        from app.services.sync_service import start_scheduler
        start_scheduler(app)

    return app


# Import models to ensure they're registered with SQLAlchemy
from app import models
