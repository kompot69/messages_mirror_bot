import asyncio, threading, time, logging, vk_api, os, requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.upload import VkUpload
import config, commands, db, strings

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s %(levelname)s in %(name)s: %(message)s")
handler = logging.StreamHandler()
#handler = logging.FileHandler(f"{__name__}.log", mode='w')
handler.setFormatter(formatter)
logger.addHandler(handler)

# === Очередь обмена сообщениями ===
message_bus = asyncio.Queue()
async def msg_send(): # ловим cooбщения
    vk_session = vk_api.VkApi(token=config.vk_user_token)
    vk = vk_session.get_api()
    upload = VkUpload(vk_session)
    while True:
        to_service, msg, to_id, attachments = await message_bus.get()
        logger.debug(f'send message to {to_service} {to_id}')
        if to_service == "tg": 
            try: 
                await tg_bot.send_message(to_id, msg) 
                for attachment in attachments: #[attachment_prefix, attachment_name, attachment_size]
                    if os.path.isfile(f'{config.attachments_dir}/{attachment[1]}'):
                        if attachment[1].endswith('.png') or attachment[1].endswith('.jpg') or attachment[1].endswith('.jpeg'): await tg_bot.send_photo(to_id, FSInputFile(f'{config.attachments_dir}/{attachment[1]}'), caption=attachment[1])
                        elif attachment[1].endswith('.ogg'): await tg_bot.send_voice(to_id, FSInputFile(f'{config.attachments_dir}/{attachment[1]}'), caption=attachment[1])
                        elif attachment[1].endswith('.mp3'): await tg_bot.send_audio(to_id, FSInputFile(f'{config.attachments_dir}/{attachment[1]}'), caption=attachment[1])
                        elif attachment[1].endswith('.mp4'): await tg_bot.send_video(to_id, FSInputFile(f'{config.attachments_dir}/{attachment[1]}'), caption=attachment[1])
                        else: await tg_bot.send_document(to_id, FSInputFile(f'{config.attachments_dir}/{attachment[1]}'), caption=attachment[1])
                    os.remove(f'{config.attachments_dir}/{attachment[1]}')
            except TelegramForbiddenError as e: logger.warning(f'error send to {to_service} {to_id}: {e}')
            except Exception as e: logger.error(e,exc_info=True)
        elif to_service == "vk": 
            try: 
                vk.messages.send( peer_id=to_id, message=f"{msg}", random_id=0 )
                for attachment in attachments: #[attachment_prefix, attachment_name, attachment_size]
                    if os.path.isfile(f'{config.attachments_dir}/{attachment[1]}'):
                        if attachment[1].endswith('.png') or attachment[1].endswith('.jpg') or attachment[1].endswith('.jpeg'):
                            vk_attachment = upload.photo_messages(f'{config.attachments_dir}/{attachment[1]}')
                            vk_attachment = f"photo{vk_attachment[0]['owner_id']}_{vk_attachment[0]['id']}"
                            vk.messages.send(peer_id=to_id,random_id=0,attachment=vk_attachment,message=attachment[1])
                        ''' [27] Group authorization failed: method is unavailable with group auth.
                        elif attachment[1].endswith('.ogg'):
                            vk_attachment = upload.audio_message(audio=f'{config.attachments_dir}/{attachment[1]}',peer_id=to_id)
                            vk_attachment = f"audio{vk_attachment['audio_message']['owner_id']}_{vk_attachment['audio_message']['id']}"
                            vk.messages.send(peer_id=to_id,random_id=0,attachment=vk_attachment,message=attachment[1])
                        elif attachment[1].endswith('.mp3'):
                            vk_attachment = upload.audio(audio=f'{config.attachments_dir}/{attachment[1]}',artist=config.vk_group_tag,title=attachment[1])
                            vk_attachment = f"audio{vk_attachment[0]['owner_id']}_{vk_attachment[0]['id']}"
                            vk.messages.send(peer_id=to_id,random_id=0,attachment=vk_attachment,message=attachment[1])
                        elif attachment[1].endswith('.mp4'):
                            vk_attachment = upload.video(video_file=f'{config.attachments_dir}/{attachment[1]}', name=attachment[1])
                            vk_attachment = f"video{vk_attachment['owner_id']}_{vk_attachment['video_id']}"
                            vk.messages.send(peer_id=to_id,random_id=0,attachment=vk_attachment,message=attachment[1])
                        else:
                            vk_attachment = upload.document_message(doc=f'{config.attachments_dir}/{attachment[1]}',title=attachment[1])
                            vk_attachment = f"doc{vk_attachment['doc']['owner_id']}_{vk_attachment['doc']['id']}"
                            vk.messages.send(peer_id=to_id,random_id=0,attachment=vk_attachment,message=attachment[1])
                        '''
                    os.remove(f'{config.attachments_dir}/{attachment[1]}')
            except vk_api.exceptions.ApiError as e: logger.warning(f'error send to {to_service} {to_id}: {e}')
            except Exception as e: logger.error(e,exc_info=True)

