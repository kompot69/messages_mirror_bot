bot_version=[1,1]
import asyncio, threading, logging, vk_api, requests, subprocess, tempfile, json, os, yt_dlp
from datetime import datetime
from io import BytesIO
from collections import defaultdict
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.utils.media_group import MediaGroupBuilder
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.upload import VkUpload
import config, commands, db, strings

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s %(levelname)s [%(filename)s %(funcName)s]: %(message)s")
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler(f"{__name__}.log", mode='w')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

buttons_main=[
    ['link', 'FAQ', 'https://'],
    ['payload', 'disconnect'],
    ['payload', 'connect_to', 'id'],
    ['payload', 'stats'],
    ['payload', 'update']
    ]


# === очередь отправки сообщений ===
message_buffer = defaultdict(list)
message_buffer_timers = {} 
message_buffer_queue = asyncio.Queue()
async def message_buffer_worker():     # добавлять к вложениям group id (только тг > вк)
    while True:
        service_to, message, to_id, attachments = await message_buffer_queue.get()
        if not attachments or len(attachments[0]) < 5: # если без вложений или вложение не групповое  
            await message_send_queue.put((service_to, message, to_id, attachments))
            continue
        group_id = attachments[0][4]
        if not group_id: # group_id некорректен 
            await message_send_queue.put((service_to, message, to_id, attachments))
            continue
        logger.debug(f'new attachments for group_id {group_id}: {attachments}')

        if group_id in message_buffer: 
            existing_attachments = message_buffer[group_id][3] # add new attachments to old
            existing_attachments.extend(attachments)
            attachments = existing_attachments
            if message[2] == '': message = message_buffer[group_id][1]
            message_buffer[group_id] = [service_to, message, to_id, existing_attachments]
        else:
            message_buffer[group_id] = [service_to, message, to_id, list(attachments)]

        if group_id in message_buffer_timers: message_buffer_timers[group_id].cancel() # cancel old timer
        message_buffer_timers[group_id] = asyncio.create_task(message_buffer_timer(group_id)) # start new timer

async def message_buffer_timer(group_id: str):
    try:
        await asyncio.sleep(config.attachments_buffer_timeout)
        logger.debug(f'its time to send attachments group: {group_id}')
        if group_id in message_buffer:
            service_to, message, to_id, attachments = message_buffer[group_id]
            await message_send_queue.put((service_to, message, to_id, attachments))
            del message_buffer[group_id]
            del message_buffer_timers[group_id]
    except asyncio.CancelledError: pass
    except Exception as e: 
        logger.error(f'timer error for group {group_id}: {e}', exc_info=True)
        del message_buffer[group_id]

