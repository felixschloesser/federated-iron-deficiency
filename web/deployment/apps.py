from django.apps import AppConfig


class DeploymentConfig(AppConfig):
    name = "web.deployment"
    label = "deployment"
    verbose_name = "Deployed model"
