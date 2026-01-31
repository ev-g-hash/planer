#!/usr/bin/env python
"""
Telegram Bot для управления задачами.
Запускается отдельно от Django, но использует его модели.
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКА ПУТЕЙ ==========
# Определяем корень проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Добавляем путь к site-packages если используется virtualenv
VENV_PATH = os.environ.get('VIRTUAL_ENV', '')
if VENV_PATH:
    site_packages = Path(VENV_PATH) / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
    if site_packages.exists():
        sys.path.insert(0, str(site_packages))

# Проверяем, что Django доступен
try:
    import django
    DJANGO_AVAILABLE = True
except ImportError as e:
    DJANGO_AVAILABLE = False
    logger.error(f"Django не найден: {e}")

# Загружаем переменные окружения
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(".env файл загружен")
    else:
        logger.warning(".env файл не найден")
except ImportError:
    logger.warning("dotenv не установлен, используем системные переменные")

# ========== НАСТРОЙКА DJANGO ==========
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_planner.settings')

if DJANGO_AVAILABLE:
    try:
        django.setup()
        logger.info("Django успешно инициализирован")
    except Exception as e:
        logger.error(f"Ошибка инициализации Django: {e}")
        DJANGO_AVAILABLE = False

# ========== ИМПОРТЫ AIOGRAM И APSCHEDULER ==========
try:
    from aiogram import Bot, Dispatcher, types, F
    from aiogram.filters import CommandStart
    from aiogram.utils.keyboard import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.fsm.context import FSMContext
    from asgiref.sync import sync_to_async
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from django.utils import timezone
    from django.utils.timezone import localtime
    AIOGRAM_AVAILABLE = True
except ImportError as e:
    logger.error(f"Ошибка импорта зависимостей: {e}")
    AIOGRAM_AVAILABLE = False
    sys.exit(1)

# ========== КОНФИГУРАЦИЯ БОТА ==========
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
YOUR_CHAT_ID = int(os.environ.get('TELEGRAM_CHAT_ID', '0') or 0)

if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен! Бот не может запуститься.")
    sys.exit(1)

logger.info(f"Чат ID для уведомлений: {YOUR_CHAT_ID}")

# Создание бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Планировщик задач
scheduler = AsyncIOScheduler()

# ========== ПРОВЕРКА БАЗЫ ДАННЫХ ==========
if DJANGO_AVAILABLE:
    from tasks.models import Task
    
    @sync_to_async
    def check_database():
        """Проверка соединения с БД"""
        try:
            count = Task.objects.count()
            logger.info(f"База данных доступна. Задач в БД: {count}")
            return True
        except Exception as e:
            logger.error(f"Ошибка БД: {e}")
            return False
    
    # ========== АСИНХРОННЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С БД ==========
    @sync_to_async
    def get_all_tasks():
        return list(Task.objects.all()[:50])
    
    @sync_to_async
    def get_task_by_id(task_id):
        try:
            return Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return None
    
    @sync_to_async
    def delete_task_by_id(task_id):
        try:
            Task.objects.get(id=task_id).delete()
            return True
        except Task.DoesNotExist:
            return False
    
    @sync_to_async
    def create_task(title, description, due_date):
        return Task.objects.create(
            title=title,
            description=description,
            due_date=due_date,
            status='new'
        )
    
    @sync_to_async
    def get_pending_tasks_with_deadline():
        return list(Task.objects.filter(
            due_date__isnull=False,
            status__in=['new', 'in_progress']
        ))
    
    @sync_to_async
    def mark_task_overdue(task_id):
        try:
            task = Task.objects.get(id=task_id)
            task.status = 'overdue'
            task.save()
            return True
        except Task.DoesNotExist:
            return False
else:
    logger.error("Django недоступен! Бот не может работать с базой данных.")
    sys.exit(1)

# ========== ПРОВЕРКА ДЕДЛАЙНОВ ==========
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
                    # "⏰ **Дедлайн наступил!** ⏰\n\n"
                    f"📝 **Задача:** {task.title}\n\n"
                    f"📝 **Описание:**\n{description}\n\n"
                    f"📅 **Срок:** {due_date_str}\n\n"
                    "⚠️ Задача наступила!"
                )
                
                if YOUR_CHAT_ID:
                    try:
                        await bot.send_message(YOUR_CHAT_ID, text, parse_mode="Markdown")
                        logger.info(f"Уведомление отправлено: {task.title}")
                        await mark_task_overdue(task.id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки: {e}")
                        
    except Exception as e:
        logger.error(f"Ошибка проверки дедлайнов: {e}")


# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    keyboard = [
        [{"text": "📋 Все задачи"}],
        [{"text": "➕ Новая задача"}],
        [{"text": "⏰ Напоминания"}],
        [{"text": "🌐 Веб-интерфейс"}],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_cancel_keyboard():
    keyboard = [[{"text": "❌ Отмена"}]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_skip_keyboard():
    keyboard = [[{"text": "⏩ Пропустить"}]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ========== FSM СОСТОЯНИЯ ==========
class CreateTask(StatesGroup):
    title = State()
    description = State()
    due_date = State()


# ========== ОБРАБОТЧИКИ ==========
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить задачу", callback_data="go_to_delete")]
    ])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.message(F.text == "🌐 Веб-интерфейс")
async def show_web_interface(message: types.Message):
    """Показать ссылку на веб-интерфейс"""
    web_url = "https://planer-pihtulovevgeny.amvera.io/"
    
    text = (
        f"🌐 **Веб-интерфейс планировщика задач**\n\n"
        f"Перейдите по ссылке для работы через браузер:\n"
        f"🔗 {web_url}\n\n"
        f"💡 В веб-интерфейсе доступны все функции:"
    )
    
    # Inline клавиатура для быстрого перехода
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть планировщик", url=web_url)],
        [InlineKeyboardButton(text="📋 Создать задачу", callback_data="web_create_task")],
        [InlineKeyboardButton(text="📊 Все задачи", callback_data="web_list_tasks")]
    ])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.callback_query(F.data == "web_create_task")
async def web_create_task_callback(callback: types.CallbackQuery):
    """Переход к созданию задачи через веб"""
    web_url = "https://planer-pihtulovevgeny.amvera.io/tasks/create/"
    
    text = (
        "➕ **Создание задачи через веб-интерфейс**\n\n"
        f"🔗 {web_url}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Создать задачу", url=web_url)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.callback_query(F.data == "web_list_tasks")
async def web_list_tasks_callback(callback: types.CallbackQuery):
    """Переход к списку задач через веб"""
    web_url = "https://planer-pihtulovevgeny.amvera.io/tasks/"
    
    text = (
        "📋 **Все задачи через веб-интерфейс**\n\n"
        f"🔗 {web_url}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть список", url=web_url)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)


@dp.callback_query(F.data == "go_to_delete")
async def go_to_delete(callback: types.CallbackQuery):
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
    
    keyboard = []
    row = []
    for i, task in enumerate(tasks, 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"delete_{task.id}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(F.data.startswith("delete_"))
async def delete_task_callback(callback: types.CallbackQuery):
    task_id = int(callback.data.replace("delete_", ""))
    task = await get_task_by_id(task_id)
    
    if task:
        task_title = task.title
        await delete_task_by_id(task_id)
        await callback.answer(f"✅ Задача '{task_title}' удалена!")
        logger.info(f"Пользователь {callback.from_user.id} удалил задачу: {task_title}")
    else:
        await callback.answer("Задача не найдена!")
    
    await show_all_tasks(callback.message)


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("🔙 Возврат в меню...")
    await cmd_start(callback.message)


@dp.message(F.text == "➕ Новая задача")
async def create_task_start(message: types.Message, state: FSMContext):
    await message.answer(
        "➕ **Новая задача**\n\n"
        "📝 Введите название задачи:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(CreateTask.title)


@dp.message(CreateTask.title)
async def process_title(message: types.Message, state: FSMContext):
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
    text = message.text
    
    if text == "❌ Отмена":
        await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    
    description = "" if text == "⏩ Пропустить" else text
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
            await message.answer("❌ Неверный формат!\n\nФормат: ДД.ММ.ГГГГ ЧЧ:ММ", reply_markup=get_skip_keyboard())
            return
    
    await state.update_data(due_date=due_date)
    data = await state.get_data()
    
    task = await create_task(
        title=data['title'],
        description=data.get('description', ''),
        due_date=data.get('due_date')
    )
    
    due_date_str = f"\n📅 {localtime(task.due_date).strftime('%d.%m.%Y %H:%M')}" if task.due_date else ""
    
    response = f"✅ **Задача создана!**\n\n📝 *{task.title}*{due_date_str}"
    
    await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    await state.clear()


@dp.message(F.text == "⏰ Напоминания")
async def show_reminders(message: types.Message):
    tasks = await get_pending_tasks_with_deadline()
    now = timezone.now()
    
    overdue = [t for t in tasks if t.due_date and now >= t.due_date]
    upcoming = [t for t in tasks if t.due_date and now < t.due_date and (t.due_date - now).total_seconds() < 86400]
    
    text = "⏰ **Напоминания:**\n\n"
    
    if overdue:
        text += "⚠️ **Просроченные:**\n"
        for task in overdue:
            desc = (task.description[:30] + "...") if task.description and len(task.description) > 30 else (task.description or "")
            text += f"📝 *{task.title}*\n   📅 {localtime(task.due_date).strftime('%d.%m %H:%M')}\n"
            if desc:
                text += f"   📝 {desc}\n\n"
    
    if upcoming:
        text += "⏳ **Скоро (до 24ч):**\n"
        for task in upcoming:
            hours = int((task.due_date - now).total_seconds() // 3600)
            desc = (task.description[:30] + "...") if task.description and len(task.description) > 30 else (task.description or "")
            text += f"📝 *{task.title}* - {hours}ч\n   📅 {localtime(task.due_date).strftime('%d.%m %H:%M')}\n"
            if desc:
                text += f"   📝 {desc}\n\n"
    
    if not overdue and not upcoming:
        text += "✅ Нет напоминаний!"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


@dp.message(F.text == "❌ Отмена")
async def cancel(message: types.Message, state: FSMContext):
    await message.answer("❌ Отменено.", reply_markup=get_main_keyboard())
    await state.clear()


# ========== ЗАПУСК ==========
async def main():
    """Запуск бота"""
    try:
        logger.info("🤖 Бот запускается...")
        
        # Проверяем БД
        db_ok = await check_database()
        if not db_ok:
            logger.error("Не удалось подключиться к базе данных!")
        
        # Запускаем планировщик
        scheduler.add_job(check_deadlines, IntervalTrigger(seconds=60), id='check_deadlines')
        scheduler.start()
        logger.info("📅 Планировщик дедлайнов запущен")
        
        # Запускаем поллинг
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())