message_send_queue = asyncio.Queue()
async def message_sender(): 
    chat_last_send = {} # [nick,time]
    while True:
        service_to, message, to_id, attachments = await message_send_queue.get()
        logger.info(f'sending message to {service_to} {to_id}: {message} {attachments}')

        if isinstance(message, list):
            last = chat_last_send.get(service_to+str(to_id))
            if last: 
                if message[1] == last[0] and (datetime.now()-last[1]).total_seconds()/60 <= config.nick_repeat_after_min: 
                    message_text = message[0]+message[2]
                else: message_text = message[0]+message[1]+message[2]
            else: message_text = message[0]+message[1]+message[2]
            chat_last_send[service_to+str(to_id)] = [message[1],datetime.now()]
        else: message_text = message

        if service_to == "tg": 
            try: 
                if 'tread' in to_id: to_id, tread = to_id.split('tread')
                else: tread = None
                
                if message_text and not attachments: 
                    await tg_bot.send_message(to_id, message_text, message_thread_id=tread) 
                
                elif attachments:
                    group_id = False
                    if len(attachments[0])>4 and len(attachments)>1: 
                        if attachments[0][4]: group_id = attachments[0][4] 
                    if group_id: media_group = MediaGroupBuilder(caption=message_text)

                    for attachment in attachments: # [attachment_type, file_name, file_size, bytes]
                        if attachment[3] is None and attachment[0] != 'wall':
                            if attachment[2] is not None and attachment[2] != 0:
                                await tg_bot.send_message(to_id, f'{message_text+"\n" if message_text else ""}{strings.attachments_emoji[attachment[0]]} {attachment[1]} ({round(attachment[2]/1024/1024,2)}МБ)', message_thread_id=tread)
                            else:
                                await tg_bot.send_message(to_id, f'{message_text+"\n" if message_text else ""}{strings.attachments_emoji[attachment[0]]} {attachment[1]}', message_thread_id=tread)
                        else:
                            try:
                                if attachment[0] == 'photo': 
                                    if group_id: media_group.add_photo(media=attachment[3])
                                    else: await tg_bot.send_photo(to_id, attachment[3], caption=message_text, message_thread_id=tread)
                                elif attachment[0] == 'video': 
                                    if group_id: media_group.add_video(media=attachment[3])
                                    else: await tg_bot.send_video(to_id, attachment[3], caption=message_text, message_thread_id=tread)
                                elif attachment[0] == 'audio': 
                                    await tg_bot.send_audio(to_id, attachment[3], caption=message_text, message_thread_id=tread)
                                elif attachment[0] == 'doc': 
                                    if group_id: media_group.add_document(media=attachment[3])
                                    else: await tg_bot.send_document(to_id, attachment[3], caption=message_text, message_thread_id=tread)
                                elif attachment[0] == 'sticker' or attachment[0] == 'graffiti' : 
                                    await tg_bot.send_sticker(to_id, attachment[3], message_thread_id=tread)
                                elif attachment[0] == 'audio_message': 
                                    await tg_bot.send_voice(to_id, attachment[3], message_thread_id=tread)
                                elif attachment[0] == 'video_message': 
                                    await tg_bot.send_video_note(to_id, attachment[3], message_thread_id=tread)
                                elif attachment[0] == 'location': 
                                    if message_text: await tg_bot.send_message(to_id, message_text, message_thread_id=tread) 
                                    await tg_bot.send_location(to_id, latitude=attachment[3][0], longitude=attachment[3][1], message_thread_id=tread)
                                elif attachment[0] == 'wall': 
                                    await tg_bot.send_message(to_id, f'{message_text+"\n" if message_text else ""}{strings.attachments_emoji["wall"]} {attachment[1]}', message_thread_id=tread)
                                elif attachment[0] == 'story': 
                                    await tg_bot.send_message(to_id, f'{message_text+"\n" if message_text else ""}{strings.attachments_emoji["story"]} {attachment[1]}', message_thread_id=tread)
                                elif attachment[0] == 'poll': 
                                    poll = f'{message_text+"\n" if message_text else ""}{strings.attachments_emoji["poll"]} {attachment[1]}'
                                    for option in attachment[3]: poll += f'\n ● {option}'
                                    await tg_bot.send_message(to_id, poll, message_thread_id=tread)
                                else: 
                                    await tg_bot.send_message(to_id, f'{message_text+"\n" if message_text else ""}{strings.attachments_emoji["unknown"]} {attachment[1]}', message_thread_id=tread)
                            except Exception as e: 
                                logger.error(e, exc_info=True)
                                await tg_bot.send_message(to_id, f'{message_text+"\n" if message_text else ""}{strings.attachments_emoji[attachment[0]]} {attachment[1]}', message_thread_id=tread)
                    if group_id: 
                        await tg_bot.send_media_group(to_id, media=media_group.build())

            except TelegramForbiddenError as e: logger.warning(f'error send to {service_to} {to_id}: {e}')
            except Exception as e: logger.error(e,exc_info=True)

        elif service_to == "vk": 
            try: 
                if not attachments: vk_group_api.messages.send( peer_id=to_id, message=message_text, random_id=0)
                vk_attachments = []
                group_id = False
                if attachments: # [attachment_type, file_name, file_size, bytes]
                    if len(attachments[0])>4 and len(attachments)>1: 
                        if attachments[0][4]: group_id = attachments[0][4] 
                    for attachment in attachments:                         
                        # отправка вложений (текст)
                        if attachment[0] == 'location': 
                            vk_group_api.messages.send( peer_id=to_id, lat=attachment[3][0], long=attachment[3][1], random_id=0)
                        elif attachment[0] == 'poll': 
                            poll = f'{strings.attachments_emoji["poll"]} {attachment[1]}'
                            for option in attachment[3]: poll += f'\n ● {option}'
                            vk_group_api.messages.send( peer_id=to_id, message=poll, random_id=0 )
                        elif attachment[0] == 'contact':
                            vk_group_api.messages.send( peer_id=to_id, message = f'{strings.attachments_emoji["contact"]} {attachment[1]}\n{attachment[3]}', random_id=0 )
                        else: # отправка вложений (файлы)
                            if attachment[2] is not None and attachment[2] != 0 and isinstance(attachment[2], (int, float)): 
                                attachment_size = f'({round(attachment[2]/1024/1024,2)}МБ)' 
                            else: attachment_size = ''
                            if attachment[3] is None: 
                                vk_attachment = None
                            elif attachment[0] == 'photo' or attachment[0] == 'sticker': 
                                vk_attachment = await vk_attachment_upload(file_photo=attachment[3])
                            elif attachment[0] == 'video' or attachment[0] == 'video_message': 
                                vk_attachment = await vk_attachment_upload(file_video=attachment[3], name=attachment[1], video_description=strings.attachment_video_description.format(sender_name=message[1]+message[2]))
                            elif attachment[0] == 'story': 
                                vk_attachment = None
                            elif attachment[0] == 'doc': 
                                vk_attachment = await vk_attachment_upload(file_doc=attachment[3], to_id=to_id, name=attachment[1])
                            elif attachment[0] == 'gif': 
                                vk_attachment = await vk_attachment_upload(file_gif=attachment[3], to_id=to_id, name=attachment[1])
                            elif attachment[0] == 'audio': 
                                vk_attachment = await vk_attachment_upload(file_audio=attachment[3], to_id=to_id, name=attachment[1])
                            elif attachment[0] == 'audio_message': 
                                vk_attachment = await vk_attachment_upload(file_audio_message=attachment[3], to_id=to_id, name=attachment[1])
                            else: 
                                vk_attachment = None

                            if not vk_attachment:
                                attachments_emoji = strings.attachments_emoji.get(attachment[0], strings.attachments_emoji["unknown"])
                                vk_group_api.messages.send( peer_id=to_id, message=f'{message_text+"\n" if message_text and not group_id else ""}{attachments_emoji} {attachment[1]} {attachment_size}', random_id=0)
                            elif group_id: vk_attachments.append(vk_attachment)
                            elif message_text: vk_group_api.messages.send(peer_id=to_id, message=message_text, random_id=0, attachment=vk_attachment)
                            else: vk_group_api.messages.send(peer_id=to_id, random_id=0, attachment=vk_attachment)
                if group_id:
                    if not message_text: vk_group_api.messages.send( peer_id=to_id, random_id=0, attachment=vk_attachments)
                    else: vk_group_api.messages.send( peer_id=to_id, message=message_text, random_id=0, attachment=vk_attachments)

            except vk_api.exceptions.ApiError as e: logger.warning(f'error send to {service_to} {to_id}: {e}', exc_info=True)
            except Exception as e: logger.error(e, exc_info=True)

