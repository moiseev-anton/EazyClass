from scheduler.models import User
from telebot.types import User as TelegramUser


class UserService:

    @staticmethod
    def register_user(telegram_id, username):
        if User.objects.exists(telegram_id):
            raise ValidationError("User already exists")
        return User.objects.create(telegram_id, username)

    @staticmethod
    def sign_up_user(telegram_user: TelegramUser) -> bool:
        user, created = User.objects.get_or_create_by_telegram(telegram_user)
        CacheService.cache_user_data(user=user)
        return created
