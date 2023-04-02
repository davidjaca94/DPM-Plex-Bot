# Native imports
import os
import json
import shutil
import logging

# Installed imports
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedPhoto, ParseMode, InputMediaPhoto
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, ChosenInlineResultHandler, Filters
from telegram.ext.dispatcher import run_async

# Custom imports
from tg_conf import *


# Global vars
tg_users = lambda: [int(user) for user in list(set(json.loads(open("tg_users.json", "r").read()).values()))]

# Enable logging
logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(asctime)s] [%(levelname)s] %(message)s", level=logging.INFO)
logging.getLogger('apscheduler').setLevel(logging.CRITICAL)
logging.getLogger('telegram').setLevel(logging.CRITICAL)


#region TheMovieDB auxiliary functions

pass

#endregion


#region TheMovieDB call functions

def search_movies(query):
    language = 'es-ES'
    url = f'https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={query}&language={language}'
    response = requests.get(url)
    data = response.json()

    results = data['results']
    if results:
        for result in results:
            title = result['title']
            release_date = result['release_date']
            print(f'{title} ({release_date})')
    else:
        print('No se encontraron resultados para esta búsqueda.')

#endregion


#region Telegram auxiliary functions

def tg_generate_menu_request(options):
    keyboard = []

    if len(options) == 1:
        keyboard.append([])
        keyboard[0].append(InlineKeyboardButton("✅ Confirmar", callback_data=json.dumps({'cmd': "req_1", 'opt': options[0]['id']})))
        keyboard[0].append(InlineKeyboardButton("❌ Rechazar", callback_data=json.dumps({'cmd': "req_1", 'opt': ""})))
    elif len(options) > 1:
        for option in options:
            keyboard.append([InlineKeyboardButton(option['title'], callback_data=json.dumps({'cmd': "req_n", 'opt': option['id']}))])

    return InlineKeyboardMarkup(keyboard)

def tg_logger_format(update, text):
    log = ""

    log += f"[{update.message.chat.title}] " if update.message.chat.title else ""

    log += f"[{update._effective_user.id}]"
    log += f"[@{update._effective_user.username}]" if update._effective_user.username else ""
    log += f"[{update._effective_user.first_name} {update._effective_user.last_name}] ".replace(" None", "")

    log += text

    return log

#endregion


#region Telegram handler functions

def handler_start(update, context):
    msg = '''
• *Mándame 1 foto* frontal de tu cara y podrás hacer lo siguiente:
    - Verte más joven
    - Verte más viejo
    - Verte más hombre
    - Verte más mujer
• *Mándame 2 o más fotos de vez* con una cara frontal en cada una y podrás hacer lo siguiente:
    - Fusionar las caras en una sola persona
    '''

    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

def handler_help(update, context):
    handler_start(update, context)

def handler_bad_msg(update, context):
    if update._effective_chat.type=="private":
        logger.warning(tg_logger_format(update, f"Invalid command '{update.message.text}' {update}"))
        update.message.reply_text("Lo siento pero sólo entiendo klingon y una serie de comandos")
        handler_start(update, context)

def handler_bad_user(update, context):
    if update._effective_chat.type == "private":
        logger.warning(tg_logger_format(update, f"Forbidden user {update}"))
        update.message.reply_text("No eres digno de empuñar a Excalibur, si crees que es un error contacta con Merlín")

def handler_error(update, context):
    logger.error(tg_logger_format(update, f"Error '{context.error}' {update}"), exc_info=True)

def handler_request(update, context):
    msg = update.message.text
    msg = msg[len("#Petición "):].split("\n")[0]
    logger.info(tg_logger_format(update, f"Request '{msg}'"))

    #TODO
    options = [{'id': "447277", 'title': "[PELIC] (2023) La sirenita"}, {'id': "10144", 'title': "[PELIC] (1989) La sirenita"}]

    if options:

        #TODO
        if False:
            response = msg
            options = [options[0]]
        else:
            response = "Dime con cuál se corresponde:"
            options.append({'id': "", 'title': "❌ Ninguna"})

        menu_options = tg_generate_menu_request(options)
        update.message.reply_text(response, reply_markup=menu_options)
    else:
        update.message.reply_text("No he encontrado coincidencias, puedes darme más detalles?")

def handler_request_callback(update, context):
    data = json.loads(update.callback_query.data)

    #TODO
    print(data)

    update.callback_query.edit_message_text("patata")

#endregion


def main():
    logger.info("Bot starting...")

    updater = Updater(tg_bot_token, use_context=True, workers=1)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", handler_start, Filters.user(user_id=tg_users())))
    dp.add_handler(CommandHandler("help", handler_help, Filters.user(user_id=tg_users())))

    dp.add_handler(CommandHandler("peticion", handler_request, Filters.user(user_id=tg_users())))
    dp.add_handler(MessageHandler(Filters.regex("#[Pp]etici[óo]n .*") & Filters.user(user_id=tg_users()), handler_request))
    dp.add_handler(CallbackQueryHandler(handler_request_callback, pattern='^{"cmd": "req_.", "opt": ".*"}$'))

    dp.add_handler(MessageHandler(Filters.all & Filters.user(user_id=tg_users()), handler_bad_msg))
    dp.add_handler(MessageHandler(Filters.all, handler_bad_user))
    dp.add_error_handler(handler_error)

    logger.info("Bot listening...")
    updater.start_polling(timeout=60)
    updater.idle()


if __name__ == '__main__':
    main()
