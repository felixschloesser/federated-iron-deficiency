from django.apps import AppConfig


class DeploymentConfig(AppConfig):
    name = "hospital.deployment"
    label = "deployment"
    verbose_name = "Deployed model"
