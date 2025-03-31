from typing import Dict, Any


class MessageFactory:
    WELCOME_NEW = "Добро пожаловать, {name}!👋\nРегистрация выполнена успешно."
    WELCOME_BACK = "С возвращением, {name}! 👋"

    AUTH_MESSAGES = {
        "authenticated": "✅ Вы успешно авторизовались, теперь можно вернуться обратно ↩",
        "failed": "⚠ Произошла ошибка авторизации, повторите попытку позже."
    }

    @classmethod
    def get_start_message(cls, user: Dict[str, Any], created: bool, nonce_status: str | None) -> str:
        """Собирает финальное сообщение в зависимости от условий"""
        auth_message = cls.AUTH_MESSAGES.get(nonce_status, "")

        if not created and auth_message:
            return auth_message

        name = user.get("first_name", "")
        welcome = cls.WELCOME_NEW.format(name=name) if created else cls.WELCOME_BACK.format(name=name)
        return welcome + (f"\n\n{auth_message}" if auth_message else "")

