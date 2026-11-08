from django.apps import AppConfig


class DeploymentConfig(AppConfig):
    name = "web.hospital.deployment"
    label = "deployment"
    verbose_name = "Deployed screening model"
