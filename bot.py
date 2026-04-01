import telebot
from telebot import types
import json
import os
from datetime import datetime, timedelta
import time
import calendar
import requests
import threading
import pytz
import logging
import shutil
from pathlib import Path

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
BASE_DIR = '/data' if os.path.exists('/data') else '.'
DATA_FILE = os.path.join(BASE_DIR, 'metrics_data.json')
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
METRICS_FILE = os.path.join(BASE_DIR, 'company_metrics.json')
PLANS_FILE = os.path.join(BASE_DIR, 'grade_plans.json')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

TOKEN = '8632435773:AAHjyDl8I447q5NnA-Pq-RiIGemlkHoqyEY'

session = requests.Session()
session.trust_env = True
bot = telebot.TeleBot(TOKEN)
bot.session = session

REGISTRATION_PASSWORD = '903829'
GRADES = [8, 9, 10]
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Временные хранилища
temp_password = {}
temp_name = {}
temp_role = {}
temp_grade = {}
temp_plans = {}

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ДАТАМИ ==========
def get_moscow_now():
    """Возвращает текущее время в Москве с часовым поясом"""
    return datetime.now(MOSCOW_TZ)

def make_naive(dt):
    """Преобразует datetime с часовым поясом в naive (без часового пояса)"""
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

def get_week_number(date):
    """Получает номер недели из naive datetime"""
    naive_date = make_naive(date)
    return naive_date.strftime('%Y-W%W')

def get_quarter(date):
    """Получает квартал из naive datetime"""
    naive_date = make_naive(date)
    quarter = (naive_date.month - 1) // 3 + 1
    return f"{naive_date.year}-Q{quarter}"

