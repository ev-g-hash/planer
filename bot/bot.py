import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from asgiref.sync import sync_to_async
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.utils import timezone
from django.utils.timezone import localtime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загружаем переменные из .env файла
load_dotenv()

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_planner.settings')

import django
django.setup()

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from tasks.models import Task

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
YOUR_CHAT_ID = int(os.environ.get('TELEGRAM_CHAT_ID', '0'))

# Создание бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Планировщик задач
scheduler = AsyncIOScheduler()

# ========== FSM Состояния ==========
class CreateTask(StatesGroup):
    """Создание задачи"""
    title = State()
    description = State()
    due_date = State()


# ========== Асинхронные функции для работы с БД ==========
@sync_to_async
def get_all_tasks():
    """Получить все задачи"""
    return list(Task.objects.all()[:50])


@sync_to_async
def get_task_by_id(task_id):
    """Получить задачу по ID"""
    try:
        return Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return None


@sync_to_async
def delete_task_by_id(task_id):
    """Удалить задачу по ID"""
    try:
        Task.objects.get(id=task_id).delete()
        return True
    except Task.DoesNotExist:
        return False


@sync_to_async
def create_task(title, description, due_date):
    """Создать задачу"""
    return Task.objects.create(
        title=title,
        description=description,
        due_date=due_date,
        status='new'
    )


@sync_to_async
def get_pending_tasks_with_deadline():
    """Получить задачи со статусом new/in_progress"""
    return list(Task.objects.filter(
        due_date__isnull=False,
        status__in=['new', 'in_progress']
    ))


@sync_to_async
def mark_task_overdue(task_id):
    """Пометить задачу как просроченную"""
    try:
        task = Task.objects.get(id=task_id)
        task.status = 'overdue'
        task.save()
        return True
    except Task.DoesNotExist:
        return False


# ========== Проверка дедлайнов ==========
async def check_deadlines():
    """Проверка дедлайнов"""
    try:
        tasks = await get_pending_tasks_with_deadline()
        now = timezone.now()
        
        for task in tasks:
            if task.due_date and now >= task.due_date and task.status not in ['done', 'overdue']:
                description = task.description if task.description else "Нет описания"
                
                due_date_local = localtime(task.due_date)
                due_date_str = due_date_local.strftime('%d.%m.%Y %H:%M')
                
                text = (
                    "⏰ **Дедлайн наступил!** ⏰\n\n"
                    f"📝 **Задача:** {task.title}\n\n"
                    f"📝 **Описание:**\n{description}\n\n"
                    f"📅 **Срок:** {due_date_str}\n\n"
                    "⚠️ Задача просрочена!"
                )
                
                if YOUR_CHAT_ID:
                    try:
                        await bot.send_message(YOUR_CHAT_ID, text, parse_mode="Markdown")
                        logger.info(f"Уведомление: {task.title}")
                        await mark_task_overdue(task.id)
                    except Exception as e:
                        logger.error(f"Ошибка: {e}")
                        
    except Exception as e:
        logger.error(f"Ошибка проверки дедлайнов: {e}")


