from flask import Flask
from dotenv import load_dotenv
from flask_jwt_extended import JWTManager

from .config import Config
from .extensions import cors


def create_app() -> Flask:
    load_dotenv(override=True)  # loads .env if present

    app = Flask(__name__)
    app.config.from_object(Config)

    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"] or "*"}},
        supports_credentials=True,
    )

    #  Initialize JWT (required for cookie auth / @jwt_required)
    JWTManager(app)

    #  Blueprints
    from .routes.health import bp as health_bp
    from .routes.subnets import bp as subnets_bp
    from .routes.identity import bp as identity_bp
    from .routes.auth import bp as auth_bp  
    from .routes.logout import bp as logout_bp
    from .routes.policy_exemptions import bp as policy_exemptions_bp
    from .routes.install_config import bp as install_config_bp
    from .routes.installer import bp as installer_bp
    from app.routes.clusters import bp as clusters_bp
    from .routes.cluster_destroy import bp as clusters_destroy_bp

    app.register_blueprint(clusters_destroy_bp)
    
    app.register_blueprint(clusters_bp)    
    app.register_blueprint(installer_bp)
    app.register_blueprint(install_config_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(subnets_bp)
    app.register_blueprint(identity_bp)
    app.register_blueprint(auth_bp)  
    app.register_blueprint(logout_bp)
    app.register_blueprint(policy_exemptions_bp)


    return app