def get_quarter_progress(date):
    """Возвращает процент прошедшего времени квартала (0-100)"""
    naive_date = make_naive(date)
    year = naive_date.year
    quarter = (naive_date.month - 1) // 3 + 1
    quarter_start = datetime(year, ((naive_date.month-1)//3)*3 + 1, 1)
    quarter_end = datetime(year, ((naive_date.month-1)//3)*3 + 4, 1) - timedelta(days=1)
    total_days = (quarter_end - quarter_start).days + 1
    days_passed = (naive_date - quarter_start).days + 1
    return (days_passed / total_days) * 100

def get_dynamic_plan(quarterly_plan, progress_percent):
    """Возвращает динамический план на текущий момент"""
    return quarterly_plan * (progress_percent / 100)

# ========== ФУНКЦИИ РАБОТЫ С ДАННЫМИ ==========
def create_backup():
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        for file in [DATA_FILE, USERS_FILE, METRICS_FILE, PLANS_FILE]:
            if os.path.exists(file):
                backup_file = os.path.join(BACKUP_DIR, f"{os.path.basename(file)}_{backup_name}")
                shutil.copy2(file, backup_file)
        backups = sorted(Path(BACKUP_DIR).glob('*.json'))
        for old_backup in backups[:-10]:
            old_backup.unlink()
    except Exception as e:
        logger.error(f"Ошибка бэкапа: {e}")

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {'daily': {}, 'weekly': {}, 'quarterly': {}}

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {'admins': [], 'employees': {}}

def save_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

def load_company_metrics():
    try:
        if os.path.exists(METRICS_FILE):
            with open(METRICS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {'metrics': []}

def save_company_metrics(metrics):
    try:
        with open(METRICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

def load_grade_plans():
    try:
        if os.path.exists(PLANS_FILE):
            with open(PLANS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {8: {}, 9: {}, 10: {}}

def save_grade_plans(plans):
    try:
        with open(PLANS_FILE, 'w', encoding='utf-8') as f:
            json.dump(plans, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

def get_user_grade(user_id):
    users = load_users()
    return users['employees'].get(user_id, {}).get('grade', 8)

def set_user_grade(user_id, grade):
    users = load_users()
    if user_id in users['employees']:
        users['employees'][user_id]['grade'] = grade
        save_users(users)
        return True
    return False

def is_admin(user_id):
    users = load_users()
    return user_id in users['admins']

def get_role_name(role):
    return "Руководитель" if role == 'admin' else "Сотрудник"

def safe_get_text(message):
    if not message:
        return None
    if hasattr(message, 'text') and message.text:
        return message.text.strip()
    if hasattr(message, 'caption') and message.caption:
        return message.caption.strip()
    return None

def notify_all_users(message_text, photo=None, document=None):
    users = load_users()
    sent = 0
    all_users = list(users['employees'].keys()) + users['admins']
    for user_id in set(all_users):
        try:
            if photo:
                bot.send_photo(user_id, photo, caption=message_text)
            elif document:
                bot.send_document(user_id, document, caption=message_text)
            else:
                bot.send_message(user_id, message_text)
            sent += 1
        except:
            pass
    return sent

def update_all_metrics(user_id, daily_values, date=None):
    if date is None:
        date = get_moscow_now()
    
    # Преобразуем в naive для расчетов
    naive_date = make_naive(date)
    data = load_data()
    date_str = naive_date.strftime('%Y-%m-%d')
    week_key = get_week_number(naive_date)
    quarter_key = get_quarter(naive_date)
    
    if user_id not in data['daily']:
        data['daily'][user_id] = {}
    if date_str not in data['daily'][user_id]:
        data['daily'][user_id][date_str] = {}
    for metric, value in daily_values.items():
        data['daily'][user_id][date_str][metric] = value
    
    if user_id not in data['weekly']:
        data['weekly'][user_id] = {}
    if week_key not in data['weekly'][user_id]:
        data['weekly'][user_id][week_key] = {}
    
    week_start = naive_date - timedelta(days=naive_date.weekday())
    for metric in daily_values.keys():
        week_total = 0
        for i in range(7):
            day = week_start + timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            if day_str in data['daily'].get(user_id, {}):
                if metric in data['daily'][user_id][day_str]:
                    week_total += data['daily'][user_id][day_str][metric]
        data['weekly'][user_id][week_key][metric] = week_total
    
    if user_id not in data['quarterly']:
        data['quarterly'][user_id] = {}
    if quarter_key not in data['quarterly'][user_id]:
        data['quarterly'][user_id][quarter_key] = {}
    
    quarter_start = datetime(naive_date.year, ((naive_date.month-1)//3)*3 + 1, 1)
    quarter_end = datetime(naive_date.year, ((naive_date.month-1)//3)*3 + 4, 1) - timedelta(days=1)
    for metric in daily_values.keys():
        quarter_total = 0
        current = quarter_start
        while current <= quarter_end:
            day_str = current.strftime('%Y-%m-%d')
            if day_str in data['daily'].get(user_id, {}):
                if metric in data['daily'][user_id][day_str]:
                    quarter_total += data['daily'][user_id][day_str][metric]
            current += timedelta(days=1)
        data['quarterly'][user_id][quarter_key][metric] = quarter_total
    
    save_data(data)
    create_backup()
    return data

# ========== ЕЖЕДНЕВНОЕ УВЕДОМЛЕНИЕ ==========
def send_daily_notification():
    while True:
        try:
            now = get_moscow_now()
            naive_now = make_naive(now)
            target = naive_now.replace(hour=17, minute=44, second=0, microsecond=0)
            if naive_now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - naive_now).total_seconds()
            time.sleep(wait_seconds)
            notify_all_users("📢 **Проверить Callback**\n\nНе забудьте проверить и заполнить сегодняшние показатели!")
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")
            time.sleep(60)

threading.Thread(target=send_daily_notification, daemon=True).start()

# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
def start(message):
    if not message or not hasattr(message, 'chat'):
        return
    user_id = str(message.from_user.id)
    users = load_users()
    if user_id in users['employees'] or user_id in users['admins']:
        show_main_menu(message)
    else:
        msg = bot.send_message(message.chat.id, "🔐 **Регистрация**\n\nВведите пароль для регистрации:")
        bot.register_next_step_handler(msg, check_password)

def check_password(message):
    if not message or not hasattr(message, 'chat'):
        return
    text = safe_get_text(message)
    if not text:
        bot.send_message(message.chat.id, "❌ Ошибка. Напишите /start")
        return
    user_id = str(message.from_user.id)
    if text.strip() == REGISTRATION_PASSWORD:
        temp_password[user_id] = True
        msg = bot.send_message(message.chat.id, "📝 Введите ваше ФИО (например: Иванов Иван Иванович):")
        bot.register_next_step_handler(msg, get_full_name)
    else:
        bot.send_message(message.chat.id, "❌ Неверный пароль!")

def get_full_name(message):
    if not message or not hasattr(message, 'chat'):
        return
    text = safe_get_text(message)
    if not text:
        bot.send_message(message.chat.id, "❌ Введите ФИО!")
        return
    user_id = str(message.from_user.id)
    full_name = text.strip()
    if len(full_name.split()) < 2:
        msg = bot.send_message(message.chat.id, "❌ Введите полное ФИО (Фамилия Имя Отчество):")
        bot.register_next_step_handler(msg, get_full_name)
        return
    temp_name[user_id] = full_name
    markup = types.InlineKeyboardMarkup(row_width=3)
    for grade in GRADES:
        markup.add(types.InlineKeyboardButton(f"Грейд {grade}", callback_data=f"grade_{grade}"))
    bot.send_message(message.chat.id, "🎯 **Выберите ваш грейд:**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('grade_'))
def select_grade(call):
    user_id = str(call.from_user.id)
    grade = int(call.data.replace('grade_', ''))
    temp_grade[user_id] = grade
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton('👨‍💼 Сотрудник', callback_data='role_employee'))
    markup.add(types.InlineKeyboardButton('👔 Руководитель', callback_data='role_admin'))
    bot.edit_message_text(f"✅ Выбран грейд {grade}\n\nТеперь выберите роль:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('role_'))
def choose_role(call):
    user_id = str(call.from_user.id)
    role = call.data.replace('role_', '')
    temp_role[user_id] = role
    if role == 'admin':
        register_user_final(call.message, user_id)
    else:
        grade = temp_grade.get(user_id, 8)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('✅ Подтвердить', callback_data='confirm_grade'))
        markup.add(types.InlineKeyboardButton('🔄 Изменить грейд', callback_data='change_grade'))
        bot.edit_message_text(f"👤 ФИО: {temp_name.get(user_id, '')}\n🎯 Грейд: {grade}\n👔 Роль: {get_role_name(role)}\n\nПроверьте данные и подтвердите:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'confirm_grade')
def confirm_grade(call):
    register_user_final(call.message, str(call.from_user.id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'change_grade')
def change_grade(call):
    user_id = str(call.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=3)
    for grade in GRADES:
        markup.add(types.InlineKeyboardButton(f"Грейд {grade}", callback_data=f"grade_change_{grade}"))
    bot.edit_message_text("🎯 **Выберите новый грейд:**", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('grade_change_'))
def grade_change(call):
    user_id = str(call.from_user.id)
    grade = int(call.data.replace('grade_change_', ''))
    temp_grade[user_id] = grade
    role = temp_role.get(user_id, 'employee')
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✅ Подтвердить', callback_data='confirm_grade'))
    markup.add(types.InlineKeyboardButton('🔄 Изменить грейд', callback_data='change_grade'))
    bot.edit_message_text(f"👤 ФИО: {temp_name.get(user_id, '')}\n🎯 Грейд: {grade}\n👔 Роль: {get_role_name(role)}\n\nПроверьте данные и подтвердите:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

def register_user_final(message, user_id):
    full_name = temp_name.get(user_id, '')
    username = message.from_user.username or "не указан"
    role = temp_role.get(user_id, 'employee')
    grade = temp_grade.get(user_id, 8)
    users = load_users()
    users['employees'][user_id] = {
        'name': full_name, 'username': username,
        'registered_at': get_moscow_now().strftime('%Y-%m-%d %H:%M:%S'),
        'role': role, 'grade': grade
    }
    if role == 'admin' and user_id not in users['admins']:
        users['admins'].append(user_id)
    save_users(users)
    if role == 'employee':
        notify_all_users(f"🎉 Новый сотрудник!\n👤 {full_name}\n📱 @{username}\n🎯 Грейд: {grade}")
    bot.send_message(message.chat.id, f"✅ Вы зарегистрированы как {get_role_name(role)}!\n👤 {full_name}\n🎯 Грейд: {grade}\n\nНажмите /start")
    for k in [temp_password, temp_name, temp_role, temp_grade]:
        if user_id in k:
            del k[user_id]
    show_main_menu(message)

def show_main_menu(message):
    if not message or not hasattr(message, 'chat'):
        return
    user_id = str(message.from_user.id)
    users = load_users()
    if user_id not in users['employees']:
        return
    role = users['employees'][user_id].get('role', 'employee')
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    if role == 'admin':
        btns = ['📊 Управление показателями', '👥 Список сотрудников', '📋 Отчеты по сотрудникам', 
                '✏️ Редактировать отчеты', '📈 Общий свод', '📊 Свод за день', '📢 Сообщение всем', '🎯 Управление планами']
        for btn in btns:
            markup.add(types.KeyboardButton(btn))
    else:
        btns = ['📝 Внести показатель', '📊 Мои показатели', '📈 Общий свод', '📊 Свод за день']
        for btn in btns:
            markup.add(types.KeyboardButton(btn))
    markup.add(types.KeyboardButton('👤 Мой профиль'), types.KeyboardButton('ℹ️ Помощь'))
    bot.send_message(message.chat.id, f"🏠 Главное меню\n\n👋 Привет, {users['employees'][user_id]['name']}!", reply_markup=markup)

# ========== ПРОФИЛЬ ==========
@bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
def my_profile(message):
    user_id = str(message.from_user.id)
    users = load_users()
    ud = users['employees'].get(user_id, {})
    text = f"👤 Мой профиль\n\n📝 ФИО: {ud.get('name', '-')}\n🎯 Грейд: {ud.get('grade', '-')}\n👔 Роль: {get_role_name(ud.get('role', 'employee'))}\n📱 @{ud.get('username', '-')}\n📅 {ud.get('registered_at', '-')}"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton('✏️ ФИО', callback_data='edit_name'), types.InlineKeyboardButton('🎯 Грейд', callback_data='edit_grade'))
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'edit_name')
def edit_name(call):
    msg = bot.send_message(call.message.chat.id, "📝 Введите новое ФИО:")
    bot.register_next_step_handler(msg, update_name)
    bot.answer_callback_query(call.id)

def update_name(message):
    text = safe_get_text(message)
    if text and len(text.split()) >= 2:
        users = load_users()
        users['employees'][str(message.from_user.id)]['name'] = text.strip()
        save_users(users)
        bot.send_message(message.chat.id, f"✅ ФИО обновлено: {text}")
    else:
        bot.send_message(message.chat.id, "❌ Введите полное ФИО!")
    show_main_menu(message)

@bot.callback_query_handler(func=lambda call: call.data == 'edit_grade')
def edit_grade(call):
    user_id = str(call.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=3)
    for g in GRADES:
        markup.add(types.InlineKeyboardButton(f"Грейд {g}", callback_data=f"set_grade_{g}"))
    bot.edit_message_text("🎯 Выберите новый грейд:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_grade_'))
def set_grade(call):
    user_id = str(call.from_user.id)
    new_grade = int(call.data.replace('set_grade_', ''))
    if set_user_grade(user_id, new_grade):
        bot.edit_message_text(f"✅ Грейд изменен на {new_grade}!", call.message.chat.id, call.message.message_id)
        users = load_users()
        name = users['employees'].get(user_id, {}).get('name', 'Сотрудник')
        for a in users['admins']:
            try:
                bot.send_message(a, f"📝 {name} изменил грейд на {new_grade}")
            except:
                pass
    else:
        bot.edit_message_text("❌ Ошибка", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
    show_main_menu(call.message)

# ========== МОИ ПОКАЗАТЕЛИ ==========
@bot.message_handler(func=lambda message: message.text == '📊 Мои показатели')
def my_metrics(message):
    user_id = str(message.from_user.id)
    data = load_data()
    metrics = load_company_metrics()['metrics']
    plans = load_grade_plans()
    grade = get_user_grade(user_id)
    now = get_moscow_now()
    naive_now = make_naive(now)
    progress = get_quarter_progress(naive_now)
    qkey = get_quarter(naive_now)
    wkey = get_week_number(naive_now)
    today = naive_now.strftime('%Y-%m-%d')
    
    daily = data['daily'].get(user_id, {}).get(today, {})
    weekly = data['weekly'].get(user_id, {}).get(wkey, {})
    quarterly = data['quarterly'].get(user_id, {}).get(qkey, {})
    
    result = f"📊 Ваши показатели на {naive_now.strftime('%d.%m.%Y')}\n🎯 Грейд: {grade}\n📅 Прогресс: {progress:.0f}%\n\n"
    total_plan, total_fact = 0, 0
    for m in metrics:
        qplan = plans.get(grade, {}).get(m, 0)
        dplan = get_dynamic_plan(qplan, progress)
        fq = quarterly.get(m, 0)
        fw = weekly.get(m, 0)
        fd = daily.get(m, 0)
        pct = (fq / dplan * 100) if dplan > 0 else 0
        result += f"{m}: {qplan} - {fq}/{fw}/{fd}  {pct:.0f}%\n"
        total_plan += dplan
        total_fact += fq
    if total_plan > 0:
        result += f"\n📈 Общее выполнение: {(total_fact/total_plan*100):.0f}% от плана"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✏️ Редактировать сегодня', callback_data='edit_today'))
    markup.add(types.InlineKeyboardButton('📅 Другая дата', callback_data='edit_other'))
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, result, reply_markup=markup)

# ========== ВНЕСЕНИЕ ПОКАЗАТЕЛЯ ==========
@bot.message_handler(func=lambda message: message.text == '📝 Внести показатель')
def enter_metric(message):
    metrics = load_company_metrics()['metrics']
    if not metrics:
        bot.send_message(message.chat.id, "📭 Нет показателей")
        return
    template = "📝 Введите значения:\n\n```\n"
    for m in metrics:
        template += f"{m}: \n"
    template += "```\nПример:\n```\n"
    for m in metrics:
        template += f"{m}: 5\n"
    template += "```\nДля другой даты:\n```\n25.03.2024\n"
    for m in metrics:
        template += f"{m}: 10\n"
    template += "```"
    msg = bot.send_message(message.chat.id, template)
    bot.register_next_step_handler(msg, save_metrics)

def save_metrics(message):
    text = safe_get_text(message)
    if not text:
        bot.send_message(message.chat.id, "❌ Ошибка")
        return
    lines = text.split('\n')
    date = None
    try:
        if '.' in lines[0] and len(lines[0]) <= 10:
            date = datetime.strptime(lines[0].strip(), '%d.%m.%Y')
            lines = lines[1:]
    except:
        pass
    metrics = load_company_metrics()['metrics']
    values = {}
    errors = []
    for line in lines:
        line = line.strip()
        if not line or ':' not in line:
            continue
        name, val = line.split(':', 1)
        name = name.strip()
        try:
            val = float(val.strip())
            if name in metrics:
                values[name] = val
            else:
                errors.append(f"{name} - не найден")
        except:
            errors.append(f"{name} - ошибка")
    if not values:
        bot.send_message(message.chat.id, "❌ Нет данных")
        return
    user_id = str(message.from_user.id)
    if date:
        update_all_metrics(user_id, values, date)
        dstr = date.strftime('%d.%m.%Y')
    else:
        update_all_metrics(user_id, values)
        dstr = "сегодня"
    users = load_users()
    name = users['employees'].get(user_id, {}).get('name', 'Сотрудник')
    notify_all_users(f"📊 Отчет!\n👤 {name}\n📅 {dstr}\n" + "\n".join([f"• {k}: {v}" for k, v in values.items()]))
    result = f"✅ Сохранено!\n📅 {dstr}\n\n" + "\n".join([f"• {k}: {v}" for k, v in values.items()])
    if errors:
        result += "\n⚠️ " + "\n".join(errors)
    data = load_data()
    now = get_moscow_now()
    naive_now = make_naive(now)
    qkey = get_quarter(naive_now)
    wkey = get_week_number(naive_now)
    qv = data['quarterly'].get(user_id, {}).get(qkey, {})
    wv = data['weekly'].get(user_id, {}).get(wkey, {})
    result += f"\n\n📈 Накопления:\n"
    for m, v in values.items():
        result += f"• {m}: {qv.get(m,0)} / {wv.get(m,0)} / {v}\n"
    result += "\n(квартал / неделя / день)"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✏️ Редактировать', callback_data='edit_today'))
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, result, reply_markup=markup)

# ========== РЕДАКТИРОВАНИЕ ОТЧЕТА ==========
@bot.callback_query_handler(func=lambda call: call.data == 'edit_today')
def edit_today(call):
    user_id = str(call.from_user.id)
    today = make_naive(get_moscow_now()).strftime('%Y-%m-%d')
    data = load_data()
    metrics = load_company_metrics()['metrics']
    cur = data['daily'].get(user_id, {}).get(today, {})
    msg = bot.send_message(call.message.chat.id, "✏️ Введите новые значения:\n" + "\n".join([f"• {m}: {cur.get(m,0)}" for m in metrics]) + "\n\nФормат: Название: значение")
    bot.register_next_step_handler(msg, lambda m: update_report(m, user_id, None))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'edit_other')
def edit_other(call):
    msg = bot.send_message(call.message.chat.id, "📅 Введите дату (ДД.ММ.ГГГГ):")
    bot.register_next_step_handler(msg, lambda m: get_edit_date(m, call.message))
    bot.answer_callback_query(call.id)

def get_edit_date(message, orig):
    try:
        date = datetime.strptime(message.text.strip(), '%d.%m.%Y')
        user_id = str(message.from_user.id)
        data = load_data()
        metrics = load_company_metrics()['metrics']
        cur = data['daily'].get(user_id, {}).get(date.strftime('%Y-%m-%d'), {})
        msg = bot.send_message(message.chat.id, f"✏️ Редактирование {date.strftime('%d.%m.%Y')}\n" + "\n".join([f"• {m}: {cur.get(m,0)}" for m in metrics]) + "\n\nФормат: Название: значение")
        bot.register_next_step_handler(msg, lambda m: update_report(m, user_id, date))
    except:
        bot.send_message(message.chat.id, "❌ Неверный формат")

def update_report(message, user_id, date):
    text = safe_get_text(message)
    if not text:
        bot.send_message(message.chat.id, "❌ Ошибка")
        return
    metrics = load_company_metrics()['metrics']
    values = {}
    for line in text.split('\n'):
        if ':' in line:
            n, v = line.split(':', 1)
            n = n.strip()
            try:
                v = float(v.strip())
                if n in metrics:
                    values[n] = v
            except:
                pass
    if values:
        update_all_metrics(user_id, values, date)
        bot.send_message(message.chat.id, "✅ Обновлено!")
    else:
        bot.send_message(message.chat.id, "❌ Нет данных")
    my_metrics(message)

# ========== ОБЩИЙ СВОД ==========
@bot.message_handler(func=lambda message: message.text == '📈 Общий свод')
def general_summary(message):
    data = load_data()
    users = load_users()
    metrics = load_company_metrics()['metrics']
    now = get_moscow_now()
    naive_now = make_naive(now)
    qkey = get_quarter(naive_now)
    wkey = get_week_number(naive_now)
    today = naive_now.strftime('%Y-%m-%d')
    res = f"📊 Общий свод\n📅 {naive_now.strftime('%d.%m.%Y')}\n\n"
    for m in metrics:
        d, w, q = 0, 0, 0
        for uid, ud in users['employees'].items():
            if ud.get('role') == 'employee':
                d += data['daily'].get(uid, {}).get(today, {}).get(m, 0)
                w += data['weekly'].get(uid, {}).get(wkey, {}).get(m, 0)
                q += data['quarterly'].get(uid, {}).get(qkey, {}).get(m, 0)
        res += f"{m}: {q} / {w} / {d}\n"
    res += "\n(квартал / неделя / день)"
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu')
    if is_admin(str(message.from_user.id)):
        markup.add(types.InlineKeyboardButton('🗑️ Удалить все', callback_data='delete_all'), btn_back)
    else:
        markup.add(btn_back)
    bot.send_message(message.chat.id, res, reply_markup=markup)

# ========== СВОД ЗА ДЕНЬ ==========
@bot.message_handler(func=lambda message: message.text == '📊 Свод за день')
def daily_summary(message):
    data = load_data()
    users = load_users()
    metrics = load_company_metrics()['metrics']
    now = get_moscow_now()
    naive_now = make_naive(now)
    qkey = get_quarter(naive_now)
    wkey = get_week_number(naive_now)
    today = naive_now.strftime('%Y-%m-%d')
    res = f"📊 Свод за {naive_now.strftime('%d.%m.%Y')}\n\n"
    for m in metrics:
        d, w, q = 0, 0, 0
        for uid, ud in users['employees'].items():
            if ud.get('role') == 'employee':
                d += data['daily'].get(uid, {}).get(today, {}).get(m, 0)
                w += data['weekly'].get(uid, {}).get(wkey, {}).get(m, 0)
                q += data['quarterly'].get(uid, {}).get(qkey, {}).get(m, 0)
        res += f"{m}: {q} / {w} / {d}\n"
    res += "\n(квартал / неделя / день)"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, res, reply_markup=markup)

# ========== УПРАВЛЕНИЕ ПЛАНАМИ ==========
@bot.message_handler(func=lambda message: message.text == '🎯 Управление планами')
def manage_plans(message):
    if not is_admin(str(message.from_user.id)):
        bot.send_message(message.chat.id, "⛔ Нет прав")
        return
    metrics = load_company_metrics()['metrics']
    if not metrics:
        bot.send_message(message.chat.id, "📭 Сначала добавьте показатели")
        return
    markup = types.InlineKeyboardMarkup(row_width=3)
    for g in GRADES:
        markup.add(types.InlineKeyboardButton(f"🎯 Грейд {g}", callback_data=f"plan_grade_{g}"))
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, "📊 Управление планами\nВыберите грейд:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('plan_grade_'))
def plan_grade(call):
    if not is_admin(str(call.from_user.id)):
        bot.answer_callback_query(call.id, "Нет прав")
        return
    grade = int(call.data.replace('plan_grade_', ''))
    metrics = load_company_metrics()['metrics']
    plans = load_grade_plans()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for m in metrics:
        cur = plans.get(grade, {}).get(m, 0)
        markup.add(types.InlineKeyboardButton(f"📊 {m}: {cur}", callback_data=f"set_plan_{grade}_{m}"))
    markup.add(types.InlineKeyboardButton('◀️ Назад', callback_data='back_plans'))
    bot.edit_message_text(f"🎯 Грейд {grade}\nВыберите показатель:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_plan_'))
def set_plan(call):
    if not is_admin(str(call.from_user.id)):
        bot.answer_callback_query(call.id, "Нет прав")
        return
    parts = call.data.split('_')
    grade = int(parts[2])
    metric = parts[3]
    temp_plans[call.from_user.id] = {'grade': grade, 'metric': metric}
    msg = bot.send_message(call.message.chat.id, f"📝 Грейд {grade}, {metric}\nВведите квартальный план (число):")
    bot.register_next_step_handler(msg, save_plan)
    bot.answer_callback_query(call.id)

def save_plan(message):
    text = safe_get_text(message)
    if not text:
        bot.send_message(message.chat.id, "❌ Введите число")
        return
    try:
        plan = int(text.strip())
        if plan < 0:
            raise ValueError
        temp = temp_plans.get(message.from_user.id, {})
        grade = temp.get('grade')
        metric = temp.get('metric')
        if grade and metric:
            plans = load_grade_plans()
            if grade not in plans:
                plans[grade] = {}
            plans[grade][metric] = plan
            save_grade_plans(plans)
            bot.send_message(message.chat.id, f"✅ План для {metric} (гр. {grade}): {plan}")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка")
    except:
        bot.send_message(message.chat.id, "❌ Введите число")
    manage_plans(message)

@bot.callback_query_handler(func=lambda call: call.data == 'back_plans')
def back_plans(call):
    manage_plans(call.message)
    bot.answer_callback_query(call.id)

# ========== УПРАВЛЕНИЕ ПОКАЗАТЕЛЯМИ ==========
@bot.message_handler(func=lambda message: message.text == '📊 Управление показателями')
def manage_metrics(message):
    if not is_admin(str(message.from_user.id)):
        bot.send_message(message.chat.id, "⛔ Нет прав")
        return
    metrics = load_company_metrics()['metrics']
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton('➕ Добавить', callback_data='add_metrics'))
    markup.add(types.InlineKeyboardButton('📋 Список', callback_data='list_metrics'))
    markup.add(types.InlineKeyboardButton('🗑️ Удалить', callback_data='remove_metric'))
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, f"📊 Показатели: {', '.join(metrics) if metrics else 'нет'}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'add_metrics')
def add_metrics_prompt(call):
    msg = bot.send_message(call.message.chat.id, "📝 Введите показатели:\nНазвание: план\nПример:\nВыдачи: 100\nВстречи: 50")
    bot.register_next_step_handler(msg, add_metrics_save)
    bot.answer_callback_query(call.id)

def add_metrics_save(message):
    text = safe_get_text(message)
    if not text:
        bot.send_message(message.chat.id, "❌ Ошибка")
        return
    metrics = load_company_metrics()
    added, errors = [], []
    for line in text.split('\n'):
        if ':' in line:
            name, _ = line.split(':', 1)
            name = name.strip()
            if name and name not in metrics['metrics']:
                metrics['metrics'].append(name)
                added.append(name)
            else:
                errors.append(f"{name} - уже есть")
    if added:
        save_company_metrics(metrics)
        bot.send_message(message.chat.id, f"✅ Добавлено: {', '.join(added)}")
    if errors:
        bot.send_message(message.chat.id, f"⚠️ {', '.join(errors)}")

@bot.callback_query_handler(func=lambda call: call.data == 'list_metrics')
def list_metrics(call):
    metrics = load_company_metrics()['metrics']
    text = "📋 Список:\n" + "\n".join([f"{i+1}. {m}" for i, m in enumerate(metrics)]) if metrics else "📭 Пусто"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'remove_metric')
def remove_metric_prompt(call):
    metrics = load_company_metrics()['metrics']
    if not metrics:
        bot.answer_callback_query(call.id, "Нет показателей")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for m in metrics:
        markup.add(types.InlineKeyboardButton(f"🗑️ {m}", callback_data=f"del_metric_{m}"))
    markup.add(types.InlineKeyboardButton('◀️ Назад', callback_data='back_metrics'))
    bot.edit_message_text("Выберите показатель:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_metric_'))
def del_metric(call):
    metric = call.data.replace('del_metric_', '')
    metrics = load_company_metrics()
    if metric in metrics['metrics']:
        metrics['metrics'].remove(metric)
        save_company_metrics(metrics)
        data = load_data()
        for uid in data['daily']:
            for date in list(data['daily'][uid].keys()):
                if metric in data['daily'][uid][date]:
                    del data['daily'][uid][date][metric]
        for uid in data['weekly']:
            for week in list(data['weekly'][uid].keys()):
                if metric in data['weekly'][uid][week]:
                    del data['weekly'][uid][week][metric]
        for uid in data['quarterly']:
            for q in list(data['quarterly'][uid].keys()):
                if metric in data['quarterly'][uid][q]:
                    del data['quarterly'][uid][q][metric]
        save_data(data)
        bot.edit_message_text(f"✅ Удален: {metric}", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'back_metrics')
def back_metrics(call):
    manage_metrics(call.message)
    bot.answer_callback_query(call.id)

# ========== УДАЛЕНИЕ ВСЕХ РЕЗУЛЬТАТОВ ==========
@bot.callback_query_handler(func=lambda call: call.data == 'delete_all')
def confirm_delete_all(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✅ Да, удалить', callback_data='confirm_delete_all'))
    markup.add(types.InlineKeyboardButton('❌ Отмена', callback_data='back_menu'))
    bot.edit_message_text("⚠️ Удалить ВСЕ показатели? Необратимо!", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'confirm_delete_all')
def delete_all(call):
    create_backup()
    save_data({'daily': {}, 'weekly': {}, 'quarterly': {}})
    notify_all_users("⚠️ Все показатели удалены!")
    bot.edit_message_text("✅ Все удалено", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# ========== ОСТАЛЬНЫЕ АДМИН-ФУНКЦИИ ==========
@bot.message_handler(func=lambda message: message.text == '👥 Список сотрудников')
def list_employees(message):
    if not is_admin(str(message.from_user.id)):
        return
    users = load_users()
    res = "👥 Сотрудники:\n"
    for uid, ud in users['employees'].items():
        if ud.get('role') == 'employee':
            res += f"• {ud['name']} (@{ud['username']}) - грейд {ud.get('grade', '-')}\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, ud in users['employees'].items():
        if ud.get('role') == 'employee':
            markup.add(types.InlineKeyboardButton(f"🗑️ {ud['name']}", callback_data=f"del_emp_{uid}"))
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, res, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_emp_'))
def del_emp(call):
    if not is_admin(str(call.from_user.id)):
        bot.answer_callback_query(call.id, "Нет прав")
        return
    uid = call.data.replace('del_emp_', '')
    users = load_users()
    name = users['employees'].get(uid, {}).get('name', '')
    if uid in users['employees']:
        del users['employees'][uid]
        if uid in users['admins']:
            users['admins'].remove(uid)
        save_users(users)
        data = load_data()
        for k in ['daily', 'weekly', 'quarterly']:
            if uid in data[k]:
                del data[k][uid]
        save_data(data)
        bot.edit_message_text(f"✅ Удален: {name}", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(uid, "⚠️ Ваша учетная запись удалена")
        except:
            pass
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text == '📋 Отчеты по сотрудникам')
def reports_list(message):
    if not is_admin(str(message.from_user.id)):
        return
    users = load_users()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, ud in users['employees'].items():
        if ud.get('role') == 'employee':
            markup.add(types.InlineKeyboardButton(f"📊 {ud['name']}", callback_data=f"report_{uid}"))
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, "Выберите сотрудника:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '✏️ Редактировать отчеты')
def edit_reports_list(message):
    if not is_admin(str(message.from_user.id)):
        return
    users = load_users()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, ud in users['employees'].items():
        if ud.get('role') == 'employee':
            markup.add(types.InlineKeyboardButton(f"✏️ {ud['name']}", callback_data=f"edit_reports_{uid}"))
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, "Выберите сотрудника:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('report_'))
def show_report(call):
    uid = call.data.replace('report_', '')
    users = load_users()
    data = load_data()
    metrics = load_company_metrics()['metrics']
    name = users['employees'].get(uid, {}).get('name', '')
    res = f"📊 Отчет: {name}\n\n"
    for date in sorted(data['daily'].get(uid, {}).keys(), reverse=True)[:10]:
        res += f"📅 {date}\n"
        for m in metrics:
            res += f"  • {m}: {data['daily'][uid][date].get(m, 0)}\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✏️ Редактировать', callback_data=f"edit_reports_{uid}"))
    markup.add(types.InlineKeyboardButton('◀️ Назад', callback_data='back_reports'))
    bot.edit_message_text(res, call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_reports_'))
def edit_reports_list2(call):
    uid = call.data.replace('edit_reports_', '')
    data = load_data()
    dates = sorted(data['daily'].get(uid, {}).keys(), reverse=True)[:10]
    if not dates:
        bot.answer_callback_query(call.id, "Нет данных")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for d in dates:
        markup.add(types.InlineKeyboardButton(f"📅 {d}", callback_data=f"edit_date_{uid}_{d}"))
    markup.add(types.InlineKeyboardButton('◀️ Назад', callback_data='back_reports'))
    bot.edit_message_text("Выберите дату:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_date_'))
def edit_date(call):
    parts = call.data.split('_')
    uid = parts[2]
    date = parts[3]
    metrics = load_company_metrics()['metrics']
    data = load_data()
    cur = data['daily'].get(uid, {}).get(date, {})
    msg = bot.send_message(call.message.chat.id, f"✏️ {date}\nТекущие:\n" + "\n".join([f"{m}: {cur.get(m,0)}" for m in metrics]) + "\n\nВведите новые значения:")
    bot.register_next_step_handler(msg, lambda m: admin_update(m, uid, date))
    bot.answer_callback_query(call.id)

def admin_update(message, uid, date_str):
    text = safe_get_text(message)
    if not text:
        bot.send_message(message.chat.id, "❌ Ошибка")
        return
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
    except:
        date = None
    metrics = load_company_metrics()['metrics']
    values = {}
    for line in text.split('\n'):
        if ':' in line:
            n, v = line.split(':', 1)
            n = n.strip()
            try:
                v = float(v.strip())
                if n in metrics:
                    values[n] = v
            except:
                pass
    if values:
        update_all_metrics(uid, values, date)
        bot.send_message(message.chat.id, "✅ Обновлено")
        try:
            bot.send_message(uid, f"📝 Ваш отчет за {date_str} отредактирован")
        except:
            pass
    else:
        bot.send_message(message.chat.id, "❌ Нет данных")

@bot.callback_query_handler(func=lambda call: call.data == 'back_reports')
def back_reports(call):
    reports_list(call.message)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text == '📢 Сообщение всем')
def broadcast_prompt(message):
    if not is_admin(str(message.from_user.id)):
        return
    msg = bot.send_message(message.chat.id, "📢 Введите сообщение (можно с фото/документом):")
    bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    text = safe_get_text(message)
    photo = message.photo[-1].file_id if message.photo else None
    doc = message.document.file_id if message.document else None
    cnt = notify_all_users(text or "", photo, doc)
    bot.send_message(message.chat.id, f"✅ Отправлено {cnt} пользователям")

@bot.message_handler(func=lambda message: message.text == 'ℹ️ Помощь')
def help_cmd(message):
    help_text = "📚 Помощь\n\nДля сотрудников:\n• 📝 Внести показатель\n• 📊 Мои показатели\n• 📈 Общий свод\n• 📊 Свод за день\n\nДля руководителя:\n• Управление показателями\n• Управление планами\n• Список сотрудников\n• Отчеты/Редактирование\n• Сообщение всем\n\nПароль: 903829\nПервый пользователь - админ"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_menu'))
    bot.send_message(message.chat.id, help_text, reply_markup=markup)

# ========== НАВИГАЦИЯ ==========
@bot.callback_query_handler(func=lambda call: call.data == 'back_menu')
def back_menu(call):
    show_main_menu(call.message)
    bot.answer_callback_query(call.id)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🤖 Бот запускается...")
    print("✅ Готов!")
    print("🔐 Пароль: 903829")
    while True:
        try:
            bot.polling(none_stop=True, timeout=120)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(15)