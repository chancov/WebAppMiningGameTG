import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, WEBAPP_URL
from urllib.parse import quote_plus
import httpx

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not hasattr(user, 'id'):
        return
    user_id = int(user.id)
    first_name = getattr(user, 'first_name', '') or ''
    last_name = getattr(user, 'last_name', '') or ''
    photo_url = ''

    # Получаем фото профиля пользователя (если есть)
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        print(f"Debug: Total photos found: {photos.total_count}")
        
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            print(f"Debug: File ID: {file_id}")
            
            # Получаем информацию о файле
            file = await context.bot.get_file(file_id)
            if file and file.file_path:
                photo_url = file.file_path
                # Оставляем только file_path, если file_path — это полный URL
                prefix = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/"
                if photo_url.startswith(prefix):
                    photo_url = photo_url[len(prefix):]
                print(f"Debug: File path (for webapp): {photo_url}")
            else:
                # Если file_path недоступен, используем file_id
                photo_url = file_id
                print(f"Debug: Using file_id as fallback: {photo_url}")
        else:
            photo_url = ''
            print(f"Debug: No photo found for user {user_id}")
    except Exception as e:
        photo_url = ''
        print(f"Debug: Error getting photo: {e}")
    
    # Дополнительная отладка
    print(f"Debug: User data - ID: {user_id}, Name: {first_name}, Last: {last_name}")
    print(f"Debug: Final photo_url: {photo_url}")

    # --- Реферальная регистрация через backend API ---
    ref_code = None
    if context.args and len(context.args) > 0:
        ref_code = context.args[0]
    # Проверяем, есть ли пользователь в БД
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(f"http://127.0.0.1:5000/api/profile?telegram_id={user_id}")
        profile_data = profile_resp.json() if profile_resp.status_code == 200 else None
        if not profile_data or not profile_data.get('ok'):
            # Регистрируем пользователя через API
            reg_payload = {
                'telegram_id': str(user_id),
                'first_name': first_name,
                'last_name': last_name,
                'photo_url': photo_url,
                'ref_code': ref_code
            }
            reg_resp = await client.post("http://127.0.0.1:5000/api/register", json=reg_payload)
            reg_data = reg_resp.json() if reg_resp.status_code == 200 else None
            print(f"[BOT] Registered user {user_id} via API, ref_code={ref_code}, result: {reg_data}")
        else:
            print(f"[BOT] User {user_id} already exists in DB")

    # Формируем URL для Web App с данными пользователя (кодируем параметры)
    webapp_url = f"{WEBAPP_URL}?user_id={user_id}&first_name={quote_plus(str(first_name))}&last_name={quote_plus(str(last_name))}&photo_url={quote_plus(str(photo_url))}"
    print(f"Debug: WebApp URL: {webapp_url}")
    
    # Создаем кнопку Web App
    keyboard = [[KeyboardButton(
        text="Открыть веб-приложение",
        web_app=WebAppInfo(url=webapp_url)
    )]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    message = getattr(update, 'message', None)
    if message and hasattr(message, 'reply_text'):
        await message.reply_text(
            'Нажмите кнопку, чтобы открыть веб-приложение:',
            reply_markup=reply_markup
        )
    elif getattr(update, 'callback_query', None) is not None:
        callback_message = getattr(update.callback_query, 'message', None)
        if callback_message and hasattr(callback_message, 'reply_text'):
            await callback_message.reply_text(
                'Нажмите кнопку, чтобы открыть веб-приложение:',
                reply_markup=reply_markup
            )

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.run_polling() 