# === new msg parser ===
async def msg_navigator(from_service, msg_obj):
    logger.debug(f'msg_obj: {str(msg_obj)}')
    try:
        attachment_list=[]

        # === tg parser ===
        if from_service == 'tg':
            to_service = 'vk'
            from_chat_id = int(msg_obj.chat.id)
            from_msg_text = msg_obj.text or msg_obj.caption or ''
            from_chat_is_private = msg_obj.chat.type == 'private'
            from_user_nick = f"{msg_obj.from_user.first_name} {msg_obj.from_user.last_name}" if msg_obj.from_user.last_name else msg_obj.from_user.first_name
            is_invite = False
            if msg_obj.new_chat_members: # invite check
                for user in msg_obj.new_chat_members:
                    if config.tg_bot_tag == user.username and int(config.tg_token.split(':')[0]) == user.id: is_invite = True
            # --- reply / forward parse ---
            reply_to_msg_text = getattr(msg_obj.reply_to_message, 'text', None)
            #if not reply_to_msg_text: reply_to_msg_text = getattr(msg_obj.reply_to_message, 'document', None)
            if msg_obj.forward_from or getattr(msg_obj, 'forward_sender_name', None) or getattr(msg_obj, 'forward_from_chat', None):
                forward_from_name='unknown'
                if getattr(msg_obj, 'forward_sender_name', None): forward_from_name={msg_obj.forward_sender_name}
                elif getattr(msg_obj.forward_from, 'first_name', None) and getattr(msg_obj.forward_from, 'last_name', None): forward_from_name=f'{msg_obj.forward_from.first_name} {msg_obj.forward_from.last_name}'
                elif getattr(msg_obj.forward_from, 'first_name', None): forward_from_name=msg_obj.forward_from.first_name
                elif getattr(msg_obj, 'forward_from_chat', None): forward_from_name=msg_obj.forward_from_chat.title
                from_user_nick += strings.msg_forward.format(forward_from_name=forward_from_name)
            # --- attachment parse --- [attachment_prefix, attachment_name, attachment_size]
            if msg_obj.document and not msg_obj.animation: 
                attachment_list.append([strings.msg_attachment_prefix_doc, msg_obj.document.file_name, msg_obj.document.file_size])
                if config.attachments_forward and msg_obj.document.file_size/1024/1024 < config.attachments_max_size_mb:
                    file=await tg_bot.get_file(msg_obj.document.file_id)
                    await tg_bot.download_file(file.file_path, f'{config.attachments_dir}/{msg_obj.document.file_name}')
            if msg_obj.animation: 
                file = await tg_bot.get_file(msg_obj.animation.file_id)
                file_name=f"gif{file.file_unique_id}.{file.file_path.split(".")[1]}"
                attachment_list.append([strings.msg_attachment_prefix_animation, file_name, file.file_size])
                if config.attachments_forward and file.file_size/1024/1024 < config.attachments_max_size_mb:
                    await tg_bot.download_file(file.file_path, f'{config.attachments_dir}/{file_name}')
            if msg_obj.photo:
                file = await tg_bot.get_file(msg_obj.photo[-1].file_id)
                file_name=f"photo{file.file_unique_id}.{file.file_path.split(".")[1]}"
                attachment_list.append([strings.msg_attachment_prefix_image, file_name, file.file_size])
                if config.attachments_forward and file.file_size/1024/1024 < config.attachments_max_size_mb:
                    await tg_bot.download_file(file.file_path, f'{config.attachments_dir}/{file_name}')
            if msg_obj.sticker:
                file = await tg_bot.get_file(msg_obj.sticker.file_id)
                if file.file_path.split(".")[1] == 'webp': file_name = f"sticker{file.file_unique_id}.{file.file_path.split(".")[1]}"
                elif file.file_path.split(".")[1] == 'tgs': file_name = f"sticker_animated{file.file_unique_id}.{file.file_path.split(".")[1]}"
                elif file.file_path.split(".")[1] == 'webm': file_name = f"sticker_video{file.file_unique_id}.{file.file_path.split(".")[1]}"
                else: file_name = f"sticker_unknown{file.file_unique_id}.{file.file_path.split(".")[1]}"
                attachment_list.append([msg_obj.sticker.emoji, file_name, file.file_size])
                if config.attachments_forward and msg_obj.sticker.file_size/1024/1024 < config.attachments_max_size_mb:
                    await tg_bot.download_file(file.file_path, f"{config.attachments_dir}/{file_name}")
            if msg_obj.audio:
                file = await tg_bot.get_file(msg_obj.audio.file_id)
                file_name=f"audio{file.file_unique_id}.{file.file_path.split(".")[1]}"
                attachment_list.append([strings.msg_attachment_prefix_audio, file_name, file.file_size])
                if config.attachments_forward and file.file_size/1024/1024 < config.attachments_max_size_mb:
                    await tg_bot.download_file(file.file_path, f'{config.attachments_dir}/{file_name}')
            if msg_obj.voice:
                attachment_list.append([strings.msg_attachment_prefix_voice, f"voice{msg_obj.voice.file_unique_id}.ogg", msg_obj.voice.file_size])
                if config.attachments_forward and msg_obj.voice.file_size/1024/1024 < config.attachments_max_size_mb:
                    file = await tg_bot.get_file(msg_obj.voice.file_id) 
                    await tg_bot.download_file(file.file_path, f"{config.attachments_dir}/voice{msg_obj.voice.file_unique_id}.ogg")
            if msg_obj.video_note:
                attachment_list.append([strings.msg_attachment_prefix_video_note, f"video_note{msg_obj.video_note.file_unique_id}.mp4", msg_obj.video_note.file_size])
                if config.attachments_forward and msg_obj.video_note.file_size/1024/1024 < config.attachments_max_size_mb:
                    file = await tg_bot.get_file(msg_obj.video_note.file_id) 
                    print(file)
                    await tg_bot.download_file(file.file_path, f"{config.attachments_dir}/video_note{msg_obj.video_note.file_unique_id}.mp4")


        # === vk parser ===
        elif from_service == 'vk':
            to_service = 'tg'
            from_chat_id = int(msg_obj.get('peer_id', 0))
            from_msg_text = msg_obj.get('text', '')
            from_chat_is_private = False if int(from_chat_id) >= 2000000000 else True
            from_user_profile_info=vk_api.VkApi(token=config.vk_user_token).get_api().users.get(user_ids=msg_obj.get('from_id'))[0]
            from_user_nick = f"{from_user_profile_info['first_name']} {from_user_profile_info['last_name']}"
            is_invite = False 
            if msg_obj.get('action'): # invite check
                if msg_obj.get('action').get('type') == "chat_invite_user": is_invite = True
            # --- reply / forward parse ---
            reply_to_msg_text = msg_obj.get('reply_message', {}).get('text') # не видит ответ на пересланые сообщения 
            for fwd_msg in msg_obj.get('fwd_messages', []):
                text = fwd_msg.get('text') if fwd_msg.get('text') else '[unknown_message_type]'
                forward_from_name=fwd_msg.get('from_id')
                from_msg_text += f"\n{strings.msg_forward.format(forward_from_name=forward_from_name)}\n{text}"
            # --- attachment parse --- [attachment_prefix, attachment_name, attachment_size]
            if msg_obj.get('attachments'):
                for attachment in msg_obj.get('attachments'): 
                    if attachment['type']=='photo':
                        file_name = f'photo{attachment['photo']['id']}.jpg'
                        file = requests.get(max(attachment["photo"]["sizes"], key=lambda s: s["width"])["url"])
                        with open(f'{config.attachments_dir}/{file_name}', "wb") as f: f.write(file.content)
                        file_size = os.stat(f'{config.attachments_dir}/{file_name}').st_size
                        attachment_list.append([strings.msg_attachment_prefix_image, file_name, file_size])

                    if attachment.get('title'): pass #attachment_list.append(attachment.get('title'))
                    else: pass #attachment_list.append(attachment.get('type')) 

    except Exception as e: logger.error(e,exc_info=True)
    logger.info(f'msg from {from_service} {from_chat_id}: {from_msg_text}')

    # === command / invite parse ===
    command_answer = await commands.if_command(from_service,from_msg_text,from_chat_id,from_chat_is_private)
    if command_answer: 
        return await message_bus.put((from_service, command_answer, from_chat_id, None))
    elif is_invite: 
        logger.info(f'bot invited to {from_service} {from_chat_id}')
        return await message_bus.put((from_service, strings.cmd_start_public_chat, from_chat_id, None))

    # === setting message to send ===
    if True: 
        this_service_name, other_service_name, other_service, other_service_bot_link = await commands.get_strings(from_service)
        # --- connect check ---
        connected_to_id = await db.get_connected_chat(from_service,from_chat_id) # чек подключения
        if not connected_to_id: # нет подключения вообще
            if from_chat_is_private: await message_bus.put((from_service, strings.cmd_mirror_no_connect.format(time=strings.time_now,this_service_name=this_service_name,other_service_name=other_service_name,other_service_bot_link=other_service_bot_link,this_chat_id=from_chat_id), from_chat_id, None))
            return logger.debug(f'чат {from_service} {from_chat_id} не подключен к чату {to_service}')
        if await db.get_connected_chat(to_service,connected_to_id) != from_chat_id: # нет ответного подключения
            if from_chat_is_private: await message_bus.put((from_service, strings.cmd_mirror_no_connect_mutually.format(time=strings.time_now,this_service_name=this_service_name,other_service_name=other_service_name,other_service_bot_link=other_service_bot_link,this_chat_id=from_chat_id,connected_to_id=connected_to_id), from_chat_id, None))
            return logger.info(f'чат {from_service} {from_chat_id} подключен к чату {to_service} {connected_to_id}, который не подключен в ответ')
        # --- nick ---
        from_msg_text = f'{strings.msg_nick_prefix} {from_user_nick}\n{from_msg_text}'
        if len(from_msg_text)>config.message_max_len: from_msg_text=from_msg_text[:config.message_max_len]
        # --- replys ---
        if reply_to_msg_text:
            if reply_to_msg_text.startswith(strings.msg_reply_prefix): reply_to_msg_text=reply_to_msg_text[reply_to_msg_text.find('\n')+1:] # обрезка реплаев в реплаях
            if reply_to_msg_text.startswith(strings.msg_nick_prefix): reply_to_msg_text=reply_to_msg_text[reply_to_msg_text.find('\n')+1:] # обрезка ников в реплаях
            if len(reply_to_msg_text)>config.message_reply_max_len: reply_to_msg_text = reply_to_msg_text[:config.message_reply_max_len]+'...' # обрезка длины
            reply_to_msg_text = reply_to_msg_text.replace("\n", " ")
            from_msg_text = f'{strings.msg_reply_prefix} {reply_to_msg_text}\n{from_msg_text}'
        # --- attachments --- [attachment_prefix, attachment_name, attachment_size]
        if attachment_list: 
            for attachment in attachment_list:
                from_msg_text += f'\n{attachment[0]} {attachment[1]} ({round(attachment[2]/1024/1024,2)}МБ)'
        logger.info(f'└ send to {to_service} {connected_to_id}')
        await message_bus.put((to_service, from_msg_text, connected_to_id, attachment_list)) 

# === TG catcher ===
tg_bot = Bot(token=config.tg_token)
dp = Dispatcher(storage=MemoryStorage())
@dp.message()
async def handle_telegram_message(message: Message):
    await msg_navigator('tg',message)
# === VK catcher ===
def run_vk_bot_polling(loop):
    vk_session = vk_api.VkApi(token=config.vk_user_token)
    try:
        for event in VkBotLongPoll(vk_session, config.vk_group_id).listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                if event.object.message['from_id'] == -config.vk_group_id: continue  # пропускаем сообщения от самого бота
                asyncio.run_coroutine_threadsafe(msg_navigator('vk', event.object.message), loop)
    except Exception as e:
        logger.error(e, exc_info=True)
        time.sleep(3)
        run_vk_bot_polling(loop)  # перезапуск при ошибке

# === MAIN ===
async def main():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_vk_bot_polling, args=(loop,), daemon=True).start() 
    asyncio.create_task(msg_send())
    await db.initialization()
    if config.attachments_forward: os.makedirs(config.attachments_dir, exist_ok=True)
    logger.debug("bot started")
    await dp.start_polling(tg_bot)
    logger.debug("bot stopped")
if __name__ == "__main__":
    asyncio.run(main())