async def message_navigator(service0, msg_obj):
    try:
        logger.debug(f'message from {service0} catched: {str(msg_obj)}')
        service0_name, service1_name, service1, service1_bot_link = await commands.get_strings(service0)
        # parsing
        if service0 == 'tg': service0_chat_id, service0_user_id, service0_user_nick, service0_msg_text, reply_to_msg_text, attachment_list, service0_chat_is_private, is_invite = await tg_parse_message(msg_obj)
        elif service0 == 'vk': service0_chat_id, service0_user_id, service0_user_nick, service0_msg_text, reply_to_msg_text, attachment_list, service0_chat_is_private, is_invite = await vk_parse_message(msg_obj)
        logger.info(f"new message from {service0} {service0_chat_id}: {service0_msg_text.replace(chr(10), '  ')} {str(attachment_list) if attachment_list else ''}")
        # command / invite answer 
        command_answer = await commands.if_command(service0, service0_msg_text, service0_chat_id, service0_chat_is_private)
        if command_answer is not None and command_answer != False: 
            return await message_send_queue.put((service0, command_answer, service0_chat_id, None))
        elif is_invite: 
            logger.info(f'bot was invited to {service0_chat_id} {service0} chat')
            return await message_send_queue.put((service0, strings.cmd_start_public_chat, service0_chat_id, None))
        # connect check 
        service1_chat_id = await db.get_connected_chat(service0, service0_chat_id)
        if not service1_chat_id: # нет подключения вообще
            if service0_chat_is_private: await message_send_queue.put((service0, strings.cmd_mirror_no_connect.format(time=strings.time_now,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id), service0_chat_id, None))
            return logger.debug(f'чат {service0} {service0_chat_id} не подключен к чату {service1}')
        if await db.get_connected_chat(service1, service1_chat_id) != service0_chat_id: # нет ответного подключения
            if service0_chat_is_private: await message_send_queue.put((service0, strings.cmd_mirror_no_connect_mutually.format(time=strings.time_now,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id,service1_chat_id=service1_chat_id), service0_chat_id, None))
            return logger.debug(f'чат {service0} {service0_chat_id} подключен к чату {service1} {service1_chat_id}, который не подключен в ответ')
        # replys 
        if reply_to_msg_text:
            if reply_to_msg_text.startswith(strings.msg_reply_prefix): reply_to_msg_text=reply_to_msg_text[reply_to_msg_text.find('\n')+1:] # обрезка реплаев в реплаях
            if reply_to_msg_text.startswith(strings.msg_nick_prefix): reply_to_msg_text=reply_to_msg_text[reply_to_msg_text.find('\n')+1:] # обрезка ников в реплаях
            if len(reply_to_msg_text)>config.message_reply_max_len: reply_to_msg_text = reply_to_msg_text[:config.message_reply_max_len-3]+'...' # обрезка длины
            reply_to_msg_text = reply_to_msg_text.replace("\n", " ")
            reply_to_msg_text = f'{strings.msg_reply_prefix} {reply_to_msg_text}\n'
        # sending
        if len(service0_msg_text) > config.message_max_len: service0_msg_text=service0_msg_text[:config.message_max_len]+"\n [ ... ]"
        message = [reply_to_msg_text or '', f'{strings.msg_nick_prefix} {service0_user_nick}\n', service0_msg_text]
        await message_buffer_queue.put((service1, message, service1_chat_id, attachment_list)) 
    except Exception as e: logger.error(e, exc_info=True)