# ========== Клавиатуры ==========
def get_main_keyboard():
    """Главное меню"""
    keyboard = [
        [{"text": "📋 Все задачи"}],
        [{"text": "➕ Новая задача"}],
        [{"text": "⏰ Напоминания"}],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_cancel_keyboard():
    """Клавиатура отмены"""
    keyboard = [[{"text": "❌ Отмена"}]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_skip_keyboard():
    """Клавиатура пропуска"""
    keyboard = [[{"text": "⏩ Пропустить"}]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_tasks_keyboard(tasks):
    """Inline клавиатура со списком задач для удаления"""
    keyboard = []
    for task in tasks[:10]:  # Максимум 10 кнопок
        keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {task.title[:30]}",
                callback_data=f"delete_task_{task.id}"
            )
        ])
    
    if keyboard:
        keyboard.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ========== Обработчики ==========
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Команда /start"""
    welcome_text = (
        "👋 Привет! Я бот для управления задачами.\n\n"
        "📋 Функции:\n"
        "• Просмотр и удаление задач\n"
        "• Создание задач\n"
        "• Автоматические напоминания о дедлайнах"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    logger.info(f"Пользователь {message.from_user.id} запустил бота")


@dp.message(F.text == "📋 Все задачи")
async def show_all_tasks(message: types.Message):
    """Показать все задачи"""
    tasks = await get_all_tasks()
    
    if not tasks:
        await message.answer("📭 Задач пока нет!", reply_markup=get_main_keyboard())
        return
    
    text = "📋 **Все задачи:**\n\n"
    
    for i, task in enumerate(tasks, 1):
        status_icon = "✅" if task.status == "done" else "⏳" if task.status == "in_progress" else "🆕"
        if task.status == "overdue":
            status_icon = "⚠️"
        
        due_date_str = ""
        if task.due_date:
            due_date_local = localtime(task.due_date)
            due_date_str = f" 📅 {due_date_local.strftime('%d.%m %H:%M')}"
        
        desc_str = ""
        if task.description:
            desc = task.description[:50] + "..." if len(task.description) > 50 else task.description
            desc_str = f"\n   📝 {desc}"
        
        text += f"{i}. {status_icon} *{task.title}*{due_date_str}{desc_str}\n"
    
    # Кнопка удаления внизу
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить задачу", callback_data="go_to_delete")]
    ])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.callback_query(F.data == "go_to_delete")
async def go_to_delete(callback: types.CallbackQuery):
    """Переход к выбору задачи для удаления"""
    tasks = await get_all_tasks()
    
    if not tasks:
        await callback.message.edit_text("📭 Задач нет!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ]))
        return
    
    text = "🗑️ **Выберите задачу для удаления:**\n\n"
    
    for i, task in enumerate(tasks, 1):
        status_icon = "✅" if task.status == "done" else "⏳" if task.status == "in_progress" else "🆕"
        if task.status == "overdue":
            status_icon = "⚠️"
        
        due_date_str = ""
        if task.due_date:
            due_date_local = localtime(task.due_date)
            due_date_str = f" 📅 {due_date_local.strftime('%d.%m %H:%M')}"
        
        text += f"{i}. {status_icon} *{task.title}*{due_date_str}\n"
    
    # Кнопки с номерами - по 5 в ряд
    keyboard = []
    row = []
    for i, task in enumerate(tasks, 1):
        row.append(InlineKeyboardButton(
            text=str(i),
            callback_data=f"delete_{task.id}"
        ))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(F.data.startswith("delete_"))
async def delete_task_callback(callback: types.CallbackQuery):
    """Удаление задачи"""
    task_id = int(callback.data.replace("delete_", ""))
    task = await get_task_by_id(task_id)
    
    if task:
        task_title = task.title
        await delete_task_by_id(task_id)
        await callback.answer(f"✅ Задача '{task_title}' удалена!")
        logger.info(f"Пользователь {callback.from_user.id} удалил задачу: {task_title}")
    else:
        await callback.answer("Задача не найдена!")
    
    # Возвращаемся к списку задач
    await show_all_tasks(callback.message)


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text("🔙 Возврат в меню...")
    await cmd_start(callback.message)


@dp.callback_query(F.data.startswith("delete_task_"))
async def delete_task_callback(callback: types.CallbackQuery):
    """Удаление задачи по кнопке"""
    task_id = int(callback.data.replace("delete_task_", ""))
    task = await get_task_by_id(task_id)
    
    if task:
        await delete_task_by_id(task_id)
        await callback.answer(f"Задача '{task.title}' удалена!")
        await callback.message.edit_text(f"✅ Задача '{task.title}' удалена!")
        logger.info(f"Пользователь {callback.from_user.id} удалил задачу: {task.title}")
    else:
        await callback.answer("Задача не найдена!")
    
    # Обновляем список задач
    await show_all_tasks(callback.message)


@dp.message(F.text == "➕ Новая задача")
async def create_task_start(message: types.Message, state: FSMContext):
    """Начало создания задачи"""
    await message.answer(
        "➕ **Новая задача**\n\n"
        "📝 Введите название задачи:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(CreateTask.title)


@dp.message(CreateTask.title)
async def process_title(message: types.Message, state: FSMContext):
    """Обработка названия"""
    text = message.text
    
    if text == "❌ Отмена":
        await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    await state.update_data(title=text)
    
    await message.answer(
        "📝 **Описание задачи**\n\n"
        "Введите описание или нажмите 'Пропустить':",
        parse_mode="Markdown",
        reply_markup=get_skip_keyboard()
    )
    await state.set_state(CreateTask.description)


@dp.message(CreateTask.description)
async def process_description(message: types.Message, state: FSMContext):
    """Обработка описания"""
    text = message.text
    
    if text == "❌ Отмена":
        await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    if text == "⏩ Пропустить":
        description = ""
    else:
        description = text
    
    await state.update_data(description=description)
    
    await message.answer(
        "📅 **Срок выполнения**\n\n"
        "Формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Например: 25.01.2026 14:30\n\n"
        "⏩ - Без срока",
        parse_mode="Markdown",
        reply_markup=get_skip_keyboard()
    )
    await state.set_state(CreateTask.due_date)


@dp.message(CreateTask.due_date)
async def process_due_date(message: types.Message, state: FSMContext):
    """Обработка срока и создание задачи"""
    text = message.text
    
    if text == "❌ Отмена":
        await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    if text == "⏩ Пропустить":
        due_date = None
    else:
        try:
            due_date = timezone.make_aware(
                timezone.datetime.strptime(text, "%d.%m.%Y %H:%M")
            )
        except ValueError:
            await message.answer(
                "❌ Неверный формат!\n\n"
                "Формат: ДД.ММ.ГГГГ ЧЧ:ММ",
                reply_markup=get_skip_keyboard()
            )
            return
    
    await state.update_data(due_date=due_date)
    
    # Создаём задачу
    data = await state.get_data()
    
    task = await create_task(
        title=data['title'],
        description=data.get('description', ''),
        due_date=data.get('due_date')
    )
    
    due_date_str = ""
    if task.due_date:
        due_date_local = localtime(task.due_date)
        due_date_str = f"\n📅 {due_date_local.strftime('%d.%m.%Y %H:%M')}"
    
    response = (
        f"✅ **Задача создана!**\n\n"
        f"📝 *{task.title}*{due_date_str}"
    )
    
    await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    await state.clear()


@dp.message(F.text == "⏰ Напоминания")
async def show_reminders(message: types.Message):
    """Показать просроченные задачи"""
    tasks = await get_pending_tasks_with_deadline()
    
    now = timezone.now()
    overdue = []
    upcoming = []
    
    for task in tasks:
        if task.due_date:
            if now >= task.due_date:
                overdue.append(task)
            else:
                time_left = task.due_date - now
                if time_left.total_seconds() < 86400:
                    upcoming.append(task)
    
    text = "⏰ **Напоминания:**\n\n"
    
    if overdue:
        text += "⚠️ **Просроченные:**\n"
        for task in overdue:
            desc = task.description[:30] + "..." if task.description and len(task.description) > 30 else (task.description or "")
            due_date_local = localtime(task.due_date)
            text += f"📝 *{task.title}*\n"
            text += f"   📅 {due_date_local.strftime('%d.%m %H:%M')}\n"
            if desc:
                text += f"   📝 {desc}\n"
            text += "\n"
    
    if upcoming:
        text += "⏳ **Скоро (до 24ч):**\n"
        for task in upcoming:
            time_left = task.due_date - now
            hours = int(time_left.total_seconds() // 3600)
            desc = task.description[:30] + "..." if task.description and len(task.description) > 30 else (task.description or "")
            due_date_local = localtime(task.due_date)
            text += f"📝 *{task.title}* - {hours}ч\n"
            text += f"   📅 {due_date_local.strftime('%d.%m %H:%M')}\n"
            if desc:
                text += f"   📝 {desc}\n"
            text += "\n"
    
    if not overdue and not upcoming:
        text += "✅ Нет напоминаний!"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


@dp.message(F.text == "❌ Отмена")
async def cancel(message: types.Message, state: FSMContext):
    """Отмена"""
    await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())
    await state.clear()


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text("🔙 Возврат в меню...")
    await cmd_start(callback.message)


async def main():
    """Запуск бота"""
    try:
        logger.info("🤖 Бот запущен...")
        
        scheduler.add_job(check_deadlines, IntervalTrigger(seconds=60), id='check_deadlines')
        scheduler.start()
        
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())