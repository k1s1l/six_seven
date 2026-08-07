"""
bot.py — мемный Telegram-бот «67».

Логика работы:
    * /start показывает главное меню (🔥 67 / ⚙️ Настройки / 🛑 Стоп).
    * «🔥 67» предлагает выбрать количество сообщений (10 / 25 / 50 / 100).
    * После выбора бот отправляет «67» несколько раз ПРЯМО В ТЕКУЩИЙ ЧАТ,
      с небольшой задержкой между сообщениями.
    * Отправка идёт асинхронно (asyncio.Task), поэтому бот не блокируется
      и может обслуживать другие чаты параллельно.
    * У каждого чата есть кулдаун между запусками и возможность
      немедленно остановить рассылку кнопкой «🛑 Стоп».

Важные ограничения (встроены в код и не обходятся пользователем):
    * Бот НИКОГДА не пишет никому в личные сообщения по @username.
    * Сообщения отправляются только в тот chat_id, откуда пришла команда —
      то есть только в чат/группу, где бот уже присутствует и был вызван.
    * Жёсткий верхний предел числа сообщений за один запуск (MAX_MESSAGES).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot67")

config = load_config()
router = Router()


# --------------------------------------------------------------------------- 
# Состояние по каждому чату (без БД — храним в памяти процесса)
# --------------------------------------------------------------------------- 
@dataclass
class ChatState:
    task: Optional[asyncio.Task] = None
    stop_requested: bool = False
    last_run_finished_at: Optional[datetime] = None


chat_states: Dict[int, ChatState] = {}


def get_state(chat_id: int) -> ChatState:
    if chat_id not in chat_states:
        chat_states[chat_id] = ChatState()
    return chat_states[chat_id]


# --------------------------------------------------------------------------- 
# Клавиатуры
# --------------------------------------------------------------------------- 
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔥 67", callback_data="menu:67")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
            [InlineKeyboardButton(text="🛑 Стоп", callback_data="menu:stop")],
        ]
    )


def counts_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10", callback_data="count:10"),
                InlineKeyboardButton(text="25", callback_data="count:25"),
            ],
            [
                InlineKeyboardButton(text="50", callback_data="count:50"),
                InlineKeyboardButton(text="100", callback_data="count:100"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:back")],
        ]
    )


# --------------------------------------------------------------------------- 
# Хендлеры
# --------------------------------------------------------------------------- 
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 <b>Привет! Это мемный бот «67».</b>\n\n"
        "Выбери действие ниже 👇",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "👋 <b>Главное меню</b>\n\nВыбери действие ниже 👇",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def cb_settings(callback: CallbackQuery) -> None:
    text = (
        "⚙️ <b>Настройки бота</b>\n\n"
        f"• Максимум сообщений за запуск: <b>{config.max_messages}</b>\n"
        f"• Задержка между сообщениями: <b>{config.send_delay} сек</b>\n"
        f"• Кулдаун между запусками: <b>{config.cooldown_seconds} сек</b>\n\n"
        "Эти параметры задаются в файле <code>.env</code> "
        "(переменные MAX_MESSAGES, SEND_DELAY, COOLDOWN_SECONDS)."
    )
    await callback.message.edit_text(text, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "menu:stop")
async def cb_stop(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id
    state = get_state(chat_id)

    if state.task is not None and not state.task.done():
        state.stop_requested = True
        await callback.answer("Останавливаю отправку...")
    else:
        await callback.message.answer("ℹ️ Сейчас рассылка не выполняется.")
        await callback.answer()


@router.callback_query(F.data == "menu:67")
async def cb_67(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id
    state = get_state(chat_id)

    # Проверяем, не идёт ли уже отправка в этом чате
    if state.task is not None and not state.task.done():
        await callback.answer("⏳ Отправка уже идёт в этом чате!", show_alert=True)
        return

    # Проверяем кулдаун
    if state.last_run_finished_at is not None:
        elapsed = datetime.now() - state.last_run_finished_at
        remaining = timedelta(seconds=config.cooldown_seconds) - elapsed
        if remaining.total_seconds() > 0:
            seconds_left = int(remaining.total_seconds()) + 1
            await callback.answer(
                f"🕒 Подожди ещё {seconds_left} сек. перед новым запуском.",
                show_alert=True,
            )
            return

    await callback.message.edit_text(
        "Сколько раз отправить <b>67</b> в этот чат?",
        reply_markup=counts_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("count:"))
async def cb_count(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id
    state = get_state(chat_id)

    # Защита от повторного запуска, если пользователь кликнул дважды
    if state.task is not None and not state.task.done():
        await callback.answer("⏳ Отправка уже идёт в этом чате!", show_alert=True)
        return

    requested = int(callback.data.split(":")[1])
    # Жёстко ограничиваем сверху, независимо от того, что пришло в callback_data
    count = min(requested, config.max_messages)

    await callback.answer()
    await callback.message.edit_text(
        f"🔥 <b>Запускаю 67...</b>\nБудет отправлено сообщений: <b>{count}</b>\n\n"
        "Остановить можно в любой момент командой /stop "
        "или кнопкой «🛑 Стоп» в /start.",
    )

    state.stop_requested = False
    state.task = asyncio.create_task(
        send_67_messages(callback.message.bot, chat_id, count, state)
    )


@router.message(F.text == "/stop")
async def cmd_stop(message: Message) -> None:
    chat_id = message.chat.id
    state = get_state(chat_id)

    if state.task is not None and not state.task.done():
        state.stop_requested = True
        await message.answer("🛑 Останавливаю отправку...")
    else:
        await message.answer("ℹ️ Сейчас рассылка не выполняется.")


# --------------------------------------------------------------------------- 
# Логика отправки
# --------------------------------------------------------------------------- 
async def send_67_messages(
    bot: Bot, chat_id: int, count: int, state: ChatState
) -> None:
    """
    Отправляет сообщение "67" `count` раз в указанный chat_id.

    Отправка идёт ТОЛЬКО в chat_id, откуда был вызван бот — никаких
    обращений к другим чатам или пользователям по @username.
    """
    sent = 0
    try:
        for _ in range(count):
            if state.stop_requested:
                break

            try:
                await bot.send_message(chat_id, "67")
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Не удалось отправить сообщение в %s: %s", chat_id, exc)
                # Небольшая доп. пауза при ошибке (например, flood control),
                # чтобы не долбить API повторными запросами.
                await asyncio.sleep(1.0)

            await asyncio.sleep(config.send_delay)

    finally:
        state.task = None
        state.last_run_finished_at = datetime.now()

        if state.stop_requested:
            await bot.send_message(
                chat_id, f"🛑 <b>Отправка остановлена.</b>\nОтправлено: <b>{sent}</b>"
            )
        else:
            await bot.send_message(
                chat_id, f"✅ <b>Готово! Отправлено: {sent}</b>"
            )

        state.stop_requested = False


# --------------------------------------------------------------------------- 
# Точка входа
# --------------------------------------------------------------------------- 
async def main() -> None:
    bot = Bot(token=config.bot_token, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Бот запущен, начинаю polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную (Ctrl+C).")
