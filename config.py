"""
config.py — конфигурация бота.

Все чувствительные и настраиваемые параметры берутся из переменных
окружения (.env), чтобы не хранить токен в коде.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Загружаем переменные из файла .env, лежащего рядом с этим файлом
load_dotenv()


@dataclass(frozen=True)
class Config:
    # Токен бота, выданный @BotFather
    bot_token: str

    # Максимально допустимое количество сообщений за один запуск
    max_messages: int

    # Задержка между отправкой сообщений (в секундах)
    send_delay: float

    # Кулдаун между запусками рассылки в одном чате (в секундах)
    cooldown_seconds: int


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не найден. Скопируйте .env.example в .env "
            "и укажите токен, полученный у @BotFather."
        )

    return Config(
        bot_token=token,
        max_messages=_get_env_int("MAX_MESSAGES", 100),
        send_delay=_get_env_float("SEND_DELAY", 0.6),
        cooldown_seconds=_get_env_int("COOLDOWN_SECONDS", 30),
    )
