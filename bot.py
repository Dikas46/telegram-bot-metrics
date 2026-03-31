import telebot
from telebot import types
import json
import os
from datetime import datetime, timedelta
import time
import calendar
import requests

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = '8632435773:AAHjyDl8I447q5NnA-Pq-RiIGemlkHoqyEY'

# Настройка прокси
session = requests.Session()
session.trust_env = True

bot = telebot.TeleBot(TOKEN)
bot.session = session

# Файлы для хранения данных
DATA_FILE = 'metrics_data.json'
USERS_FILE = 'users.json'
METRICS_FILE = 'company_metrics.json'

# ========== ФУНКЦИИ РАБОТЫ С ДАННЫМИ ==========
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'daily': {}, 'weekly': {}, 'quarterly': {}}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'admins': [], 'employees': {}}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_company_metrics():
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'metrics': []}

def save_company_metrics(metrics):
    with open(METRICS_FILE, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_week_number(date):
    return date.strftime('%Y-W%W')

def get_quarter(date):
    quarter = (date.month - 1) // 3 + 1
    return f"{date.year}-Q{quarter}"

def update_all_metrics(user_id, daily_values, date=None):
    if date is None:
        date = datetime.now()
    
    data = load_data()
    date_str = date.strftime('%Y-%m-%d')
    week_key = get_week_number(date)
    quarter_key = get_quarter(date)
    
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
    
    week_start = date - timedelta(days=date.weekday())
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
    
    quarter_start = datetime(date.year, ((date.month-1)//3)*3 + 1, 1)
    quarter_end = datetime(date.year, ((date.month-1)//3)*3 + 4, 1) - timedelta(days=1)
    
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
    return data

def notify_all_users(message_text):
    users = load_users()
    for user_id in users['employees']:
        try:
            bot.send_message(user_id, message_text)
        except:
            pass

def is_admin(user_id):
    users = load_users()
    return user_id in users['admins']

def get_role_name(role):
    return "Руководитель" if role == 'admin' else "Сотрудник"

# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    users = load_users()
    
    # Если пользователь уже зарегистрирован
    if user_id in users['employees']:
        show_main_menu(message)
        return
    
    # Если это первый пользователь - делаем его админом
    if len(users['employees']) == 0:
        users['employees'][user_id] = {
            'name': '',
            'username': message.from_user.username or "не указан",
            'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'role': 'admin'
        }
        users['admins'].append(user_id)
        save_users(users)
        
        msg = bot.send_message(
            message.chat.id,
            "👑 Вы первый пользователь!\n\nВведите ваше ФИО (например: Иванов Иван Иванович):"
        )
        bot.register_next_step_handler(msg, set_first_admin_name)
        return
    
    # Обычная регистрация
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_employee = types.InlineKeyboardButton('👨‍💼 Сотрудник', callback_data='role_employee')
    btn_admin = types.InlineKeyboardButton('👔 Руководитель', callback_data='role_admin')
    markup.add(btn_employee, btn_admin)
    
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать!\n\nВыберите вашу роль:",
        reply_markup=markup
    )

def set_first_admin_name(message):
    user_id = str(message.from_user.id)
    full_name = message.text.strip()
    
    if len(full_name.split()) < 2:
        msg = bot.send_message(
            message.chat.id,
            "❌ Введите полное ФИО (Фамилия Имя Отчество):"
        )
        bot.register_next_step_handler(msg, set_first_admin_name)
        return
    
    users = load_users()
    if user_id in users['employees']:
        users['employees'][user_id]['name'] = full_name
        save_users(users)
    
    bot.send_message(
        message.chat.id,
        f"✅ Вы зарегистрированы как Руководитель!\n\n👤 ФИО: {full_name}\n\nНажмите /start для начала работы."
    )
    show_main_menu(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith('role_'))
def choose_role(call):
    user_id = str(call.from_user.id)
    role = call.data.replace('role_', '')
    
    msg = bot.send_message(
        call.message.chat.id,
        "📝 Введите ваше ФИО (например: Иванов Иван Иванович):"
    )
    bot.register_next_step_handler(msg, lambda m: register_user(m, role))
    bot.answer_callback_query(call.id)

def register_user(message, role):
    user_id = str(message.from_user.id)
    full_name = message.text.strip()
    username = message.from_user.username or "не указан"
    
    if len(full_name.split()) < 2:
        msg = bot.send_message(
            message.chat.id,
            "❌ Пожалуйста, введите полное ФИО (Фамилия Имя Отчество):"
        )
        bot.register_next_step_handler(msg, lambda m: register_user(m, role))
        return
    
    users = load_users()
    
    users['employees'][user_id] = {
        'name': full_name,
        'username': username,
        'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'role': role
    }
    
    if role == 'admin':
        users['admins'].append(user_id)
    
    save_users(users)
    
    if role == 'employee':
        notify_message = f"🎉 Новый сотрудник!\n\n👤 {full_name}\n📱 @{username}\n✅ Присоединился к системе!"
        notify_all_users(notify_message)
    
    welcome_msg = f"✅ Вы успешно зарегистрированы как {get_role_name(role)}!\n\n"
    welcome_msg += f"👤 ФИО: {full_name}\n"
    welcome_msg += f"📱 Username: @{username}\n\n"
    
    if role == 'admin':
        welcome_msg += f"🔧 Вам доступны функции администратора.\n\n"
    
    welcome_msg += f"Нажмите /start для начала работы."
    
    bot.send_message(message.chat.id, welcome_msg)
    show_main_menu(message)

def show_main_menu(message):
    user_id = str(message.from_user.id)
    users = load_users()
    user_role = users['employees'].get(user_id, {}).get('role', 'employee')
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    if user_role == 'admin':
        btn1 = types.KeyboardButton('📊 Управление показателями')
        btn2 = types.KeyboardButton('👥 Список сотрудников')
        btn3 = types.KeyboardButton('📋 Отчеты по сотрудникам')
        btn4 = types.KeyboardButton('✏️ Редактировать отчеты')
        btn5 = types.KeyboardButton('📈 Общий свод')
        btn6 = types.KeyboardButton('📊 Свод за день')
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    else:
        btn1 = types.KeyboardButton('📝 Внести показатель')
        btn2 = types.KeyboardButton('📊 Мои показатели')
        btn3 = types.KeyboardButton('📈 Общий свод')
        btn4 = types.KeyboardButton('📊 Свод за день')
        markup.add(btn1, btn2, btn3, btn4)
    
    markup.add(types.KeyboardButton('👤 Мой профиль'))
    markup.add(types.KeyboardButton('ℹ️ Помощь'))
    
    bot.send_message(
        message.chat.id,
        f"🏠 Главное меню\n\n👋 Привет, {users['employees'][user_id]['name']}!",
        reply_markup=markup
    )

# ========== ПРОФИЛЬ ==========
@bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
def my_profile(message):
    user_id = str(message.from_user.id)
    users = load_users()
    user_data = users['employees'].get(user_id, {})
    
    profile_text = f"👤 Мой профиль\n\n"
    profile_text += f"📝 ФИО: {user_data.get('name', 'не указано')}\n"
    profile_text += f"👔 Роль: {get_role_name(user_data.get('role', 'employee'))}\n"
    profile_text += f"📱 Username: @{user_data.get('username', 'не указан')}\n"
    profile_text += f"📅 Дата регистрации: {user_data.get('registered_at', 'неизвестно')}\n"
    
    markup = types.InlineKeyboardMarkup()
    btn_edit = types.InlineKeyboardButton('✏️ Редактировать ФИО', callback_data='edit_profile_name')
    markup.add(btn_edit)
    
    bot.send_message(
        message.chat.id,
        profile_text,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == 'edit_profile_name')
def edit_profile_name(call):
    msg = bot.send_message(
        call.message.chat.id,
        "📝 Введите новое ФИО (Фамилия Имя Отчество):"
    )
    bot.register_next_step_handler(msg, update_profile_name)
    bot.answer_callback_query(call.id)

def update_profile_name(message):
    user_id = str(message.from_user.id)
    new_name = message.text.strip()
    
    if len(new_name.split()) < 2:
        bot.send_message(message.chat.id, "❌ Введите полное ФИО!")
        return
    
    users = load_users()
    users['employees'][user_id]['name'] = new_name
    save_users(users)
    
    bot.send_message(message.chat.id, f"✅ ФИО успешно обновлено!\nНовое имя: {new_name}")
    show_main_menu(message)

# ========== ВНЕСЕНИЕ ПОКАЗАТЕЛЯ ==========
@bot.message_handler(func=lambda message: message.text == '📝 Внести показатель')
def enter_daily_metric(message):
    company_metrics = load_company_metrics()
    
    if not company_metrics['metrics']:
        bot.send_message(
            message.chat.id,
            "📭 Показатели еще не настроены администратором.\nДождитесь настройки."
        )
        return
    
    template = "📝 Внесение показателей\n\n"
    template += "Скопируйте список ниже, впишите значения и отправьте:\n\n"
    
    for metric in company_metrics['metrics']:
        template += f"{metric}: \n"
    
    template += "\nПример:\n"
    for metric in company_metrics['metrics']:
        template += f"{metric}: 5\n"
    
    template += "\n📌 Можно ввести показатели за другой день в формате:\n"
    template += "25.03.2024\n"
    for metric in company_metrics['metrics']:
        template += f"{metric}: 10\n"
    
    msg = bot.send_message(message.chat.id, template)
    bot.register_next_step_handler(msg, save_daily_metrics)

def save_daily_metrics(message):
    user_id = str(message.from_user.id)
    company_metrics = load_company_metrics()
    users = load_users()
    text = message.text.strip()
    lines = text.split('\n')
    
    date = None
    first_line = lines[0].strip()
    try:
        if '.' in first_line and len(first_line) <= 10:
            date = datetime.strptime(first_line, '%d.%m.%Y')
            lines = lines[1:]
    except:
        pass
    
    daily_values = {}
    errors = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if ':' in line:
            name, value = line.split(':', 1)
            name = name.strip()
            try:
                value = float(value.strip())
                if name in company_metrics['metrics']:
                    daily_values[name] = value
                else:
                    errors.append(f"{name} - показатель не найден")
            except:
                errors.append(f"{name} - неверное значение")
        else:
            if line.strip():
                errors.append(f"{line} - неверный формат")
    
    if not daily_values:
        bot.send_message(message.chat.id, "❌ Не удалось обработать ни одного показателя.")
        return
    
    # Сохраняем показатели
    if date:
        update_all_metrics(user_id, daily_values, date)
        date_str = date.strftime('%d.%m.%Y')
    else:
        update_all_metrics(user_id, daily_values)
        date_str = "сегодня"
    
    # Получаем имя сотрудника
    employee_name = users['employees'].get(user_id, {}).get('name', 'Сотрудник')
    
    # Формируем сообщение для уведомления
    notify_text = f"📊 **Отчет сдан!**\n\n"
    notify_text += f"👤 **Сотрудник:** {employee_name}\n"
    notify_text += f"📅 **Дата:** {date_str}\n\n"
    notify_text += f"📈 **Показатели:**\n"
    for name, value in daily_values.items():
        notify_text += f"• {name}: {value}\n"
    
    # Отправляем уведомление всем пользователям
    notify_all_users(notify_text)
    
    # Результат для сотрудника
    result = f"✅ Показатели сохранены!\n📅 Дата: {date_str}\n\n"
    for name, value in daily_values.items():
        result += f"• {name}: {value}\n"
    
    if errors:
        result += f"\n⚠️ Ошибки:\n"
        for e in errors:
            result += f"• {e}\n"
    
    data = load_data()
    now = datetime.now()
    week_key = get_week_number(now)
    quarter_key = get_quarter(now)
    
    result += f"\n📈 Текущие накопления:\n"
    for name, value in daily_values.items():
        weekly = data['weekly'].get(user_id, {}).get(week_key, {}).get(name, 0)
        quarterly = data['quarterly'].get(user_id, {}).get(quarter_key, {}).get(name, 0)
        result += f"• {name}: {quarterly} / {weekly} / {value}\n"
    
    result += f"\n(квартал / неделя / день)"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✏️ Редактировать сегодняшний отчет', callback_data='edit_today_report'))
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu'))
    
    bot.send_message(message.chat.id, result, reply_markup=markup)
# ========== МОИ ПОКАЗАТЕЛИ ==========
@bot.message_handler(func=lambda message: message.text == '📊 Мои показатели')
def my_metrics(message):
    user_id = str(message.from_user.id)
    data = load_data()
    company_metrics = load_company_metrics()
    now = datetime.now()
    
    today_str = now.strftime('%Y-%m-%d')
    week_key = get_week_number(now)
    quarter_key = get_quarter(now)
    
    result = f"📊 Ваши показатели на {now.strftime('%d.%m.%Y')}\n\n"
    
    daily = data['daily'].get(user_id, {}).get(today_str, {})
    weekly = data['weekly'].get(user_id, {}).get(week_key, {})
    quarterly = data['quarterly'].get(user_id, {}).get(quarter_key, {})
    
    for metric in company_metrics['metrics']:
        daily_val = daily.get(metric, 0)
        weekly_val = weekly.get(metric, 0)
        quarterly_val = quarterly.get(metric, 0)
        result += f"{metric}: {quarterly_val} / {weekly_val} / {daily_val}\n"
    
    result += f"\n(квартал / неделя / день)"
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_edit_today = types.InlineKeyboardButton('✏️ Редактировать сегодняшний отчет', callback_data='edit_today_report')
    btn_edit_history = types.InlineKeyboardButton('📅 Редактировать за другую дату', callback_data='edit_history_report')
    btn_back = types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu')
    markup.add(btn_edit_today, btn_edit_history, btn_back)
    
    bot.send_message(
        message.chat.id,
        result,
        reply_markup=markup
    )

# ========== РЕДАКТИРОВАНИЕ ОТЧЕТОВ ==========
@bot.callback_query_handler(func=lambda call: call.data == 'edit_today_report')
def edit_today_report(call):
    user_id = str(call.from_user.id)
    data = load_data()
    company_metrics = load_company_metrics()
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    current_values = data['daily'].get(user_id, {}).get(today_str, {})
    
    template = "✏️ Редактирование отчета за сегодня\n\n"
    template += "Введите новые показатели в формате:\n"
    template += "Название: значение\n\n"
    template += "Текущие значения:\n"
    
    for metric in company_metrics['metrics']:
        current = current_values.get(metric, 0)
        template += f"• {metric}: {current}\n"
    
    template += "\nВведите новые значения (каждый с новой строки):"
    
    msg = bot.send_message(call.message.chat.id, template)
    bot.register_next_step_handler(msg, lambda m: update_today_report(m, user_id))
    bot.answer_callback_query(call.id)

def update_today_report(message, user_id):
    company_metrics = load_company_metrics()
    text = message.text.strip()
    lines = text.split('\n')
    
    new_values = {}
    errors = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if ':' in line:
            name, value = line.split(':', 1)
            name = name.strip()
            try:
                value = float(value.strip())
                if name in company_metrics['metrics']:
                    new_values[name] = value
                else:
                    errors.append(f"{name} - показатель не найден")
            except:
                errors.append(f"{name} - неверное значение")
    
    if new_values:
        update_all_metrics(user_id, new_values)
        bot.send_message(message.chat.id, "✅ Отчет за сегодня успешно обновлен!")
        
        data = load_data()
        now = datetime.now()
        week_key = get_week_number(now)
        quarter_key = get_quarter(now)
        
        result = f"\n📈 Текущие накопления:\n"
        for name, value in new_values.items():
            weekly = data['weekly'].get(user_id, {}).get(week_key, {}).get(name, 0)
            quarterly = data['quarterly'].get(user_id, {}).get(quarter_key, {}).get(name, 0)
            result += f"• {name}: {quarterly} / {weekly} / {value}\n"
        result += f"\n(квартал / неделя / день)"
        bot.send_message(message.chat.id, result)
    
    if errors:
        bot.send_message(message.chat.id, f"⚠️ Ошибки:\n" + "\n".join(errors))
    
    my_metrics(message)

@bot.callback_query_handler(func=lambda call: call.data == 'edit_history_report')
def edit_history_report(call):
    msg = bot.send_message(
        call.message.chat.id,
        "📅 Введите дату в формате ДД.ММ.ГГГГ\n\nНапример: 25.03.2024"
    )
    bot.register_next_step_handler(msg, lambda m: select_date_for_edit(m, call.message))
    bot.answer_callback_query(call.id)

def select_date_for_edit(message, original_message):
    try:
        date = datetime.strptime(message.text.strip(), '%d.%m.%Y')
        user_id = str(message.from_user.id)
        data = load_data()
        company_metrics = load_company_metrics()
        date_str = date.strftime('%Y-%m-%d')
        
        current_values = data['daily'].get(user_id, {}).get(date_str, {})
        
        template = f"✏️ Редактирование отчета за {date.strftime('%d.%m.%Y')}\n\n"
        template += "Введите новые показатели в формате:\n"
        template += "Название: значение\n\n"
        template += "Текущие значения:\n"
        
        for metric in company_metrics['metrics']:
            current = current_values.get(metric, 0)
            template += f"• {metric}: {current}\n"
        
        template += "\nВведите новые значения (каждый с новой строки):"
        
        msg = bot.send_message(message.chat.id, template)
        bot.register_next_step_handler(msg, lambda m: update_history_report(m, user_id, date))
        
    except:
        bot.send_message(message.chat.id, "❌ Неверный формат даты! Используйте ДД.ММ.ГГГГ")

def update_history_report(message, user_id, date):
    company_metrics = load_company_metrics()
    text = message.text.strip()
    lines = text.split('\n')
    
    new_values = {}
    errors = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if ':' in line:
            name, value = line.split(':', 1)
            name = name.strip()
            try:
                value = float(value.strip())
                if name in company_metrics['metrics']:
                    new_values[name] = value
                else:
                    errors.append(f"{name} - показатель не найден")
            except:
                errors.append(f"{name} - неверное значение")
    
    if new_values:
        update_all_metrics(user_id, new_values, date)
        bot.send_message(message.chat.id, f"✅ Отчет за {date.strftime('%d.%m.%Y')} успешно обновлен!")
        
        data = load_data()
        now = datetime.now()
        week_key = get_week_number(now)
        quarter_key = get_quarter(now)
        
        result = f"\n📈 Текущие накопления:\n"
        for name, value in new_values.items():
            weekly = data['weekly'].get(user_id, {}).get(week_key, {}).get(name, 0)
            quarterly = data['quarterly'].get(user_id, {}).get(quarter_key, {}).get(name, 0)
            result += f"• {name}: {quarterly} / {weekly} / {value}\n"
        result += f"\n(квартал / неделя / день)"
        bot.send_message(message.chat.id, result)
    
    if errors:
        bot.send_message(message.chat.id, f"⚠️ Ошибки:\n" + "\n".join(errors))
    
    my_metrics(message)

# ========== ОБЩИЙ СВОД ==========
@bot.message_handler(func=lambda message: message.text == '📈 Общий свод')
def general_summary(message):
    data = load_data()
    users = load_users()
    company_metrics = load_company_metrics()
    now = datetime.now()
    
    today_str = now.strftime('%Y-%m-%d')
    week_key = get_week_number(now)
    quarter_key = get_quarter(now)
    
    result = f"📊 Общий свод по компании\n"
    result += f"📅 {now.strftime('%d.%m.%Y')}\n\n"
    
    for metric in company_metrics['metrics']:
        daily_total = 0
        weekly_total = 0
        quarterly_total = 0
        
        for emp_id, emp_data in users['employees'].items():
            if emp_data.get('role') == 'employee':
                daily_total += data['daily'].get(emp_id, {}).get(today_str, {}).get(metric, 0)
                weekly_total += data['weekly'].get(emp_id, {}).get(week_key, {}).get(metric, 0)
                quarterly_total += data['quarterly'].get(emp_id, {}).get(quarter_key, {}).get(metric, 0)
        
        result += f"{metric}: {quarterly_total} / {weekly_total} / {daily_total}\n"
    
    result += f"\n(квартал / неделя / день)"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu'))
    
    bot.send_message(
        message.chat.id,
        result,
        reply_markup=markup
    )

# ========== СВОД ЗА ДЕНЬ ==========
@bot.message_handler(func=lambda message: message.text == '📊 Свод за день')
def daily_summary(message):
    data = load_data()
    users = load_users()
    company_metrics = load_company_metrics()
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    
    result = f"📊 Свод за сегодня: {now.strftime('%d.%m.%Y')}\n\n"
    
    for metric in company_metrics['metrics']:
        daily_total = 0
        
        for emp_id, emp_data in users['employees'].items():
            if emp_data.get('role') == 'employee':
                daily_total += data['daily'].get(emp_id, {}).get(today_str, {}).get(metric, 0)
        
        result += f"{metric}: {daily_total}\n"
    
    result += f"\n(только за сегодня)"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu'))
    
    bot.send_message(
        message.chat.id,
        result,
        reply_markup=markup
    )

# ========== АДМИНСКИЕ ФУНКЦИИ ==========
@bot.message_handler(func=lambda message: message.text == '📊 Управление показателями')
def manage_company_metrics(message):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "⛔ У вас нет прав администратора")
        return
    
    company_metrics = load_company_metrics()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_add = types.InlineKeyboardButton('➕ Добавить показатели', callback_data='add_metrics_batch')
    btn_list = types.InlineKeyboardButton('📋 Список показателей', callback_data='list_metrics')
    btn_remove = types.InlineKeyboardButton('🗑️ Удалить показатель', callback_data='remove_metric')
    btn_back = types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu')
    markup.add(btn_add, btn_list, btn_remove, btn_back)
    
    current_metrics = ", ".join(company_metrics['metrics']) if company_metrics['metrics'] else "нет"
    
    bot.send_message(
        message.chat.id,
        f"📊 Управление показателями компании\n\n"
        f"📋 Текущие показатели: {current_metrics}\n\n"
        f"Выберите действие:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == 'add_metrics_batch')
def add_metrics_batch_prompt(call):
    if not is_admin(str(call.from_user.id)):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "📝 Добавление показателей\n\n"
        "Введите показатели в формате:\n"
        "Название: план\n\n"
        "Пример:\n"
        "Выдачи: 100\n"
        "Встречи: 50\n\n"
        "Каждый показатель с новой строки."
    )
    bot.register_next_step_handler(msg, save_metrics_batch)
    bot.answer_callback_query(call.id)

def save_metrics_batch(message):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "⛔ Нет прав")
        return
    
    company_metrics = load_company_metrics()
    added = []
    errors = []
    
    lines = message.text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        try:
            if ':' in line:
                name, plan = line.split(':', 1)
                name = name.strip()
                plan = int(plan.strip())
                
                if name in company_metrics['metrics']:
                    errors.append(f"{name} - уже существует")
                else:
                    company_metrics['metrics'].append(name)
                    added.append(f"{name}")
            else:
                errors.append(f"{line} - неверный формат")
        except:
            errors.append(f"{line} - ошибка обработки")
    
    save_company_metrics(company_metrics)
    
    result = "✅ Результат добавления:\n\n"
    if added:
        result += f"Добавлено:\n"
        for a in added:
            result += f"• {a}\n"
    if errors:
        result += f"\nОшибки:\n"
        for e in errors:
            result += f"• {e}\n"
    
    bot.send_message(message.chat.id, result)

@bot.callback_query_handler(func=lambda call: call.data == 'list_metrics')
def list_metrics_admin(call):
    if not is_admin(str(call.from_user.id)):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    company_metrics = load_company_metrics()
    
    if not company_metrics['metrics']:
        text = "📭 Показатели не добавлены"
    else:
        text = "📋 Список показателей:\n\n"
        for i, metric in enumerate(company_metrics['metrics'], 1):
            text += f"{i}. {metric}\n"
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'remove_metric')
def remove_metric_prompt(call):
    if not is_admin(str(call.from_user.id)):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    company_metrics = load_company_metrics()
    
    if not company_metrics['metrics']:
        bot.answer_callback_query(call.id, "📭 Нет показателей для удаления")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for metric in company_metrics['metrics']:
        btn = types.InlineKeyboardButton(f"🗑️ {metric}", callback_data=f"removemetric_{metric}")
        markup.add(btn)
    
    btn_back = types.InlineKeyboardButton('◀️ Назад', callback_data='backtometrics')
    markup.add(btn_back)
    
    bot.edit_message_text(
        "🗑️ Выберите показатель для удаления:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('removemetric_'))
def remove_metric_confirm(call):
    if not is_admin(str(call.from_user.id)):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    metric_name = call.data.replace('removemetric_', '')
    
    markup = types.InlineKeyboardMarkup()
    btn_confirm = types.InlineKeyboardButton('✅ Да, удалить', callback_data=f'confirmremove_{metric_name}')
    btn_cancel = types.InlineKeyboardButton('❌ Отмена', callback_data='backtometrics')
    markup.add(btn_confirm, btn_cancel)
    
    bot.edit_message_text(
        f"⚠️ Вы уверены, что хотите удалить показатель '{metric_name}'?\n\n"
        f"ВНИМАНИЕ: Все данные по этому показателю будут потеряны!",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirmremove_'))
def remove_metric_execute(call):
    if not is_admin(str(call.from_user.id)):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    metric_name = call.data.replace('confirmremove_', '')
    
    company_metrics = load_company_metrics()
    if metric_name in company_metrics['metrics']:
        company_metrics['metrics'].remove(metric_name)
        save_company_metrics(company_metrics)
    
    data = load_data()
    
    for user_id in data['daily']:
        for date in list(data['daily'][user_id].keys()):
            if metric_name in data['daily'][user_id][date]:
                del data['daily'][user_id][date][metric_name]
    
    for user_id in data['weekly']:
        for week in list(data['weekly'][user_id].keys()):
            if metric_name in data['weekly'][user_id][week]:
                del data['weekly'][user_id][week][metric_name]
    
    for user_id in data['quarterly']:
        for quarter in list(data['quarterly'][user_id].keys()):
            if metric_name in data['quarterly'][user_id][quarter]:
                del data['quarterly'][user_id][quarter][metric_name]
    
    save_data(data)
    
    bot.edit_message_text(
        f"✅ Показатель '{metric_name}' успешно удален!",
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'backtometrics')
def back_to_metrics(call):
    manage_company_metrics(call.message)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text == '👥 Список сотрудников')
def list_employees_admin(message):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "⛔ Нет прав")
        return
    
    users = load_users()
    
    result = "👥 Список сотрудников\n\n"
    
    employees = []
    admins = []
    
    # Собираем данные с user_id
    for emp_id, emp_data in users['employees'].items():
        emp_data_with_id = {
            'user_id': emp_id,
            'name': emp_data['name'],
            'username': emp_data['username'],
            'role': emp_data.get('role', 'employee')
        }
        if emp_data.get('role') == 'admin':
            admins.append(emp_data_with_id)
        else:
            employees.append(emp_data_with_id)
    
    if admins:
        result += "Руководители:\n"
        for admin in admins:
            result += f"• {admin['name']} (@{admin['username']})\n"
        result += "\n"
    
    if employees:
        result += "Сотрудники:\n"
        for emp in employees:
            result += f"• {emp['name']} (@{emp['username']})\n"
    
    # Кнопки для удаления
    if employees:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for emp in employees:
            btn = types.InlineKeyboardButton(f"🗑️ {emp['name']}", callback_data=f"delete_emp_{emp['user_id']}")
            markup.add(btn)
        btn_back = types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu')
        markup.add(btn_back)
        
        bot.send_message(
            message.chat.id,
            result,
            reply_markup=markup
        )
    else:
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu')
        markup.add(btn_back)
        
        bot.send_message(
            message.chat.id,
            result + "\n\n📭 Нет сотрудников для удаления",
            reply_markup=markup
        )

# ========== УДАЛЕНИЕ СОТРУДНИКА ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_emp_'))
def confirm_delete_employee(call):
    user_id = str(call.from_user.id)
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    emp_id = call.data.replace('delete_emp_', '')
    users = load_users()
    
    if emp_id not in users['employees']:
        bot.answer_callback_query(call.id, "❌ Сотрудник не найден")
        return
    
    emp_name = users['employees'][emp_id].get('name', 'Неизвестно')
    
    markup = types.InlineKeyboardMarkup()
    btn_confirm = types.InlineKeyboardButton('✅ Да, удалить', callback_data=f'confirm_delete_{emp_id}')
    btn_cancel = types.InlineKeyboardButton('❌ Отмена', callback_data='back_to_list')
    markup.add(btn_confirm, btn_cancel)
    
    bot.edit_message_text(
        f"⚠️ Вы уверены, что хотите удалить сотрудника '{emp_name}'?\n\n"
        f"ВНИМАНИЕ: Все данные сотрудника будут потеряны!",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_'))
def execute_delete_employee(call):
    user_id = str(call.from_user.id)
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    emp_id = call.data.replace('confirm_delete_', '')
    users = load_users()
    
    if emp_id not in users['employees']:
        bot.answer_callback_query(call.id, "❌ Сотрудник не найден")
        return
    
    emp_name = users['employees'][emp_id].get('name', 'Неизвестно')
    
    # Удаляем данные сотрудника
    data = load_data()
    if emp_id in data['daily']:
        del data['daily'][emp_id]
    if emp_id in data['weekly']:
        del data['weekly'][emp_id]
    if emp_id in data['quarterly']:
        del data['quarterly'][emp_id]
    save_data(data)
    
    # Удаляем из списка сотрудников
    if emp_id in users['employees']:
        del users['employees'][emp_id]
    save_users(users)
    
    bot.edit_message_text(
        f"✅ Сотрудник '{emp_name}' успешно удален!",
        call.message.chat.id,
        call.message.message_id
    )
    
    # Уведомляем сотрудника
    try:
        bot.send_message(
            emp_id,
            f"⚠️ Ваша учетная запись была удалена администратором.\n\n"
            f"Вы можете зарегистрироваться заново, отправив команду /start"
        )
    except:
        pass
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_list')
def back_to_list(call):
    list_employees_admin(call.message)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text == '📋 Отчеты по сотрудникам')
def reports_by_employees(message):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "⛔ Нет прав")
        return
    
    users = load_users()
    employees = [emp_id for emp_id, emp_data in users['employees'].items() if emp_data.get('role') == 'employee']
    
    if not employees:
        bot.send_message(message.chat.id, "📭 Нет сотрудников")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for emp_id in employees:
        emp_name = users['employees'][emp_id]['name']
        btn = types.InlineKeyboardButton(f"📊 {emp_name}", callback_data=f"adminreport_{emp_id}")
        markup.add(btn)
    
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu'))
    
    bot.send_message(
        message.chat.id,
        "📋 Выберите сотрудника для просмотра отчета:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '✏️ Редактировать отчеты')
def edit_reports_admin(message):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        bot.send_message(message.chat.id, "⛔ Нет прав")
        return
    
    users = load_users()
    employees = [emp_id for emp_id, emp_data in users['employees'].items() if emp_data.get('role') == 'employee']
    
    if not employees:
        bot.send_message(message.chat.id, "📭 Нет сотрудников")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for emp_id in employees:
        emp_name = users['employees'][emp_id]['name']
        btn = types.InlineKeyboardButton(f"✏️ {emp_name}", callback_data=f"adminedit_{emp_id}")
        markup.add(btn)
    
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu'))
    
    bot.send_message(
        message.chat.id,
        "✏️ Выберите сотрудника для редактирования отчетов:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('adminreport_'))
def admin_show_report(call):
    user_id = str(call.from_user.id)
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    emp_id = call.data.replace('adminreport_', '')
    users = load_users()
    data = load_data()
    company_metrics = load_company_metrics()
    
    emp_name = users['employees'].get(emp_id, {}).get('name', 'Неизвестно')
    
    result = f"📊 Отчет по сотруднику: {emp_name}\n\n"
    result += "📅 Последние показатели:\n"
    
    daily_data = data['daily'].get(emp_id, {})
    dates = sorted(daily_data.keys(), reverse=True)[:10]
    
    for date in dates:
        result += f"\n{date}:\n"
        for metric in company_metrics['metrics']:
            value = daily_data[date].get(metric, 0)
            result += f"  • {metric}: {value}\n"
    
    markup = types.InlineKeyboardMarkup()
    btn_edit = types.InlineKeyboardButton('✏️ Редактировать', callback_data=f"adminedit_{emp_id}")
    btn_back = types.InlineKeyboardButton('◀️ Назад', callback_data='backtoreports')
    markup.add(btn_edit, btn_back)
    
    bot.edit_message_text(
        result,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('adminedit_'))
def admin_edit_report(call):
    user_id = str(call.from_user.id)
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    emp_id = call.data.replace('adminedit_', '')
    data = load_data()
    
    dates = sorted(data['daily'].get(emp_id, {}).keys(), reverse=True)
    
    if not dates:
        bot.send_message(call.message.chat.id, "📭 Нет показателей для редактирования")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for date in dates[:10]:
        btn = types.InlineKeyboardButton(f"📅 {date}", callback_data=f"admineditdate_{emp_id}_{date}")
        markup.add(btn)
    
    btn_back = types.InlineKeyboardButton('◀️ Назад', callback_data='backtoeditlist')
    markup.add(btn_back)
    
    bot.edit_message_text(
        f"✏️ Редактирование отчетов сотрудника\n\nВыберите дату:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admineditdate_'))
def admin_edit_date(call):
    user_id = str(call.from_user.id)
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет прав")
        return
    
    parts = call.data.split('_')
    emp_id = parts[1]
    date_str = parts[2]
    data = load_data()
    company_metrics = load_company_metrics()
    
    current_values = data['daily'].get(emp_id, {}).get(date_str, {})
    
    template = f"✏️ Редактирование отчета за {date_str}\n\n"
    template += "Введите новые показатели в формате:\n"
    template += "Название: значение\n\n"
    template += "Текущие значения:\n"
    
    for metric in company_metrics['metrics']:
        current = current_values.get(metric, 0)
        template += f"• {metric}: {current}\n"
    
    template += "\nВведите новые значения (каждый с новой строки):"
    
    msg = bot.send_message(call.message.chat.id, template)
    bot.register_next_step_handler(msg, lambda m: admin_update_report(m, emp_id, date_str))
    bot.answer_callback_query(call.id)

def admin_update_report(message, emp_id, date_str):
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
    except:
        date = datetime.now()
    
    company_metrics = load_company_metrics()
    text = message.text.strip()
    lines = text.split('\n')
    
    new_values = {}
    errors = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if ':' in line:
            name, value = line.split(':', 1)
            name = name.strip()
            try:
                value = float(value.strip())
                if name in company_metrics['metrics']:
                    new_values[name] = value
                else:
                    errors.append(f"{name} - показатель не найден")
            except:
                errors.append(f"{name} - неверное значение")
    
    if new_values:
        update_all_metrics(emp_id, new_values, date)
        bot.send_message(message.chat.id, f"✅ Отчет за {date_str} успешно обновлен!")
        
        users = load_users()
        if emp_id in users['employees']:
            try:
                bot.send_message(
                    emp_id,
                    f"📝 Ваш отчет за {date_str} был отредактирован администратором."
                )
            except:
                pass
    
    if errors:
        bot.send_message(message.chat.id, f"⚠️ Ошибки:\n" + "\n".join(errors))

@bot.callback_query_handler(func=lambda call: call.data == 'backtoreports')
def back_to_reports(call):
    reports_by_employees(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'backtoeditlist')
def back_to_edit_list(call):
    edit_reports_admin(call.message)
    bot.answer_callback_query(call.id)

# ========== ПОМОЩЬ ==========
@bot.message_handler(func=lambda message: message.text == 'ℹ️ Помощь')
def help_command(message):
    help_text = "📚 Помощь по боту\n\n"
    
    help_text += "Для всех пользователей:\n"
    help_text += "• 👤 Мой профиль - просмотр и редактирование ФИО\n"
    help_text += "• 📝 Внести показатель - ввод показателей списком\n"
    help_text += "• 📊 Мои показатели - просмотр (квартал / неделя / день)\n"
    help_text += "• 📈 Общий свод - общая сумма по компании\n"
    help_text += "• 📊 Свод за день - показатели только за сегодня\n\n"
    
    help_text += "Для руководителя:\n"
    help_text += "• 📊 Управление показателями - создание/удаление показателей\n"
    help_text += "• 👥 Список сотрудников - просмотр и удаление сотрудников\n"
    help_text += "• 📋 Отчеты по сотрудникам - детальные отчеты\n"
    help_text += "• ✏️ Редактировать отчеты - исправление любых показателей\n\n"
    
    help_text += "Важно:\n"
    help_text += "• Первый зарегистрировавшийся пользователь становится администратором\n"
    help_text += "• Формат отчета: (квартал / неделя / день)\n"
    help_text += "• После удаления сотрудник может зарегистрироваться заново"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('◀️ На главную', callback_data='back_to_menu'))
    
    bot.send_message(
        message.chat.id,
        help_text,
        reply_markup=markup
    )

# ========== НАВИГАЦИЯ ==========
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_menu')
def back_to_menu_callback(call):
    show_main_menu(call.message)
    bot.answer_callback_query(call.id)

# ========== ЗАПУСК БОТА ==========
if __name__ == '__main__':
    print("🤖 Бот запускается...")
    print("✅ Бот успешно запущен и готов к работе!")
    print("🔄 Нажмите Ctrl+C для остановки\n")
    print("📌 ПЕРВЫЙ ПОЛЬЗОВАТЕЛЬ СТАНЕТ АДМИНИСТРАТОРОМ!\n")
    
    while True:
        try:
            bot.polling(
                none_stop=True,
                timeout=120,
                long_polling_timeout=120,
                interval=0
            )
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Переподключение через 15 секунд...")
            time.sleep(15)
            continue