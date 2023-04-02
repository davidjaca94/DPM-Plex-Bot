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

def generate_request_menu(options):
    keyboard = []

    if len(options) == 1:
        keyboard.append([])
        keyboard[0].append(InlineKeyboardButton("✅ Confirmar", callback_data=json.dumps({'cmd': "req_1", 'opt': options[0]['id']})))
        keyboard[0].append(InlineKeyboardButton("❌ Rechazar", callback_data=json.dumps({'cmd': "req_1", 'opt': ""})))
    elif len(options) > 1:
        for option in options:
            keyboard.append([InlineKeyboardButton(option['title'], callback_data=json.dumps({'cmd': "req_n", 'opt': option['id']}))])

    return InlineKeyboardMarkup(keyboard)

def generate_photo_menu(msg_id, photos, cmd_type):
    keyboard = []

    for command in ["Joven", "Viejo", "Hombre", "Mujer"]:
        data = json.dumps({'cmd': command, 'msg': msg_id, 'photos': photos})
        keyboard.append([InlineKeyboardButton(command, callback_data=data)])

    return InlineKeyboardMarkup(keyboard)

def generate_poll_menu(id):
    polls = json.loads(open(polls_path, "r").read()) if os.path.exists(polls_path) else {}
    poll = polls[id] if id in polls else {}
    options = poll['options'] if 'options' in poll else empty_options

    keyboard = [[]]

    for option in poll_options:
        msg = f"{poll_options[option]} {len(options[option])}"
        data = json.dumps({'id': id, 'option': option})
        keyboard[0].append(InlineKeyboardButton(msg, callback_data=data))

    keyboard.append([InlineKeyboardButton("Compartir", switch_inline_query=id)])

    return InlineKeyboardMarkup(keyboard)

def parse_photo_id(tg_photo_id):
    photos_map = json.loads(open(photos_map_path, "r").read()) if os.path.exists(photos_map_path) else {}

    if not tg_photo_id in photos_map:
        photos_map[tg_photo_id] = len(photos_map)+1
        open(photos_map_path, "w").write(json.dumps(photos_map))

    return photos_map[tg_photo_id]

def unparse_photo_id(photo_id):
    photos_map = json.loads(open(photos_map_path, "r").read()) if os.path.exists(photos_map_path) else {}
    inverse_map = {v: k for k, v in photos_map.items()}

    tg_photo_id = inverse_map[photo_id] if photo_id in inverse_map else None

    return tg_photo_id

def get_photo(update):
    photo_file = update.message.photo[-1]
    photo_id = parse_photo_id(photo_file['file_id'])

    # Don't download until process
    # photo_path = f"{images_path}{photo_id}.jpg"
    # os.makedirs(os.path.dirname(photo_path), exist_ok=True)
    #
    # if not os.path.exists(photo_path):
    #     photo_file.get_file().download(photo_path)

    return photo_id

def recover_photo(photo_id, photo_path, bot):
    os.makedirs(os.path.dirname(photo_path), exist_ok=True)
    newFile = bot.get_file(photo_id)
    newFile.download(photo_path)

def check_photos(photos_id, bot):
    check = True

    try:
        for photo_id in photos_id:
            photo_path = f"{images_path}{photo_id}.jpg"
            if not os.path.exists(photo_path):
                tg_photo_id = unparse_photo_id(photo_id)
                if tg_photo_id:
                    recover_photo(tg_photo_id, photo_path, bot)
                else:
                    check = False
    except:
        check = False

    return check

def get_album(update, context, photo_id):
    media_group = update.message.media_group_id
    last_media_group = context.user_data['last_media_group'] if 'last_media_group' in context.user_data else None

    last_photos = context.user_data['last_photos'] if ('last_photos' in context.user_data and media_group and media_group == last_media_group) else []
    last_photos.append(photo_id)

    context.user_data['last_photos'] = last_photos
    context.user_data['last_media_group'] = media_group

    return last_photos

def update_polls(id, option=None, user=None, options=None, updates=None):
    need_update = False

    polls = json.loads(open(polls_path, "r").read()) if os.path.exists(polls_path) else {}
    poll = polls[id] if id in polls else {}

    if options and not 'options' in poll:
        # Only to init options
        poll['options'] = options

    poll['options'] = poll['options'] if 'options' in poll else {}

    if option and user:
        poll['options'][option] = poll['options'][option] if option in poll['options'] else []

        need_update = (not user in poll['options'][option])

        # If user already voted, delete the vote to change it
        for current_option in poll['options']:
            if user in poll['options'][current_option]:
                poll['options'][current_option].remove(user)

        poll['options'][option].append(user)

    if updates:
        current_updates = poll['updates'] if 'updates' in poll else []
        poll['updates'] = [dict(s) for s in set(frozenset(d.items()) for d in (current_updates + updates))]

    polls[id] = poll
    open(polls_path, "w").write(json.dumps(polls))

    return need_update

