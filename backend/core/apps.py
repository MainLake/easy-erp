from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Core'

    def ready(self):
        """Register signal handlers when the app is loaded."""
        import core.signals  # noqa: F401 — registers pre_delete handler
