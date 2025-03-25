import time
from typing import Any, TypeVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.cache import caches
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.models import TokenUser
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken, Token

cache = caches['whitelist']

AuthUser = TypeVar("AuthUser", AbstractBaseUser, TokenUser)


class CustomRefreshToken(Token):
    token_type = "refresh"
    lifetime = api_settings.REFRESH_TOKEN_LIFETIME
    no_copy_claims = (
        api_settings.TOKEN_TYPE_CLAIM,
        "exp",
        api_settings.JTI_CLAIM,
        "jti",
    )
    access_token_class = AccessToken

    payload: dict[str, Any]

    @property
    def access_token(self) -> AccessToken:
        """
        Возвращает токен доступа, созданный из этого refresh-токена
        """
        access = self.access_token_class()
        access.set_exp(from_time=self.current_time)
        no_copy = self.no_copy_claims
        for claim, value in self.payload.items():
            if claim in no_copy:
                continue
            access[claim] = value

        return access

    def verify(self, *args, **kwargs) -> None:
        """
        Проверяет наличие токена в белом списке.
        """
        self.check_whitelist()
        super().verify(*args, **kwargs)  # type: ignore

    def check_whitelist(self) -> None:
        """
        Проверяет наличие токена в белом списке.
        `TokenError` если нет.
        """
        jti = self.payload[api_settings.JTI_CLAIM]
        if not cache.has_key(jti):
            raise TokenError(_("Token is not in whitelist"))

    def add_to_whitelist(self) -> None:
        """
        Добавляет токен в белый список.
        """
        jti = self.payload[api_settings.JTI_CLAIM]
        exp = self.payload["exp"]
        timeout = max(exp - time.time(), 1)  # Минимальное время хранения — 1 сек
        cache.set(jti, True, timeout=timeout)

    def remove_from_whitelist(self):
        """
        Удаляет токен из белого списка.
        """
        jti = self.payload[api_settings.JTI_CLAIM]
        if cache.has_key(jti):
            cache.delete(jti)

    @classmethod
    def for_user(cls, user: AuthUser) -> 'CustomRefreshToken':
        """
        Создает токен и сразу добавляет в белый список.
        """
        token = super().for_user(user)  # type: ignore
        token.add_to_whitelist()  # type: ignore
        return token  # type: ignore