def update_polls_chats(id, bot):
    polls = json.loads(open(polls_path, "r").read()) if os.path.exists(polls_path) else {}
    poll = polls[id]

    reply_markup = generate_poll_menu(id)
    for update in poll['updates']:
        try:
            if 'inline_msg_id' in update:
                bot.edit_message_reply_markup(inline_message_id=update['inline_msg_id'], reply_markup=reply_markup)
            else:
                bot.edit_message_reply_markup(chat_id=update['chat_id'], message_id=update['msg_id'], reply_markup=reply_markup)
        except:
            pass # One instance of this pool is deleted

def save_results(result_id, file_id, photos_id, cmd):
    results = json.loads(open(results_path, "r").read()) if os.path.exists(results_path) else {}
    results[result_id] = {'file_id': file_id, 'photos_id': photos_id, 'cmd': cmd}
    open(results_path, "w").write(json.dumps(results))

def recover_result(result_id):
    results = json.loads(open(results_path, "r").read()) if os.path.exists(results_path) else {}
    result = results[result_id] if result_id in results else {}
    return result

def remove_path(path):
    if os.path.exists(path):
        if os.path.isfile(path):
            os.remove(path)
        else:
            # Delete folder with all content
            shutil.rmtree(path, ignore_errors=True)

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

def start(update, context):
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

def help(update, context):
    start(update, context)

def bad_msg(update, context):
    if update._effective_chat.type=="private":
        logger.warning(tg_logger_format(update, f"Invalid command '{update.message.text}' {update}"))
        update.message.reply_text("Lo siento pero sólo entiendo klingon y una serie de comandos")
        start(update, context)

def bad_user(update, context):
    if update._effective_chat.type == "private":
        logger.warning(tg_logger_format(update, f"Forbidden user {update}"))
        update.message.reply_text("No eres digno de empuñar a Excalibur, si crees que es un error contacta con Merlín")

def error(update, context):
    logger.error(tg_logger_format(update, f"Error '{context.error}' {update}"), exc_info=True)

def request(update, context):
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

        menu_options = generate_request_menu(options)
        update.message.reply_text(response, reply_markup=menu_options)
    else:
        update.message.reply_text("No he encontrado coincidencias, puedes darme más detalles?")


    # chat_id = update.message.chat.id
    # msg_id = update.message.message_id
    # user_id = update._effective_user.id
    # user_name = f"{update._effective_user.first_name} {update._effective_user.last_name}".replace(" None", "")
    #
    #     photo_id = get_photo(update)
    # photos = get_album(update, context, photo_id)
    #
    # if len(photos)==1:
    #     reply_markup = generate_photo_menu(msg_id, photos, '1')
    #     reply = update.message.reply_text("¿Qué quieres hacer con esta foto?", reply_markup=reply_markup)
    #
    #     context.user_data['last_msg'] = reply.message_id
    # elif len(photos)>=2:
    #     last_msg = context.user_data['last_msg']
    #
    #     reply_markup = generate_photo_menu(msg_id, photos, '2')
    #     context.bot.edit_message_text(chat_id=chat_id, message_id=last_msg, text="¿Qué quieres hacer con estas fotos?", reply_markup=reply_markup)
    # else:
    #     last_msg = context.user_data['last_msg']
    #
    #     context.bot.edit_message_text(chat_id=chat_id, message_id=last_msg, text=f"Lo siento pero no soy capaz de hacer nada con {len(photos)} fotos...")
    #
    # logger.info(f"({user_id}) {user_name}: {photo_id} [<<<<]")