# = = = = = TG = = = = =
async def tg_parse_message(msg_obj):
    try:
        attachment_list=[]
        tg_chat_id = str(msg_obj.chat.id)
        tg_user_id = msg_obj.from_user.id
        if msg_obj.message_thread_id: tg_chat_id += f'tread{str(msg_obj.message_thread_id)}'
        tg_msg_text = msg_obj.text or msg_obj.caption or ''
        tg_chat_is_private = msg_obj.chat.type == 'private'
        tg_user_nick = f"{msg_obj.from_user.first_name} {msg_obj.from_user.last_name}" if msg_obj.from_user.last_name else msg_obj.from_user.first_name
        is_invite = False
        if msg_obj.new_chat_members: # invite check
            for user in msg_obj.new_chat_members:
                if config.tg_bot_tag == user.username and int(config.tg_token.split(':')[0]) == user.id: is_invite = True
                else: tg_msg_text = strings.join_in_chat
        # reply / forward parse 
        reply_to_msg_text = getattr(msg_obj.reply_to_message, 'text', None) or getattr(msg_obj.reply_to_message, 'caption', None)
        if getattr(msg_obj, 'reply_to_message') and reply_to_msg_text is None: 
            if msg_obj.reply_to_message.photo: reply_to_msg_text = f"{strings.attachments_emoji['photo']} photo"
            if msg_obj.reply_to_message.video: reply_to_msg_text = f"{strings.attachments_emoji['video']} video"
            if msg_obj.reply_to_message.animation: reply_to_msg_text = f"{strings.attachments_emoji['gif']} gif"
            if msg_obj.reply_to_message.audio: reply_to_msg_text = f"{strings.attachments_emoji['audio']} audio"
            if msg_obj.reply_to_message.document: reply_to_msg_text = f"{strings.attachments_emoji['doc']} document"
            if msg_obj.reply_to_message.sticker: reply_to_msg_text = f"{strings.attachments_emoji['sticker']} sticker"
            if msg_obj.reply_to_message.voice: reply_to_msg_text = f"{strings.attachments_emoji['audio']} audio_message"
            if msg_obj.reply_to_message.video_note: reply_to_msg_text = f"{strings.attachments_emoji['video_message']} video_message"
            if msg_obj.reply_to_message.story: reply_to_msg_text = f"{strings.attachments_emoji['story']} story"
            if msg_obj.reply_to_message.location: reply_to_msg_text = f"{strings.attachments_emoji['location']} location"
            if msg_obj.reply_to_message.poll: reply_to_msg_text = f"{strings.attachments_emoji['poll']} poll"
            if msg_obj.reply_to_message.contact: reply_to_msg_text = f"{strings.attachments_emoji['contact']} contact"
        if msg_obj.forward_from or getattr(msg_obj, 'forward_sender_name', None) or getattr(msg_obj, 'forward_from_chat', None):
            forward_from_name='unknown'
            if getattr(msg_obj, 'forward_sender_name', None): forward_from_name = msg_obj.forward_sender_name
            elif getattr(msg_obj.forward_from, 'first_name', None) and getattr(msg_obj.forward_from, 'last_name', None): forward_from_name=f'{msg_obj.forward_from.first_name} {msg_obj.forward_from.last_name}'
            elif getattr(msg_obj.forward_from, 'first_name', None): forward_from_name=msg_obj.forward_from.first_name
            elif getattr(msg_obj, 'forward_from_chat', None): forward_from_name=msg_obj.forward_from_chat.title
            tg_user_nick += strings.msg_forward.format(forward_from=forward_from_name)
        # attachment parse [attachment_type, file_name, file_size, bytes]
        if msg_obj.photo: 
            try: 
                file = None
                file_size = msg_obj.photo[-1].file_size
                file_name = f"photo{msg_obj.photo[-1].file_unique_id}"
                if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                    file = BytesIO()
                    file_obj = await tg_bot.get_file(msg_obj.photo[-1].file_id)
                    file_name = f"photo{file_obj.file_unique_id}.{file_obj.file_path.split('.')[1]}"
                    await tg_bot.download_file(file_obj.file_path, destination=file)
                    file.seek(0)
            except Exception as e: logger.warning(e, exc_info=True)
            if msg_obj.media_group_id: attachment_list.append(['photo', file_name, file_size, file, msg_obj.media_group_id])
            else: attachment_list.append(['photo', file_name, file_size, file])
        if msg_obj.video: 
            try: 
                file = None
                file_size = msg_obj.video.file_size
                file_name = msg_obj.video.file_name or f"video{msg_obj.video.file_unique_id}"
                if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                    file = BytesIO()
                    file_obj = await tg_bot.get_file(msg_obj.video.file_id)
                    file_name = msg_obj.video.file_name or f"video{file_obj.file_unique_id}.{file_obj.file_path.split('.')[1]}"
                    await tg_bot.download_file(file_obj.file_path, destination=file)
                    file.seek(0)
            except TelegramBadRequest as e: logger.warning(f'cannot get video from tg: {e}')
            except Exception as e: logger.warning(e, exc_info=True)
            if msg_obj.media_group_id: attachment_list.append(['video', file_name, file_size, file, msg_obj.media_group_id])
            else: attachment_list.append(['video', file_name, file_size, file])
        if msg_obj.animation: 
            file_obj = await tg_bot.get_file(msg_obj.animation.file_id)
            file_name = msg_obj.animation.file_name or f"gif{msg_obj.animation.file_unique_id}.{msg_obj.document.mime_type.split('/')[1]}"
            file_size = msg_obj.animation.file_size
            if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                try: 
                    file = BytesIO()
                    await tg_bot.download_file(file_obj.file_path, destination=file)
                    file.seek(0)
                except Exception as e:
                    logger.warning(e, exc_info=True)
                    file = None
            else: file = None
            attachment_list.append(['gif', file_name, file_size, file])
        if msg_obj.audio:
            file_obj = await tg_bot.get_file(msg_obj.audio.file_id)
            file_name = msg_obj.audio.file_name
            file_size = msg_obj.audio.file_size
            if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                try: 
                    file = BytesIO()
                    await tg_bot.download_file(file_obj.file_path, destination=file)
                    file.seek(0)
                except Exception as e:
                    logger.warning(e, exc_info=True)
                    file = None
            else: file = None
            attachment_list.append(['audio', file_name, file_size, file])
        if msg_obj.document and not msg_obj.animation: 
            file_obj = await tg_bot.get_file(msg_obj.document.file_id)
            file_name = msg_obj.document.file_name
            file_size = msg_obj.document.file_size
            if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                try: 
                    file = BytesIO()
                    await tg_bot.download_file(file_obj.file_path, destination=file)
                    file.seek(0)
                except Exception as e:
                    logger.warning(e, exc_info=True)
                    file = None
            else: file = None
            att_type = 'gif' if file_name.endswith('.gif') else 'doc'
            if msg_obj.media_group_id: attachment_list.append([att_type, file_name, file_size, file, msg_obj.media_group_id])
            else: attachment_list.append([att_type, file_name, file_size, file])
        if msg_obj.sticker:
            file_obj = await tg_bot.get_file(msg_obj.sticker.file_id)
            file_name = f"sticker{msg_obj.sticker.file_unique_id}.{file_obj.file_path.split('.')[1]}" 
            file_size = msg_obj.sticker.file_size
            file_type='sticker'
            if msg_obj.sticker.is_animated: file_type='doc'
            if msg_obj.sticker.is_video: file_type='video'
            if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                try: 
                    file = BytesIO()
                    await tg_bot.download_file(file_obj.file_path, destination=file)
                    file.seek(0)
                except Exception as e:
                    logger.warning(e, exc_info=True)
                    file = None
            else: file = None
            attachment_list.append([file_type, file_name, file_size, file])
        if msg_obj.voice: 
            file_obj = await tg_bot.get_file(msg_obj.voice.file_id)
            file_name = f"audio_message{msg_obj.voice.file_unique_id}.ogg" 
            file_size = msg_obj.voice.file_size
            if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                try: 
                    file = BytesIO()
                    await tg_bot.download_file(file_obj.file_path, destination=file)
                    file.seek(0)
                except Exception as e:
                    logger.warning(e, exc_info=True)
                    file = None
            else: file = None
            attachment_list.append(['audio_message', file_name, file_size, file])
        if msg_obj.video_note: 
            file_obj = await tg_bot.get_file(msg_obj.video_note.file_id)
            file_name = f"video_message{msg_obj.video_note.file_unique_id}.mp4" 
            file_size = msg_obj.video_note.file_size
            if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                try: 
                    file = BytesIO()
                    await tg_bot.download_file(file_obj.file_path, destination=file)
                    file.seek(0)
                except Exception as e:
                    logger.warning(e, exc_info=True)
                    file = None
            else: file = None
            attachment_list.append(['video_message', file_name, file_size, file])
        if msg_obj.story:
            file_name = strings.attachment_story.format(first_name=msg_obj.story.chat.first_name, last_name=msg_obj.story.chat.last_name)
            file_size = None
            attachment_list.append(['story', file_name, file_size, None])
        if msg_obj.location: 
            attachment_list.append(['location', 'location', 0, [msg_obj.location.latitude, msg_obj.location.longitude]])
        if msg_obj.poll: 
            options=[]
            for option in msg_obj.poll.options: options.append(option.text)
            attachment_list.append(['poll', msg_obj.poll.question, 0, options])
        if msg_obj.contact: 
            name = ''
            if msg_obj.contact.first_name is not None: name += msg_obj.contact.first_name
            if msg_obj.contact.last_name is not None: name += msg_obj.contact.last_name
            attachment_list.append(['contact', name, 0, msg_obj.contact.phone_number])

        return tg_chat_id, tg_user_id, tg_user_nick, tg_msg_text, reply_to_msg_text, attachment_list, tg_chat_is_private, is_invite 

    except Exception as e: logger.error(e, exc_info=True)


