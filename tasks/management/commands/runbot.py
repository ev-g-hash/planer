import asyncio
import logging
import sys
import os
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Запуск Telegram бота'

    def handle(self, *args, **options):
        from tasks.models import Task
        from aiogram import Bot, Dispatcher, types, F
        from aiogram.filters import CommandStart
        from aiogram.utils.keyboard import ReplyKeyboardMarkup
        from aiogram.fsm.state import State, StatesGroup
        from aiogram.fsm.context import FSMContext
        from asgiref.sync import sync_to_async
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from django.utils import timezone
        from django.utils.timezone import localtime

        BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        CHAT_ID = int(os.environ.get('TELEGRAM_CHAT_ID', '0') or 0)

        if not BOT_TOKEN:
            self.stderr.write("ERROR: TELEGRAM_BOT_TOKEN not set!")
            sys.exit(1)

        self.stdout.write("Starting bot...")

        bot = Bot(token=BOT_TOKEN)
        dp = Dispatcher()
        scheduler = AsyncIOScheduler()

        class CreateTask(StatesGroup):
            title = State()
            description = State()
            due_date = State()

        # === DB Functions ===
        @sync_to_async
        def get_tasks():
            return list(Task.objects.all()[:50])

        @sync_to_async
        def create_task(title, desc, due_date):
            return Task.objects.create(title=title, description=desc, due_date=due_date, status='new')

        @sync_to_async
        def get_pending():
            return list(Task.objects.filter(due_date__isnull=False, status__in=['new', 'in_progress']))

        # === Keyboards ===
        def main_keyboard():
            return ReplyKeyboardMarkup(
                keyboard=[[{"text": "📋 Все задачи"}], [{"text": "➕ Новая задача"}], [{"text": "⏰ Напоминания"}]],
                resize_keyboard=True
            )

        def cancel_keyboard():
            return ReplyKeyboardMarkup(keyboard=[[{"text": "❌ Отмена"}]], resize_keyboard=True)

        def skip_keyboard():
            return ReplyKeyboardMarkup(keyboard=[[{"text": "⏩ Пропустить"}]], resize_keyboard=True)

        # === Handlers ===
        @dp.message(CommandStart())
        async def start(msg: types.Message):
            await msg.answer("👋 Бот запущен!", reply_markup=main_keyboard())

        @dp.message(F.text == "📋 Все задачи")
        async def all_tasks(msg: types.Message):
            tasks = await get_tasks()
            if not tasks:
                await msg.answer("📭 Задач нет!", reply_markup=main_keyboard())
                return
            text = "📋 Все задачи:\n\n"
            for i, t in enumerate(tasks, 1):
                status = "✅" if t.status == "done" else "⏳" if t.status == "in_progress" else "🆕"
                due = f" 📅 {localtime(t.due_date).strftime('%d.%m %H:%M')}" if t.due_date else ""
                text += f"{i}. {status} {t.title}{due}\n"
            await msg.answer(text, reply_markup=main_keyboard())

        @dp.message(F.text == "➕ Новая задача")
        async def new_task(msg: types.Message, state: FSMContext):
            await msg.answer("📝 Название задачи:", reply_markup=cancel_keyboard())
            await state.set_state(CreateTask.title)

        @dp.message(CreateTask.title)
        async def process_title(msg: types.Message, state: FSMContext):
            if msg.text == "❌ Отмена":
                await msg.answer("❌ Отменено", reply_markup=main_keyboard())
                await state.clear()
                return
            await state.update_data(title=msg.text)
            await msg.answer("📝 Описание или ⏩ Пропустить:", reply_markup=skip_keyboard())
            await state.set_state(CreateTask.description)

        @dp.message(CreateTask.description)
        async def process_desc(msg: types.Message, state: FSMContext):
            if msg.text == "❌ Отмена":
                await msg.answer("❌ Отменено", reply_markup=main_keyboard())
                await state.clear()
                return
            desc = "" if msg.text == "⏩ Пропустить" else msg.text
            await state.update_data(description=desc)
            await msg.answer("📅 Срок (ДД.ММ.ГГГГ ЧЧ:ММ) или ⏩ Без срока:", reply_markup=skip_keyboard())
            await state.set_state(CreateTask.due_date)

        @dp.message(CreateTask.due_date)
        async def process_due(msg: types.Message, state: FSMContext):
            if msg.text == "❌ Отмена":
                await msg.answer("❌ Отменено", reply_markup=main_keyboard())
                await state.clear()
                return
            
            due_date = None
            if msg.text != "⏩ Пропустить":
                try:
                    due_date = timezone.make_aware(timezone.datetime.strptime(msg.text, "%d.%m.%Y %H:%M"))
                except ValueError:
                    await msg.answer("❌ Неверный формат! Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
                    return
            
            data = await state.get_data()
            task = await create_task(data['title'], data.get('description', ''), due_date)
            await msg.answer(f"✅ Создано: {task.title}", reply_markup=main_keyboard())
            await state.clear()

        @dp.message(F.text == "⏰ Напоминания")
        async def reminders(msg: types.Message):
            tasks = await get_pending()
            now = timezone.now()
            overdue = [t for t in tasks if t.due_date and now >= t.due_date]
            if overdue:
                text = "⚠️ Просроченные:\n"
                for t in overdue:
                    text += f"• {t.title} (срок: {localtime(t.due_date).strftime('%d.%m %H:%M')})\n"
                await msg.answer(text)
            else:
                await msg.answer("✅ Нет просроченных задач!", reply_markup=main_keyboard())

        @dp.message(F.text == "❌ Отмена")
        async def cancel(msg: types.Message, state: FSMContext):
            await msg.answer("❌ Отменено", reply_markup=main_keyboard())
            await state.clear()

        # === Main ===
        async def main():
            scheduler.add_job(lambda: None, IntervalTrigger(seconds=60))
            scheduler.start()
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)

        self.stdout.write("Bot command ready!")
        asyncio.run(main())