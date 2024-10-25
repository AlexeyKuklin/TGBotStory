import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import os
from bs4 import BeautifulSoup, NavigableString
import json
import telegram
from config import TOKEN
import random

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Изменяем пути к директориям
HTML_DIR = os.path.dirname(os.path.abspath(__file__))
STORIES_DIR = os.path.join(HTML_DIR, 'stories')

# Путь к файлу с рейтингами
RATINGS_FILE = 'ratings.json'

def load_ratings():
    """Загружает рейтинги из файла"""
    if os.path.exists(RATINGS_FILE):
        with open(RATINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_ratings(ratings):
    """Сохраняет рейтинги в файл"""
    with open(RATINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ratings, f, ensure_ascii=False, indent=2)

def get_average_rating(story_id):
    """Получает средний рейтинг для рассказа"""
    ratings = load_ratings()
    if story_id in ratings and 'votes' in ratings[story_id]:
        votes = ratings[story_id]['votes']
        if votes:
            return sum(votes) / len(votes), len(votes)
    return 0, 0

def create_rating_keyboard(story_id):
    """Создает клавиатуру с кноками оценки"""
    avg_rating, votes = get_average_rating(story_id)
    
    # Используем эмодзи от какашки до довольного
    rating_symbols = {
        1: "💩",
        2: "😕",
        3: "😐",
        4: "🙂",
        5: "😊"
    }
    
    keyboard = [
        [
            InlineKeyboardButton(rating_symbols[1], callback_data=f"rate_{story_id}_1"),
            InlineKeyboardButton(rating_symbols[2], callback_data=f"rate_{story_id}_2"),
            InlineKeyboardButton(rating_symbols[3], callback_data=f"rate_{story_id}_3"),
            InlineKeyboardButton(rating_symbols[4], callback_data=f"rate_{story_id}_4"),
            InlineKeyboardButton(rating_symbols[5], callback_data=f"rate_{story_id}_5")
        ],
        # Используем dummy_ в callback_data для неактивной кнопки
        [InlineKeyboardButton(
            f"Средняя оценка: {avg_rating:.1f} {rating_symbols[round(avg_rating)] if avg_rating > 0 else '🤔'} ({votes} голосов)", 
            callback_data=f"dummy_{story_id}"
        )],
        [InlineKeyboardButton("Назад в главное меню", callback_data='main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_html_files():
    """Получает список HTML файлов из директории stories и их заголовки"""
    files = {}
    # Создаем директорию stories, если она не существует
    if not os.path.exists(STORIES_DIR):
        os.makedirs(STORIES_DIR)
        
    for filename in os.listdir(STORIES_DIR):
        if filename.endswith('.html'):
            file_path = os.path.join(STORIES_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    soup = BeautifulSoup(file, 'html.parser')
                    title = soup.find('title')
                    if title:
                        button_text = title.text.split(': ')[-1]
                        files[filename[:-5]] = button_text
            except Exception as e:
                logging.error(f"Ошибка при чтении файла {filename}: {e}")
    return files

def create_keyboard():
    """Создает клавиатуру с кнопками для каждого HTML файла"""
    files = get_html_files()
    keyboard = []
    row = []
    
    logging.info(f"Найденные файлы: {files}")  # Добавляем лог
    
    for callback_data, button_text in files.items():
        logging.info(f"Создание кнопки: callback={callback_data}, text={button_text}")  # Добавляем лог
        # Если текст кнопки длиннее 20 символов, создаем отдельный ряд
        if len(button_text) > 20:
            if row:  # Если есть незаконченный ряд, добавляем его
                keyboard.append(row)
                row = []
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        else:
            row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            if len(row) == 2:  # Если в ряду две кнопки, добавляем ряд в клавиатуру
                keyboard.append(row)
                row = []
    
    # Добавляем оставшиеся кнопки
    if row:
        keyboard.append(row)
    
    logging.info(f"Созданная клавиатура: {keyboard}")  # Добавляем лог
    return keyboard

def process_element(element, level=0):
    if isinstance(element, NavigableString):
        return element.strip()
    
    text = ""
    if element.name == 'h1':
        text += f"<b>{element.get_text(strip=True)}</b>\n\n"
    elif element.name == 'h2':
        text += f"<b>{element.get_text(strip=True)}</b>\n\n"
    elif element.name == 'h3':
        text += f"<i>{element.get_text(strip=True)}</i>\n\n"
    elif element.name == 'p':
        if element.find(['strong', 'em']):
            for child in element.children:
                if child.name == 'strong':
                    text += f"<b>{child.get_text(strip=True)}</b>"
                elif child.name == 'em':
                    text += f"<i>{child.get_text(strip=True)}</i>"
                elif isinstance(child, NavigableString):
                    text += child.strip()
        else:
            text += element.get_text(strip=True)
        text += "\n\n"
    elif element.name == 'li':
        indent = "  " * level
        if element.find(['ul', 'ol']):
            text += f"{indent}• {element.find(text=True, recursive=False).strip()}\n"
            for child in element.children:
                if child.name in ['ul', 'ol']:
                    text += process_element(child, level + 1)
        else:
            text += f"{indent}• {element.get_text(strip=True)}\n"
    elif element.name in ['ul', 'ol']:
        for child in element.children:
            if child.name == 'li':
                text += process_element(child, level)
        if level == 0:
            text += "\n"
    
    return text

def read_html_file(file_path):
    try:
        logging.info(f"Попытка чтения файла: {file_path}")
        
        if not os.path.exists(file_path):
            logging.error(f"Файл не найден: {file_path}")
            return "Файл не найден."
        
        with open(file_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'html.parser')
            
            # Для index_bot.html ищем section с классом task-description
            if os.path.basename(file_path) == 'index_bot.html':  # Изменено с 'index.html' на 'index_bot.html'
                content = soup.find('section', class_='task-description')
            else:
                # Для файлов историй ищем div с классом story-content
                content = soup.find('div', class_='story-content')
            
            if not content:
                logging.error(f"онтент не найден в файле: {file_path}")
                return "Контент не найден."
            
            text = ""
            for element in content.find_all(['h1', 'h2', 'h3', 'p', 'ul', 'ol'], recursive=False):
                text += process_element(element)
            
            # Удаляем последовательные пустые строки
            lines = text.splitlines()
            cleaned_lines = []
            previous_line_empty = False
            for line in lines:
                if line.strip():
                    cleaned_lines.append(line.rstrip())
                    previous_line_empty = False
                elif not previous_line_empty:
                    cleaned_lines.append("")
                    previous_line_empty = True
            
            result = "\n".join(cleaned_lines).strip()
            logging.info(f"Успешно прочитан файл: {file_path}")
            return result or "Контент не найден."
    except Exception as e:
        logging.error(f"Ошибка при чтении файла {file_path}: {e}")
        return f"Ошибка при чтении файла: {str(e)}"

def create_main_keyboard():
    """Создает главное меню с двумя кнопками"""
    keyboard = [
        [
            InlineKeyboardButton("Случайно", callback_data='random'),
            InlineKeyboardButton("Выбрать", callback_data='select')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_random_story():
    """Возвращает ID случайной истории"""
    files = get_html_files()
    if not files:
        return None
    return random.choice(list(files.keys()))

async def show_main_menu(update_or_query):
    reply_markup = create_main_keyboard()
    description = read_html_file(os.path.join(HTML_DIR, 'index_bot.html'))
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(description, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update_or_query.edit_message_text(description, reply_markup=reply_markup, parse_mode='HTML')

async def show_stories_menu(query):
    """Показывает меню выбора историй"""
    keyboard = create_keyboard()
    reply_markup = InlineKeyboardMarkup(keyboard + [[InlineKeyboardButton("Назад в главное меню", callback_data='main')]])
    await query.edit_message_text(
        "Выберите историю:",
        reply_markup=reply_markup
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_main_menu(update)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    logging.info(f"Получен callback: {query.data}")
    
    try:
        if query.data == 'main':
            await query.answer()
            logging.info("Показываем главное меню")
            await show_main_menu(query)
        elif query.data == 'random':
            await query.answer()
            story_id = get_random_story()
            if not story_id:
                await query.answer("Нет доступных историй")
                return
                
            file_path = os.path.join(STORIES_DIR, f"{story_id}.html")
            text = read_html_file(file_path)
            
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=create_rating_keyboard(story_id),
                    parse_mode='HTML'
                )
            except telegram.error.BadRequest as e:
                if "Message too long" in str(e) or len(text) > 4096:
                    # Обработка длинных сообщений...
                    parts = [text[i:i+4096] for i in range(0, len(text), 4096)]
                    for i, part in enumerate(parts):
                        if i == 0:
                            await query.edit_message_text(
                                text=part,
                                reply_markup=create_rating_keyboard(story_id) if i == len(parts)-1 else None,
                                parse_mode='HTML'
                            )
                        else:
                            await query.message.reply_text(
                                text=part,
                                reply_markup=create_rating_keyboard(story_id) if i == len(parts)-1 else None,
                                parse_mode='HTML'
                            )
        elif query.data == 'select':
            await query.answer()
            await show_stories_menu(query)
        elif query.data.startswith('rate_'):
            logging.info(f"Обработка оценки: {query.data}")
            try:
                # Изменяем способ разбоа данных
                # Формат: rate_story-id_rating
                # Берем последний элемент как оценку, а всё между rate_ и последним _ как id истории
                parts = query.data.split('_')
                if len(parts) < 3:
                    logging.error(f"Недостаточно частей в данных оценки: {len(parts)}")
                    await query.answer("Ошибка: неверный формат данных оценки")
                    return
                
                rating = parts[-1]  # Последний элемент - оценка
                story_id = '_'.join(parts[1:-1])  # Все элементы между первым и последним - id истории
                
                logging.info(f"Разбор оценки: story_id={story_id}, rating={rating}")
                
                try:
                    rating = int(rating)
                except ValueError:
                    logging.error(f"Неверный формат оценки: {rating}")
                    await query.answer("Ошибка: неверный формат оценки")
                    return
                
                if rating < 1 or rating > 5:
                    logging.error(f"Недопустимое значение оценки: {rating}")
                    await query.answer("Ошибка: недопустимое значение оценки")
                    return
                
                # Остальной код обработки оценки остается без изменений
                ratings = load_ratings()
                if story_id not in ratings:
                    ratings[story_id] = {
                        'votes': [],
                        'user_votes': {}
                    }
                elif 'user_votes' not in ratings[story_id]:
                    ratings[story_id]['user_votes'] = {}
                
                user_id = str(query.from_user.id)
                
                if user_id in ratings[story_id]['user_votes']:
                    old_rating = ratings[story_id]['user_votes'][user_id]
                    if old_rating == rating:
                        await query.answer("Вы уже поставили такую оценку!")
                        return
                    if old_rating in ratings[story_id]['votes']:
                        ratings[story_id]['votes'].remove(old_rating)
                
                ratings[story_id]['votes'].append(rating)
                ratings[story_id]['user_votes'][user_id] = rating
                
                save_ratings(ratings)
                
                avg_rating, votes = get_average_rating(story_id)
                await query.answer(f"Спасибо за оценку! Средний рейтинг: {avg_rating:.1f} ({votes} голосов)")
                
                await query.edit_message_reply_markup(
                    reply_markup=create_rating_keyboard(story_id)
                )
                
            except Exception as e:
                logging.error(f"Неожиданная ошибка при обработке оценки: {e}")
                await query.answer("Произошла ошибка при обработке оценки")
        elif query.data.startswith('dummy_'):
            await query.answer("Это информационная строка")
        else:
            await query.answer()
            file_path = os.path.join(STORIES_DIR, f"{query.data}.html")
            logging.info(f"Попытка открыть историю: {file_path}")
            
            if not os.path.exists(file_path):
                logging.error(f"Файл не существует: {file_path}")
                await query.message.reply_text("Ошибка: файл истории не найден")
                return
                
            text = read_html_file(file_path)
            
            if not text:
                logging.error("Получен пустой текст истории")
                await query.message.reply_text("Ошибка: не удалось загрузить историю")
                return
            
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=create_rating_keyboard(query.data),
                    parse_mode='HTML'
                )
                logging.info("История успешно отправлена")
            except telegram.error.BadRequest as e:
                if "Message too long" in str(e) or len(text) > 4096:
                    logging.info("Разбиваем длинное сообщение на части")
                    parts = [text[i:i+4096] for i in range(0, len(text), 4096)]
                    for i, part in enumerate(parts):
                        if i == 0:
                            await query.edit_message_text(
                                text=part,
                                reply_markup=create_rating_keyboard(query.data) if i == len(parts)-1 else None,
                                parse_mode='HTML'
                            )
                        else:
                            await query.message.reply_text(
                                text=part,
                                reply_markup=create_rating_keyboard(query.data) if i == len(parts)-1 else None,
                                parse_mode='HTML'
                            )
                else:
                    raise  # Пробрасываем другие ошибки BadRequest
                    
    except Exception as e:
        logging.error(f"Общая ошибка в обработке кнопки: {str(e)}")
        await query.answer(f"Произошла ошибка: {str(e)}")

def main() -> None:
    # Создание приложения и предача ему токена API
    application = ApplicationBuilder().token(TOKEN).build()

    # Регистрация обработчиков команд и кнопок
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
