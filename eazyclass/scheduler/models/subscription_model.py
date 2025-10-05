from django.conf import settings
from django.db import models
from polymorphic.models import PolymorphicModel

from scheduler.models.abstract_models import TimestampedModel


class Subscription(TimestampedModel, PolymorphicModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions"
    )
    # + created_at из TimestampedModel
    # + updated_at из TimestampedModel

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                name="unique_subscription_per_user"
            )
        ]


class TeacherSubscription(Subscription):
    teacher = models.ForeignKey(
        "scheduler.Teacher", on_delete=models.CASCADE, related_name="subscriptions"
    )


class GroupSubscription(Subscription):
    group = models.ForeignKey(
        "scheduler.Group", on_delete=models.CASCADE, related_name="subscriptions"
    )
