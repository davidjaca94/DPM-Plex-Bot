import os
import json
import time
import shutil
import logging
import argparse
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedPhoto, ParseMode, InputMediaPhoto
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, ChosenInlineResultHandler, Filters
from telegram.ext.dispatcher import run_async


tg_bot_token = "" # https://t.me/...
tg_group_id = "" # https://t.me/joinchat/...

watermark_path = "watermark.png"
images_path = "images/"
latents_path = "latents/"
polls_path = "polls.json"
photos_map_path = "photos.json"
results_path = "results.json"
cache_paths = [images_path, latents_path]
data_paths = [polls_path, photos_map_path, results_path]

reset_types = ['all', 'cache', 'data']

commands_1 = ["Joven", "Viejo", "Hombre", "Mujer"]
commands_2 = ["Fusion"]
commands = {'1': commands_1, '2': commands_2, 'all': commands_1+commands_2}

commands_map ={'Joven': {'cmd': "age", 'sign': -1}, 'Viejo': {'cmd': "age", 'sign': 1}, 'Hombre': {'cmd': "gender", 'sign': 1}, 'Mujer': {'cmd': "gender", 'sign': -1}}

poll_options = {'like': "👍", 'dislike': "👎", 'indifferent': "😐", 'scary': "😱", 'funny': "😂", 'lovely': "😍"}
empty_options = {option: [] for option in poll_options}

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


#region GAN functions
def encode_photos(input_photos_path):
    encoded_photos_path = [input_photo_path.replace(images_path, latents_path).replace(".jpg", ".npy") for input_photo_path in input_photos_path]
    new_photo_paths = [input_photo_path for input_photo_path, encoded_photo_path in zip(input_photos_path, encoded_photos_path) if not os.path.exists(encoded_photo_path)]
    
    os.makedirs(latents_path, exist_ok=True)
    
    gan_methods.images_align(new_photo_paths, new_photo_paths)
    gan_methods.images_vectorize(new_photo_paths, latents_path)

    return encoded_photos_path

def process_photos(input_photos_id, output_photo_id, command):
    input_photos_path = [f"{images_path}{input_photo_id}.jpg" for input_photo_id in input_photos_id]
    output_path = f"{images_path}{output_photo_id}.jpg"
    result = {'path': output_path}

    try:
        if not os.path.exists(output_path):
            if not facade_mode:
                encoded_photos_path = encode_photos(input_photos_path)

                if command=="Fusion":
                    gan_methods.faces_mix(encoded_photos_path, output_path)
                elif command in commands_1:
                    command_map = commands_map[command]
                    lvl = 3 * command_map['sign']
                    cmd = command_map['cmd']
                    gan_methods.face_style(encoded_photos_path[0], cmd, lvl, output_path)
                else:
                    # Command defined but not implemented
                    raise Exception(f"Funcionalidad '{command}' en desarrollo...")
                
                if watermark_enabled:
                    if os.path.exists(output_path):
                        if os.path.exists(watermark_path):
                            gan_methods.burn_watermark(output_path, watermark_path, (524, 933))
            else:
                shutil.copy(input_photos_path[0], output_path)

    except Exception as e:
        logger.error(e)
        result['error'] = e

    # Clean temp files
    for input_photo_path in input_photos_path:
        if os.path.exists(input_photo_path):
            os.remove(input_photo_path)

    return result

#endregion


#region Auxiliary functions
def generate_photo_menu(msg_id, photos, cmd_type):
    keyboard = []

    for command in commands[cmd_type]:
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

#endregion


#region Handler functions
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

def photo(update, context):
    chat_id = update.message.chat.id
    msg_id = update.message.message_id
    user_id = update._effective_user.id
    user_name = f"{update._effective_user.first_name} {update._effective_user.last_name}".replace(" None", "")

    photo_id = get_photo(update)
    photos = get_album(update, context, photo_id)
    
    if len(photos)==1:
        reply_markup = generate_photo_menu(msg_id, photos, '1')
        reply = update.message.reply_text("¿Qué quieres hacer con esta foto?", reply_markup=reply_markup)

        context.user_data['last_msg'] = reply.message_id
    elif len(photos)>=2:
        last_msg = context.user_data['last_msg']

        reply_markup = generate_photo_menu(msg_id, photos, '2')
        context.bot.edit_message_text(chat_id=chat_id, message_id=last_msg, text="¿Qué quieres hacer con estas fotos?", reply_markup=reply_markup)
    else:
        last_msg = context.user_data['last_msg']
    
        context.bot.edit_message_text(chat_id=chat_id, message_id=last_msg, text=f"Lo siento pero no soy capaz de hacer nada con {len(photos)} fotos...")

    logger.info(f"({user_id}) {user_name}: {photo_id} [<<<<]")

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

def error(update, context):
    logger.warning(f"Update '{update}' caused error '{context.error}'")

def bad(update, context):
    if update._effective_chat.type=="private":
        help(update, context)

#endregion


#region Program functions
def run():
    if not facade_mode:
        global gan_methods
        import gan_methods
        logger.info("Loading models...")
        gan_methods.load_models()
        os.system('clear')

    logger.info("Bot starting...")

    updater = Updater(tg_bot_token, use_context=True, workers=1)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))

    dp.add_handler(MessageHandler(Filters.photo, photo))
    dp.add_handler(CallbackQueryHandler(cmd, pattern='^{"cmd": .*, "msg": .*, "photos": .*}$'))
    dp.add_handler(CallbackQueryHandler(poll, pattern='^{"id": .*, "option": .*}$'))
    dp.add_handler(InlineQueryHandler(share))
    dp.add_handler(ChosenInlineResultHandler(shared))

    dp.add_error_handler(error)
    dp.add_handler(MessageHandler(Filters.all, bad))

    logger.info("Bot listening...")
    updater.start_polling(timeout=60)
    updater.idle()

def reset(type):
    if not facade_mode:
        os.system('clear')
    
    logger.info(f"Reseting {type}...")

    if type==reset_types[1]:
        for path in cache_paths:
            logger.info(f"Deleting path '{path}'")
            remove_path(path)
    elif type==reset_types[2]:
        for path in data_paths:
            logger.info(f"Deleting path '{path}'")
            remove_path(path)
    elif type==reset_types[0]:
        reset(reset_types[1])
        reset(reset_types[2])

#endregion


def main():
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--reset", type=str, nargs='*', choices=reset_types)
    parser.add_argument("--watermark", action='store_true', default=False)
    parser.add_argument("--facade", action='store_true', default=False)
    args = parser.parse_args()

    global watermark_enabled
    global facade_mode
    watermark_enabled = args.watermark
    facade_mode = args.facade
    
    if args.reset:
        for arg in args.reset:
            reset(arg)
    else:
        run()


if __name__ == '__main__':
    main()