@run_async
def cmd(update, context):
    data = json.loads(update.callback_query.data)

    chat_id = update.callback_query.message.chat.id
    msg_id = data['msg']
    user_id = update._effective_user.id
    user_name = f"{update._effective_user.first_name} {update._effective_user.last_name}".replace(" None", "")

    cmd = data['cmd']
    photos_id = data['photos']
    result_id = f"{'+'.join([str(photo_id) for photo_id in photos_id])}#{cmd}"

    check = check_photos(photos_id, context.bot) # Download again if already deleted

    logger.info(f"({user_id}) {user_name}: {result_id} [<---]")

    if check:
        result = process_photos(photos_id, result_id, cmd)

        if not 'error' in result:
            updates = []
            result_path = result['path']
            reply_markup = generate_poll_menu(result_id)

            # Response to user
            reply_user = context.bot.send_photo(chat_id, open(result_path, 'rb'), reply_to_message_id=msg_id, reply_markup=reply_markup, caption=cmd+(" #DEBUG" if facade_mode else ""))
            updates.append({'chat_id': chat_id, 'msg_id': reply_user.message_id})

            # Forward to group
            tg_photos_id = [unparse_photo_id(photo_id) for photo_id in photos_id]
            media_group = [InputMediaPhoto(tg_photo_id) for tg_photo_id in tg_photos_id]
            media_group[-1].caption = f'Reenviado desde [{user_name}](tg://user?id={user_id})'
            media_group[-1].parse_mode = ParseMode.MARKDOWN
            reply = context.bot.sendMediaGroup(tg_group_id, media_group)[0]
            #reply = context.bot.forward_message(chat_id=tg_group_id, from_chat_id=chat_id, message_id=msg_id) # Only forwards 1 photo
            reply_group = context.bot.send_photo(tg_group_id, open(result_path, 'rb'), reply_to_message_id=reply.message_id, reply_markup=reply_markup, caption=cmd+(" #DEBUG" if facade_mode else ""))
            updates.append({'chat_id': tg_group_id, 'msg_id': reply_group.message_id})

            update_polls(result_id, options=empty_options, updates=updates)
            save_results(result_id, reply_group.photo[-1]['file_id'], photos_id, cmd)
        else:
            msg = f"Se ha producido un error: {result['error']}"
            context.bot.send_message(chat_id, msg, reply_to_message_id=msg_id)
    else:
        msg_1 = "Ya no dispongo de esa foto... mándamela otra vez por favor 🙏"
        msg_2 = "Ya no dispongo de esas fotos... mándamelas otra vez por favor 🙏"
        msg = msg_1 if len(photos_id)==1 else msg_2
        context.bot.send_message(chat_id, msg, reply_to_message_id=msg_id)
        logger.error(f"{photos_id}: {msg}")

    logger.info(f"({user_id}) {user_name}: {result_id} [--->]")

def poll(update, context):
    user_id = update._effective_user.id
    user_name = f"{update._effective_user.first_name} {update._effective_user.last_name}".replace(" None", "")

    data = json.loads(update.callback_query.data)
    result_id = data['id']
    option = data['option']

    need_update = update_polls(result_id, option=option, user={'user_id': user_id, 'user_name': user_name})
    if need_update:
        update_polls_chats(result_id, context.bot)

    logger.info(f"({user_id}) {user_name}: {result_id} [{option}]")

def share(update, context):
    result_id = update.inline_query.query
    result = recover_result(result_id)

    if result:
        file_id = result['file_id']
        caption = result['cmd']
        reply_markup = generate_poll_menu(result_id)

        response = [InlineQueryResultCachedPhoto(uuid4(), file_id, caption=caption, reply_markup=reply_markup)]
        update.inline_query.answer(response, cache_time=0)

def shared(update, context):
    user_id = update._effective_user.id
    user_name = f"{update._effective_user.first_name} {update._effective_user.last_name}".replace(" None", "")

    result_id = update.chosen_inline_result.query
    updates = [{'inline_msg_id': update.chosen_inline_result.inline_message_id}]
    update_polls(result_id, updates=updates)

    logger.info(f"({user_id}) {user_name}: {result_id} [>>>>]")

#endregion


def main():
    logger.info("Bot starting...")

    updater = Updater(tg_bot_token, use_context=True, workers=1)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start, Filters.user(user_id=tg_users())))
    dp.add_handler(CommandHandler("help", help, Filters.user(user_id=tg_users())))
    dp.add_handler(CommandHandler("peticion", request, Filters.user(user_id=tg_users())))
    dp.add_handler(MessageHandler(Filters.regex("#[Pp]etici[óo]n .*") & Filters.user(user_id=tg_users()), request))

    # dp.add_handler(CallbackQueryHandler(cmd, pattern='^{"cmd": .*, "msg": .*, "photos": .*}$'))
    # dp.add_handler(CallbackQueryHandler(poll, pattern='^{"id": .*, "option": .*}$'))
    # dp.add_handler(InlineQueryHandler(share))
    # dp.add_handler(ChosenInlineResultHandler(shared))

    dp.add_error_handler(error)
    dp.add_handler(MessageHandler(Filters.all & Filters.user(user_id=tg_users()), bad_msg))
    dp.add_handler(MessageHandler(Filters.all, bad_user))

    logger.info("Bot listening...")
    updater.start_polling(timeout=60)
    updater.idle()


if __name__ == '__main__':
    main()
