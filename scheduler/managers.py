from django.db import models
from polymorphic.managers import PolymorphicManager


class BaseManager(models.Manager):
    def active_keyboard_data(self):
        raise NotImplementedError("Subclasses must implement fetch_active_data method")


class GroupManager(BaseManager):
    def active_keyboard_data(self):
        return (self.filter(is_active=True).values('id', 'title', 'grade', 'faculty__short_title')
                .order_by('faculty__short_title', 'grade', 'title'))


class TeacherManager(BaseManager):
    def active_keyboard_data(self):
        return self.filter(is_active=True).values('id', 'short_name').order_by('short_name')


class SubscriptionManager(PolymorphicManager):
    def invalidate_all_subscriptions(self, user_id: int):
        self.filter(user_id=user_id).delete()


class UserManager(models.Manager):
    def get_or_create_by_telegram_user(self, telegram_user):
        return self.get_or_create(
            telegram_id=str(telegram_user.id),
            defaults={
                'first_name': telegram_user.first_name,
                'last_name': telegram_user.last_name or '',
                'is_active': True
            }
        )

    def reset_subgroup(self, user_id: int):
        self.filter(id=user_id).update(subgroup='0')