# = = = = = VK = = = = =

def vk_get_name(id):
    try:
        if id > 0: 
            user = vk_group_api.users.get(user_ids=user)
            return f"{user[0]['first_name']} {user[0]['last_name']}"
        else: 
            return vk_group_api.groups.getById(group_id=abs(user))[0]['name']
    except Exception as e:
        logger.warning(f'error while getting name for id {id}: {e}')
        return '[неизвестно]'
    
async def vk_attachment_upload(retry=False, name=None, to_id=None, video_description=None, file_photo=None, file_video=None, file_gif=None, file_doc=None, file_audio=None, file_audio_message=None):
    try:
        if file_photo: 
            photo = vk_upload.photo_messages(file_photo)
            return f"photo{photo[0]['owner_id']}_{photo[0]['id']}"
        elif file_video: 
            with tempfile.NamedTemporaryFile() as temp_file:
                file_buffer=file_video
                file_buffer.seek(0)
                temp_file.write(file_buffer.read())
                temp_file.flush()
                upload_server = vk_user_api.video.save(name=name, description=video_description, group_id=config.vk_group_id, wallpost=0, is_private=1, privacy_comment='nobody')
                with open(temp_file.name, 'rb') as file: response = requests.post(upload_server['upload_url'], files={'video_file': file})
                video=json.loads(response.text)
            return f"video{video['owner_id']}_{video['video_id']}"
        elif file_doc or file_gif:
            file_obj = file_doc if file_doc else file_gif
            file_obj.seek(0)
            upload_url = vk_group_api.docs.getMessagesUploadServer(peer_id=to_id)['upload_url']
            if file_gif and name.endswith('.mp4'):
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_mp4:
                    temp_mp4.write(file_obj.getvalue())
                    process = subprocess.run(["ffmpeg","-i",temp_mp4.name,"-an","-sn","-dn","-t","60","-filter_complex","[0:v]fps=15,scale=320:-1:flags=bilinear,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=2","-loop", "0","-f", "gif","pipe:1",], input=file_obj.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                file_obj = BytesIO(process.stdout)
                if os.path.exists(temp_mp4.name): os.remove(temp_mp4.name)
                name = name[:-4] + '.gif'
                file_obj.seek(0)
            r = requests.post(upload_url, files={'file': (name, file_obj)})
            result = r.json()
            if 'file' in result:
                att = vk_group_api.docs.save(file=result['file'])['doc']
                return f"doc{att['owner_id']}_{att['id']}"
            else: raise ValueError(f'doc/gif upload to vk error: {result}')
        elif file_audio or file_audio_message: 
            file_obj = file_audio if file_audio else file_audio_message
            file_obj.seek(0)
            upload_url = vk_group_api.docs.getMessagesUploadServer(type='audio_message', peer_id=to_id)['upload_url']
            r = requests.post(upload_url, files={'file': (name, file_obj)})
            result = r.json()
            if 'file' in result:
                att = vk_group_api.docs.save(file=result['file'])['audio_message']
                return f"audio_message{att['owner_id']}_{att['id']}"
            else: raise ValueError(f'audio/audio_message upload to vk error: {result}')
    
    except subprocess.CalledProcessError as e: 
        logger.error(f"FFmpeg error: {e.stderr.decode()}")  # <-- Лог ошибки
    except Exception as e: 
        logger.error(e, exc_info=True)
        if not retry:
            await asyncio.sleep(1)
            args = {'name': name, 'to_id': to_id, 'video_description': video_description, 'file_photo': file_photo, 'file_video': file_video, 'file_gif': file_gif, 'file_doc': file_doc, 'file_audio': file_audio, 'file_audio_message': file_audio_message}
            args = {k: v for k, v in args.items() if v is not None}
            return await vk_attachment_upload(retry=True,**args)
    

async def vk_parse_message(msg_obj, fwd_msg_parsing=False):
    try:
        vk_chat_id = int(msg_obj.get('peer_id', 0))
        vk_chat_is_private = False if vk_chat_id >= 2000000000 else True
        vk_msg_text = msg_obj.get('text', '')
        vk_user_id = msg_obj.get('from_id')
        vk_user_info = vk_group_api.users.get(user_ids=vk_user_id)
        if vk_user_info: vk_user_nick = f"{vk_user_info[0]['first_name']} {vk_user_info[0]['last_name']}"
        else: vk_user_nick = vk_group_api.groups.getById(group_id=abs(vk_user_id))[0]['name']
        attachment_list=[]
        # --- action parse --- 
        is_invite = False 
        if msg_obj.get('action'): 
            action_type = msg_obj.get('action').get('type')
            if action_type == "chat_invite_user": 
                if msg_obj['action']['member_id'] == -config.vk_group_id: is_invite = True
                else: vk_msg_text = strings.added_in_chat.format(added_user=vk_get_name(msg_obj['action']['member_id']))
            elif action_type == "chat_kick_user": 
                vk_msg_text = strings.kicked_from_chat.format(kicked_user=vk_get_name(msg_obj['action']['member_id']))
            elif action_type == "chat_title_update":
                vk_msg_text = strings.new_chat_name.format(new_chat_name=msg_obj['action']['text'])
            elif action_type == "chat_title_update":
                vk_msg_text = strings.new_chat_name.format(new_chat_name=msg_obj['action']['text'])
            elif action_type == "chat_photo_update":
                vk_msg_text = strings.new_chat_avatar
            else: vk_msg_text += f'\naction: {action_type}'
        # --- reply parse --- 
        if msg_obj.get('reply_message', False):
            reply_to_msg_text = msg_obj['reply_message'].get('text')
            if not reply_to_msg_text and msg_obj['reply_message'].get('attachments', False): 
                for reply_attachment in msg_obj['reply_message']['attachments']:
                    if reply_attachment['type'] in strings.attachments_emoji: 
                        reply_to_msg_text = f"{strings.attachments_emoji[reply_attachment['type']]} {reply_attachment['title'] or reply_attachment['type']}"
                    else: reply_to_msg_text = f"{strings.attachments_emoji['unknown']} {reply_attachment['title'] or reply_attachment['type']}"
        else: reply_to_msg_text = None
        # --- forward parse --- 
        for fwd_msg in msg_obj.get('fwd_messages', []):
            fwd_name, fwd_msg, fwd_attachments = await vk_parse_message(fwd_msg, fwd_msg_parsing=True)
            for attachment in fwd_attachments:
                if attachment[0] in strings.attachments_emoji: fwd_msg+=f"\n{strings.attachments_emoji[attachment[0]]} {attachment[1] or attachment['type']}"
                else: fwd_msg+=f"\n{strings.attachments_emoji['unknown']} {attachment[0]}"
            vk_msg_text += f"\n{strings.msg_forward.format(forward_from=fwd_name)}{fwd_msg}"
        # --- attachment parse --- [attachment_type, file_name, file_size, bytes]
        if msg_obj.get('attachments'): attachment_list = await vk_parse_attachments(msg_obj['attachments'], f'{vk_chat_id}_{vk_user_id}')
        if msg_obj.get('geo'): attachment_list.append(['location', 'location', 0, [msg_obj.get('geo')['coordinates']['latitude'],msg_obj.get('geo')['coordinates']['longitude']]])
        # --- return --- 
        if fwd_msg_parsing: 
            logger.debug(f'forward message from vk {vk_chat_id} ({vk_user_nick}) parsed: {vk_msg_text} {str(attachment_list) if attachment_list else ""}')
            return vk_user_nick, ('\n'+vk_msg_text if vk_msg_text else ''), attachment_list
        return str(vk_chat_id), vk_user_id, vk_user_nick, vk_msg_text, reply_to_msg_text, attachment_list, vk_chat_is_private, is_invite
    except Exception as e: logger.error(e,exc_info=True)

async def vk_parse_attachments(attachment_list, group_id_name=None):
    try:
        group_id = False
        attachment_list_parsed = []
        for attachment in attachment_list: 
            if attachment['type']=='photo':
                file_url = attachment["photo"]["orig_photo"]["url"]
                file_name = f'photo{attachment["photo"]["id"]}.{file_url.split("?")[0].split(".")[-1]}'
                file_size = requests.get(file_url, stream=True).headers.get('Content-Length')
                if len(attachment)>1: group_id = group_id_name
            elif attachment['type']=='video':
                video_info = vk_user_api.video.get(videos=f"{attachment['video']['owner_id']}_{attachment['video']['id']}_{attachment['video']['access_key']}")
                logger.debug(video_info)
                if 'direct_url' in video_info['items'][0]: 
                    file_url = video_info['items'][0]['direct_url']
                    file_name =  video_info['items'][0]['title']
                    file_size = video_info['items'][0]['duration']*1024*1024/5 # примерная оценка размера видео по его длительности (1c= 200кб)
                elif attachment['video']['type'] == 'video_message':
                    file_url = None
                    file_name = f'video_message{attachment["video"]["id"]}'
                    file_size = None
                    attachment['type']=='video_message'
                else:
                    file_url = None
                    file_name = attachment["video"]["title"] or f'video{attachment["video"]["id"]}'
                    file_size = None
            elif attachment['type']=='audio':
                file_url = attachment["audio"]["url"] if attachment["audio"]["url"] != '' else None
                file_name = f'{attachment["audio"]["artist"]} - {attachment["audio"]["title"]}' # .m3u8
                if file_url is not None: file_size = requests.get(file_url, stream=True).headers.get('Content-Length')
                else: file_size = None
            elif attachment['type']=='audio_message':
                file_url = attachment["audio_message"]["link_ogg"]
                file_name = f'audio_message{attachment["audio_message"]["id"]}.ogg'
                file_size = requests.get(file_url, stream=True).headers.get('Content-Length')
            elif attachment['type']=='doc':
                file_url = attachment["doc"]["url"]
                file_name = attachment["doc"]["title"]
                file_size = attachment["doc"]["size"]
                if len(attachment)>1: group_id = group_id_name
            elif attachment['type']=='sticker':
                file_url = attachment["sticker"]["images_with_background"][-1]["url"]
                file_name = f'sticker{attachment["sticker"]["sticker_id"]}.png'
                file_size = requests.get(file_url, stream=True).headers.get('Content-Length')
            elif attachment['type']=='graffiti':
                file_url = attachment["graffiti"]["url"]
                file_name = f'graffiti{attachment["graffiti"]["id"]}.png'
                file_size = requests.get(file_url, stream=True).headers.get('Content-Length')
            elif attachment['type']=='wall':
                if attachment["wall"]["from"].get('name'): file_name = strings.attachment_wall.format(wall_from=attachment["wall"]["from"]["name"], wall_text=attachment["wall"]["text"])
                elif attachment["wall"]["from"].get('first_name'): file_name = strings.attachment_wall.format(wall_from=f'{attachment["wall"]["from"]["first_name"]} {attachment["wall"]["from"]["last_name"]}', wall_text=attachment["wall"]["text"])
                else: file_name = strings.attachment_wall.format(wall_from='', wall_text=attachment["wall"]["text"])
                if attachment["wall"].get('attachments'):
                    for wall_attachment in await vk_parse_attachments(attachment["wall"]['attachments'], f'{attachment["wall"]["id"]}'): 
                        attachment_list_parsed.append(wall_attachment)
                file_size = None
            elif attachment['type']=='story':
                file_name = strings.attachment_story.format(first_name=attachment["story"]["owner_id"], last_name='')
                file_size = None
            elif attachment['type']=='link':
                file_name = attachment["link"]["url"]
                file_size = None
            elif attachment['type']=='poll':
                options=[]
                for option in attachment["poll"]["answers"]: options.append(option["text"])
                file_name = attachment["poll"]["question"]
                file_size = None
                file = options
            else:
                file_name = attachment["type"]
                file_size = None
            if config.attachments_forward and file_size is not None:
                file_size = int(file_size)
                #logger.info(f'file_size = {file_size} \nfile_url = {file_url}')
                if file_size/1024/1024 < config.attachments_max_size_mb and file_size>0 and file_url is not None:
                    try: 
                        if attachment['type']=='audio':
                            process = subprocess.Popen(["ffmpeg","-i", file_url, "-f", "mp3", "-acodec", "libmp3lame", "-vn", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                            file = BufferedInputFile(process.stdout.read(),filename=file_name)
                        elif attachment['type']=='video':
                            with yt_dlp.YoutubeDL({'outtmpl': 'video.mp4'}) as ydl:
                                ydl.download([file_url])
                                with open("video.mp4", "rb") as f:
                                    video_bytes = f.read()
                                    file = BufferedInputFile(video_bytes, filename=f"{file_name}.mp4")
                                    file_size = len(video_bytes)
                                if os.path.exists("video.mp4"): os.remove("video.mp4")
                        else:
                            file = BufferedInputFile(requests.get(file_url).content,filename=file_name)
                    except Exception as e:
                        logger.warning(e, exc_info=True)
                        file = None
                else: file = None
            elif not attachment['type']=='poll': file = None
            if group_id: attachment_list_parsed.append([attachment['type'], file_name, file_size, file, group_id])
            else: attachment_list_parsed.append([attachment['type'], file_name, file_size, file])
        return attachment_list_parsed
    except Exception as e: logger.error(e,exc_info=True)
    
# === TG catcher ===
tg_bot = Bot(token=config.tg_token)
dp = Dispatcher(storage=MemoryStorage())
@dp.message()
async def handle_telegram_message(message: Message):
    try: await message_navigator(service0='tg',msg_obj=message)
    except Exception as e: logger.critical(e, exc_info=True)
# === VK catcher ===
vk_group_session = vk_api.VkApi(token=config.vk_group_token)
vk_group_api = vk_group_session.get_api() # group session api
vk_upload = vk_api.upload.VkUpload(vk_group_session)
vk_user_api = vk_api.VkApi(token=config.vk_group_admin_user_token).get_api() # group admin (user) session api
def run_vk_bot_polling(loop):
    try:
        for event in VkBotLongPoll(vk_group_session, config.vk_group_id).listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                if event.object.message['from_id'] == -config.vk_group_id: continue  # пропускаем сообщения от самого бота
                asyncio.run_coroutine_threadsafe(message_navigator(service0='vk', msg_obj=event.object.message), loop)
    except requests.exceptions.ReadTimeout as e:
        logger.warning(e)
        run_vk_bot_polling(loop)  # перезапуск при ошибке
    except Exception as e:
        logger.critical(e, exc_info=True)
        run_vk_bot_polling(loop)  # перезапуск при ошибке
# === MAIN ===
async def main():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_vk_bot_polling, args=(loop,), daemon=True).start() 
    asyncio.create_task(message_sender())
    asyncio.create_task(message_buffer_worker())
    await db.initialization()
    if config.message_max_len + config.message_reply_max_len > 4000: logger.warning("message len limit in telegram is 4096 symbols. check limits in config file")
    if config.attachments_max_size_mb > 20: logger.warning('telegram file size limit is 20 MB. check limits in config file')
    logger.info("bot started")
    await dp.start_polling(tg_bot)
    logger.warning("bot stopped")
if __name__ == "__main__":
    asyncio.run(main())
