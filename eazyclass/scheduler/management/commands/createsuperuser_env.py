from django.core.management.base import BaseCommand
from scheduler.models import User, Provider
import os
from dotenv import load_dotenv
import logging

logger = logging.Logger(__name__)

load_dotenv()


class Command(BaseCommand):
    help = 'Создает суперпользователя из данных в .env'

    def handle(self, *args, **options):
        # Получаем данные из .env
        social_id = os.getenv('SUPERUSER_SOCIAL_ID')
        provider = os.getenv('SUPERUSER_PROVIDER')
        first_name = os.getenv('SUPERUSER_FIRST_NAME')
        last_name = os.getenv('SUPERUSER_LAST_NAME')

        # Проверяем наличие обязательных данных
        required_fields = {
            'SUPERUSER_SOCIAL_ID': social_id,
            'SUPERUSER_PROVIDER': provider,
            'SUPERUSER_FIRST_NAME': first_name,
            'SUPERUSER_LAST_NAME': last_name,
        }

        logger.info(required_fields)
        missing_fields = [key for key, value in required_fields.items() if not value]
        if missing_fields:
            self.stdout.write(self.style.ERROR(f"Отсутствуют обязательные переменные в .env: {', '.join(missing_fields)}"))
            return

        valid_providers = [p.value for p in Provider]  # ['telegram', 'vk']
        if provider not in valid_providers:
            self.stdout.write(self.style.ERROR(
                f"Недопустимое значение provider: {provider}. Допустимые значения: {', '.join(valid_providers)}"
            ))
            return

        try:
            # Создаем суперпользователя
            user = User.objects.create_superuser(
                social_id=social_id,
                provider=provider,
                first_name=first_name,
                last_name=last_name,
            )
            self.stdout.write(self.style.SUCCESS(f"Суперпользователь успешно создан ID: {user.id}, login: {user.username}."))
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"Ошибка: {str(e)}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Неизвестная ошибка: {str(e)}"))
