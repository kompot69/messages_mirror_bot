bot_version=[3,1]
import asyncio, threading, vk_api, requests, tempfile, json, discord, psutil, os
from datetime import datetime
from io import BytesIO
from collections import defaultdict
from discord.ext import commands
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.media_group import MediaGroupBuilder
#from aiogram.utils.text_decorations import markdown_decoration
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import config, db, strings, convert
from config import logger

buttons_main=[
    ['link', 'FAQ', 'https://'],
    ['payload', 'disconnect'],
    ['payload', 'connect_to', 'id'],
    ['payload', 'stats'],
    ['payload', 'update']
    ]

chat_last_send = {} # [nick,time]

# = = = COMMANDS = = =
async def get_chat_name(service, id):
    if service == 'vk': return await vk_get_name(id)
    if service == 'tg': return await tg_get_name(id)
    if service == 'dc': return await dc_get_name(id)
async def check_message_access(service, id):
    if service == 'vk': return await vk_check_message_access(id)
    if service == 'tg': return await tg_check_message_access(id)
    if service == 'dc': return True
    
async def if_command(service, chat, message): 
    if not 'text' in message: return False
    msg_text = message['text'].lower()
    if msg_text.endswith(f'@{config.services[service]["tag"]}'): msg_text = msg_text[:-(len(config.services[service]["tag"])+1)]
    args = msg_text.split(" ")
    if  msg_text.startswith(('/start', '/mirror')) or (chat['is_private'] and msg_text in ['/help', 'начать', 'помощь']): 
        return await mirror_cmd(service, chat, message, args)
    if  msg_text.startswith('/getlogs'): 
        return await getlogs_cmd(service, chat, message)
    else: return False

async def getlogs_cmd(service, chat, message):
    logger.debug(f'command from {chat}')
    if message['sender']['id'] not in config.services[service]['admin_ids']: return False
    logger.info(f'getlogs command from {service} admin {message['sender']['id']}')
    return 'logs will be here'

async def mirror_cmd(service, chat, message, args):
    logger.debug(f'command from {chat}')
    message_access = await check_message_access(service, chat['id'])
    # admin 
    if message['sender']['id'] in config.services[service]['admin_ids']: 
        bot_ver = ".".join(str(x) for x in bot_version if isinstance(x, int))+" "+" ".join(str(x) for x in bot_version if isinstance(x, str))
        mem_usage_current_process = psutil.Process(os.getpid()).memory_info().rss/1024/1024
        admin_text = f"🔢 Версия: {bot_ver}\n💾Использовано ОП: {mem_usage_current_process:.0f} MB"
        #admin_text = strings.admin_text.format(bot_version=bot_ver.strip(), message_max_len=config.message_max_len, ram_usage=mem_usage_current_process)
    else: admin_text = False 
    if 'name' in chat: service_chat_name = chat['name']
    else: service_chat_name = await get_chat_name(service, chat['id'])
    chat_settings, connected_chats = await db.get_chat(service, chat['id_db'])
    # без аргументов - просмотр статуса
    if len(args) == 1 : 
        other_services = []
        for connected_service, connected_id in connected_chats.items():
            if connected_id is not None: connected_service_chat_name = await get_chat_name(connected_service, connected_id)
            else: connected_service_chat_name = None
            connected_chast_settings, connected_chat_connected_chasts = await db.get_chat(connected_service, connected_id)
            if connected_chat_connected_chasts is None: connected_mutually = False
            elif connected_chat_connected_chasts[service] == chat['id_db']: connected_mutually = True
            else: connected_mutually = False
            other_services.append([connected_service, connected_id, connected_service_chat_name, connected_mutually])
        return strings.cmd_mirror_status(service, chat['id_db'], other_services, message_access, admin_text)
    # больше 1 аргумента
    if len(args) != 2 : return strings.cmd_mirror_connecting(service, chat['id_db'], 'wrong_id')
    # отвязка
    if args[1]=='off' or args[1]=='disconnect':
        for connected_service, connected_id in connected_chats.items(): 
            connected_chast_settings, connected_chat_connected_chasts = await db.get_chat(connected_service, connected_id)
            if connected_chat_connected_chasts is not None and connected_chat_connected_chasts[service] == chat['id_db']: 
                await message_send_queue.put(([connected_service,connected_id], None, strings.chat_disconnected_from.format(service_name=config.services[service]['name'],service_chat_id=chat['id_db'],service_chat_name=service_chat_name)))
        await db.disconnect_chat(service,chat['id_db'])
        return strings.cmd_mirror_connecting(service, chat['id_db'], 'disconnect')
    # с аргументами - настройка привязки
    service1 = args[1][:2]
    service1_chat_id = args[1][2:]
    if 'tread' in service1_chat_id: service1_chat_id, tread_id = service1_chat_id.split('tread')
    else: tread_id = None
    # проверка валидности
    if service1_chat_id.startswith('-'): #обход для бесед вк
        if not service1_chat_id[1:].isdigit(): return strings.cmd_mirror_connecting(service, chat['id_db'], 'wrong_id')
    elif not service1_chat_id.isdigit(): return strings.cmd_mirror_connecting(service, chat['id_db'], 'wrong_id')
    if config.id_len[0] > len(service1_chat_id) or len(service1_chat_id) > config.id_len[1]: return strings.cmd_mirror_connecting(service, chat['id_db'], 'wrong_id')
    service1_chat_name = await get_chat_name(service1, service1_chat_id)
    connected_mutually = await db.connect_chats(service, chat['id_db'], service1, (service1_chat_id+'tread'+tread_id if tread_id else service1_chat_id)) # привязка 
    if connected_mutually is None: return strings.cmd_mirror_connecting(service, chat['id_db'], 'wrong_id')
    if connected_mutually == True: 
        await message_send_queue.put(([service1, service1_chat_id], None, strings.chat_connected_to.format(service_name=config.services[service]['name'],service_chat_id=chat['id_db'],service_chat_name=service_chat_name)))
    if connected_mutually == False: 
        await message_send_queue.put(([service1, service1_chat_id], None, strings.chat_connect_to_request.format(service_name=config.services[service]['name'],service_chat_id=chat['id_db'],service_chat_name=service_chat_name)))
    return strings.cmd_mirror_connecting(service, chat['id_db'], [service1, (service1_chat_id+'tread'+tread_id if tread_id else service1_chat_id), service1_chat_name], message_access, connected_mutually) 

# = = = MESSAGES BUFFER, SENDER, NAVIGATOR, CONSTRUCTOR = = =

message_buffer = defaultdict(list)
message_buffer_timers = {} 
message_buffer_queue = asyncio.Queue()
async def message_buffer_worker():
    while True:
        service_to, service_from, message = await message_buffer_queue.get()
        if isinstance(message, str) or 'attachments' not in message or all('group_id' not in a for a in message['attachments']): # просто текст / без вложений / вложения не групповые
            await message_send_queue.put((service_to, service_from, message))
            continue
        group_id = f'{message['attachments'][0]['group_id']}_to_{service_to[0]}'
        logger.debug(f'new attachments with group_id {group_id}: {message['attachments']}')
        if group_id in message_buffer: # добавляем вложения (другое - если есть - перезаписываем) к старому объекту
            existing_message_obj = message_buffer[group_id][2]
            existing_message_obj['attachments'].extend(message['attachments'])
            if 'text' in message and message['text'] is not None: existing_message_obj['text'] = message['text']
            if 'text_format' in message: existing_message_obj['text_format'] = message['text_format']
            if 'forward_from' in message: existing_message_obj['forward_from'] = message['forward_from']
            if 'reply_to_message' in message: existing_message_obj['reply_to_message'] = message['reply_to_message']
            message_buffer[group_id] = [service_to, service_from, existing_message_obj]
        else:
            message_buffer[group_id] = [service_to, service_from, message]
        if group_id in message_buffer_timers: message_buffer_timers[group_id].cancel() # cancel old timer
        message_buffer_timers[group_id] = asyncio.create_task(message_buffer_timer(group_id)) # start new timer

async def message_buffer_timer(group_id: str):
    try:
        await asyncio.sleep(1) # attachments_buffer_timeout
        logger.debug(f'its time to send attachments group: {group_id}')
        if group_id in message_buffer:
            service_to, service_from, message = message_buffer[group_id]
            await message_send_queue.put((service_to, service_from, message))
            del message_buffer[group_id]
            del message_buffer_timers[group_id]
    except asyncio.CancelledError: pass
    except Exception as e: 
        logger.error(f'timer error for group {group_id}: {e}', exc_info=True)
        del message_buffer[group_id]

async def message_notifiacte(service_to, text, tread=None):
    logger.debug(f'notificate {service_to}')
    if 'tread' in service_to[1]: service_to[1], tread = service_to[1].split('tread')
    if service_to[0] == 'vk': message = vk_group_api.messages.send(peer_id=service_to[1], message=text, random_id=0)
    elif service_to[0] == 'tg': message = await tg_bot.send_message(service_to[1], text, message_thread_id=tread) 
    elif service_to[0] == 'dc': message = await (dc_bot.get_channel(tread or service_to[1]) or await dc_bot.fetch_channel(tread or service_to[1])).send(text)         
    await asyncio.sleep(config.error_notificate_sec)
    if service_to[0] == 'vk': vk_group_api.messages.delete(message_ids=message, delete_for_all=1)
    elif service_to[0] == 'tg': await tg_bot.delete_message(chat_id=service_to[1],message_id=message.message_id) 
    elif service_to[0] == 'dc': await message.delete()

message_send_queue = asyncio.Queue()
async def message_sender(): 
    while True:
        service_to, service_from, message = await message_send_queue.get()

        if 'tread' in str(service_to[1]): service_to[1], tread = service_to[1].split('tread')
        else: tread = None

        message_text, message_attachments, attachments_with_errors = await message_constructor(service_to, service_from, message)
        logger.info(f'sending message to {service_to}: {message_text.replace(chr(10), '  ') if message_text else ""} {message_attachments if message_attachments else ""}')
        
        try:
            if service_to[0] == 'dc': 
                if tread: dc_channel = dc_bot.get_channel(service_to[1]) or await dc_bot.fetch_channel(service_to[1])
                else: dc_channel = dc_bot.get_channel(service_to[1]) or await dc_bot.fetch_channel(service_to[1])
            if isinstance(message, str): 
                if service_to[0] == 'tg': await tg_bot.send_message(service_to[1], message_text, message_thread_id=tread) 
                if service_to[0] == 'vk': vk_group_api.messages.send(peer_id=service_to[1], message=message_text, random_id=0)
                if service_to[0] == 'dc': await dc_channel.send(message_text)
            elif message_text and not message_attachments: 
                if service_to[0] == 'tg': await tg_bot.send_message(service_to[1], message_text, message_thread_id=tread) 
                if service_to[0] == 'vk': vk_group_api.messages.send(peer_id=service_to[1], message=message_text, random_id=0)
                if service_to[0] == 'dc': await dc_channel.send(message_text)
            else:
                group_id = False
                if 'group_id' in message_attachments[0] and len(message_attachments)>1: 
                    group_id = message_attachments[0]['group_id']

                if service_to[0] == 'tg':
                    if group_id: uploaded_attachments = MediaGroupBuilder(caption=message_text)
                    for attachment in message_attachments:
                        try:
                            if 'bytes' in attachment and attachment['bytes']: 
                                attachment['bytes'].seek(0)
                                attachment_bytes = BufferedInputFile(attachment['bytes'].getvalue(), attachment['file_name'])
                            if attachment['type'] == 'photo': 
                                if group_id: uploaded_attachments.add_photo(media=attachment_bytes)
                                else: await tg_bot.send_photo(service_to[1], attachment_bytes, caption=message_text, message_thread_id=tread)
                            elif attachment['type'] in ['video','sticker_video']: 
                                if group_id: uploaded_attachments.add_video(media=attachment_bytes)
                                else: await tg_bot.send_video(service_to[1], attachment_bytes, caption=message_text, message_thread_id=tread)
                            elif attachment['type'] == 'audio': 
                                await tg_bot.send_audio(service_to[1], attachment_bytes, caption=message_text, message_thread_id=tread)
                            elif attachment['type'] in ['doc','gif','sticker_animated']: 
                                if group_id: uploaded_attachments.add_document(media=attachment_bytes)
                                else: await tg_bot.send_document(service_to[1], attachment_bytes, caption=message_text, message_thread_id=tread)
                            elif attachment['type'] in ['graffiti','sticker']: 
                                await tg_bot.send_sticker(service_to[1], attachment_bytes, message_thread_id=tread)
                            elif attachment['type'] == 'audio_message': 
                                await tg_bot.send_voice(service_to[1], attachment_bytes, caption=message_text, message_thread_id=tread)
                            elif attachment['type'] == 'video_message': 
                                await tg_bot.send_video_note(service_to[1], attachment_bytes, message_thread_id=tread)
                            elif attachment['type'] == 'location': 
                                if message_text: await tg_bot.send_message(service_to[1], message_text, message_thread_id=tread) 
                                await tg_bot.send_location(service_to[1], latitude=attachment['file_name'][0], longitude=attachment['file_name'][1], message_thread_id=tread)
                            else: 
                                await tg_bot.send_message(service_to[1], f'{message_text+"\n" if message_text else ""}{strings.attachments_emoji["unknown"]} {attachment['file_name']}', message_thread_id=tread)
                        except Exception as e: 
                            logger.error(e, exc_info=True)
                            attachments_with_errors.append(attachment)
                    if group_id: await tg_bot.send_media_group(service_to[1], media=uploaded_attachments.build()) 
                        
                elif service_to[0] == 'vk':
                    uploaded_attachments = []
                    for attachment in message_attachments:
                        if 'bytes' in attachment and attachment['bytes']: attachment['bytes'].seek(0)
                        try:
                            vk_attachment = None
                            if attachment['type'] == 'location': 
                                vk_group_api.messages.send(peer_id=service_to[1], lat=attachment['file_name'][0], long=attachment['file_name'][1], random_id=0)
                            elif attachment['type'] in ['photo','sticker']: 
                                vk_attachment = await vk_attachment_upload(file_photo=attachment['bytes'])
                            elif attachment['type'] in ['video','video_message','sticker_video']: 
                                vk_attachment = await vk_attachment_upload(file_video=attachment['bytes'], to_id=service_to[1], name=attachment['file_name'], video_description=strings.attachment_video_description.format(sender_name=message['sender']['name']))
                            elif attachment['type'] in ['doc','sticker_animated']: 
                                vk_attachment = await vk_attachment_upload(file_doc=attachment['bytes'], to_id=service_to[1], name=attachment['file_name'])
                            elif attachment['type'] == 'gif': 
                                vk_attachment = await vk_attachment_upload(file_gif=attachment['bytes'], to_id=service_to[1], name=attachment['file_name'])
                            elif attachment['type'] == 'audio': 
                                vk_attachment = await vk_attachment_upload(file_audio=attachment['bytes'], to_id=service_to[1], name=attachment['file_name'])
                            elif attachment['type'] == 'audio_message': 
                                vk_attachment = await vk_attachment_upload(file_audio_message=attachment['bytes'], to_id=service_to[1], name=attachment['file_name'])
                            if not vk_attachment: raise Exception('attachment was empty')
                            if group_id: uploaded_attachments.append(vk_attachment)
                            elif message_text: vk_group_api.messages.send(peer_id=service_to[1], message=message_text, random_id=0, attachment=vk_attachment)
                            else: vk_group_api.messages.send(peer_id=service_to[1], random_id=0, attachment=vk_attachment)
                        except Exception as e:
                            logger.error(e, exc_info=True)
                            attachments_with_errors.append(attachment)
                            vk_group_api.messages.send(peer_id=service_to[1], message=message_text, random_id=0)
                    if group_id:
                        if message_text: vk_group_api.messages.send(peer_id=service_to[1], message=message_text, random_id=0, attachment=uploaded_attachments)
                        else: vk_group_api.messages.send(peer_id=service_to[1], random_id=0, attachment=uploaded_attachments)

                elif service_to[0] == 'dc':
                    uploaded_attachments = []
                    try:
                        for attachment in message_attachments:
                            if 'bytes' in attachment and attachment['bytes']: 
                                attachment['bytes'].seek(0)
                                uploaded_attachments.append(discord.File(attachment["bytes"], filename=attachment["file_name"]))
                            else: attachments_with_errors.append(attachment)
                        if message_text: await dc_channel.send(content=message_text, files=uploaded_attachments)
                        else: await dc_channel.send(files=uploaded_attachments)
                    except Exception as e:
                        if '413 Payload Too Large (error code: 40005): Request entity too large' in str(e): logger.warning(f'cannot send file to dc: {e}')
                        else: logger.error(e, exc_info=True)
                        attachments_with_errors.extend(message_attachments)

                if 'uploaded_attachments' in locals(): del uploaded_attachments
                if attachments_with_errors:
                    logger.debug(f'attachments with errors: {attachments_with_errors}')
                    notifiacte = strings.notificate_attachments_error.format(service_to=config.services[service_to[0]]['name'])
                    message_text = message_text if message_text else ''
                    for attachment in attachments_with_errors: 
                        if attachment['type'] in strings.attachments_emoji: 
                            message_text += f"\n{strings.attachments_emoji[attachment['type']]} {attachment['file_name']}"
                            notifiacte += f"\n{strings.attachments_emoji[attachment['type']]} {attachment['file_name']}"
                        else: 
                            message_text = f"\n{strings.attachments_emoji['unknown']} {attachment['file_name']}"
                            notifiacte = f"\n{strings.attachments_emoji['unknown']} {attachment['file_name']}"
                        if attachment['size'] is not None and isinstance(attachment['size'], (int, float)): 
                            message_text += f" ({round(attachment['size']/1024/1024,2)}МБ)"
                            notifiacte += f" ({round(attachment['size']/1024/1024,2)}МБ)"
                    if service_from is not None: await message_notifiacte(service_from, notifiacte, tread=tread)
                    await message_send_queue.put((service_to, service_from, message_text))

        except Exception as e: logger.error(f'error send to {service_to[0]} {service_to[1]}: {e}', exc_info=True)
        
async def message_constructor(service_to, service_from, message):
    try:
        if isinstance(message, str): return message, None, [] # simple text
        if 'text' in message and message['text'] is not None: constructor_text = message['text']
        else: constructor_text = ''

        constructor_reply = ''
        if 'reply_to_message' in message:
            if 'text' in message['reply_to_message'] and message['reply_to_message']['text'] is not None and len(message['reply_to_message']['text'])>0:
                constructor_reply = message['reply_to_message']['text']
                if constructor_reply.startswith(strings.msg_reply_prefix): constructor_reply = constructor_reply[constructor_reply.find('\n')+1:] # обрезка реплаев в реплаях
                if constructor_reply.startswith(strings.msg_nick_prefix): constructor_reply = constructor_reply[constructor_reply.find('\n')+1:] # обрезка ников в реплаях
                if len(constructor_reply)>config.message_reply_max_len: constructor_reply = constructor_reply[:config.message_reply_max_len-3].strip()+'...' # обрезка длины
                constructor_reply = f'{strings.msg_reply_prefix} {constructor_reply.replace("\n", " ")}'
            elif 'attachments' in message['reply_to_message']:
                constructor_reply = f'{strings.msg_reply_prefix} {strings.attachments_emoji[message['reply_to_message']['attachments'][0]['type']]} {message['reply_to_message']['attachments'][0]['type']}'

        constructor_sender = ''
        last_send = chat_last_send.get(f'{service_to[0]}{service_to[1]}') # sender_name, last_send_time
        if last_send: 
            if not (message['sender']['name'] == last_send[0] and (datetime.now()-last_send[1]).total_seconds()/60 <= config.nick_repeat_after_min):
                constructor_sender = strings.msg_nick_prefix + message['sender']['name']
        else: constructor_sender = strings.msg_nick_prefix + message['sender']['name']
        chat_last_send[f'{service_to[0]}{service_to[1]}'] = [message['sender']['name'],datetime.now()]

        constructor_forward = ''
        if 'forward_from' in message: 
            if 'name' in message['forward_from']: constructor_forward = strings.msg_forward.format(forward_from=message['forward_from']['name'])
            elif service_from is not None: 
                name = await get_chat_name(service_from[0], message['forward_from']['id'])
                if name: constructor_forward = strings.msg_forward.format(forward_from=(name))
                else: constructor_forward = strings.msg_forward.format(forward_from=message['forward_from']['id'])

        constructor_attachments = ''
        message_attachments = []
        attachments_with_errors = []
        if 'attachments' in message:
            for attachment in message['attachments']:
                if attachment['type'] == 'contact': 
                    constructor_attachments += f'\n{strings.attachments_emoji["contact"]} {attachment['file_name'][0]}\n{attachment['file_name'][1]}'
                elif attachment['type'] == 'link': 
                    constructor_attachments += f'\n{strings.attachments_emoji["link"]} {attachment['file_name']}'
                elif attachment['type'] == 'wall': 
                    constructor_attachments += f'\n{strings.attachments_emoji["wall"]} {attachment['file_name']}'
                elif attachment['type'] == 'story': 
                    constructor_attachments += f'\n{strings.attachments_emoji["story"]} {attachment['file_name']}'
                elif attachment['type'] == 'poll': 
                    constructor_attachments += f'\n{strings.attachments_emoji["poll"]} {attachment['file_name'][0]}'
                    for option in attachment['file_name'][0]:
                        constructor_attachments += f'\n ● {option}'
                elif (not 'bytes' in attachment or attachment['bytes'] is None) and attachment['type'] not in ['location']:
                    if attachment['type'] in strings.attachments_emoji: 
                        constructor_attachments += f'\n{strings.attachments_emoji[attachment['type']]} {attachment['file_name']}'
                    else: 
                        constructor_attachments += f'\n{strings.attachments_emoji['unknown']} {attachment['file_name']}'
                    if attachment['size'] is not None and isinstance(attachment['size'], (int, float)): 
                        constructor_attachments += f'({round(attachment['size']/1024/1024,2)}МБ)' 
                    attachments_with_errors.append(attachment)
                else:
                    message_attachments.append(attachment)
        message_text = ''
        for e in [constructor_reply, constructor_sender, constructor_forward, constructor_text, constructor_attachments]:
            if e and len(e)>0: message_text += f'\n{e}'
        if len(message_text) > config.message_max_len: message_text = message_text[:config.message_max_len]+"\n [ ... ]"
        if message_text is None or len(message_text)==0: message_text=None
        return message_text, message_attachments, attachments_with_errors
    except Exception as e: logger.error(e, exc_info=True)

async def message_navigator(service_from, msg_obj):
    try:
        logger.debug(f"message from {service_from} catched: {'(wait to re-request vk message)' if service_from=='vk' else str(msg_obj) }")
        # parsing
        if service_from == 'tg': message, chat = await tg_parse_message(msg_obj)
        elif service_from == 'vk': 
            rr_msg_obj = vk_group_api.messages.getByConversationMessageId(peer_id=msg_obj['peer_id'], conversation_message_ids=[msg_obj['conversation_message_id']])['items'] # vk govno
            if isinstance(msg_obj, (list,dict)): msg_obj = rr_msg_obj[0]
            else: logger.warning(f'rr_msg_obj is not a list or dict, using original msg_obj...')
            logger.debug(f're-requested vk message: {rr_msg_obj}')
            message, chat = await vk_parse_message(msg_obj)
        elif service_from == 'dc': message, chat = await dc_parse_message(msg_obj)
        logger.info(f"new message from {service_from} {chat}: {message}")
        if not chat or not message: return logger.error('error while parsing detected')
        # command / invite answer 
        command_answer = await if_command(service_from, chat, message)
        if command_answer is not None and command_answer != False: 
            return await message_send_queue.put(([service_from, chat['id_db']], None, command_answer))
        elif 'if_invite' in chat and chat['if_invite']: 
            logger.info(f'bot was invited to {service_from} {chat['id']}  chat')
            return await message_send_queue.put(([service_from, chat['id_db']], None, strings.welcome_message))
        # connect check 
        chat_settings, connected_chats = await db.get_chat(service_from, chat['id_db'])
        chats_to_send = {}
        for connected_service, connected_id in connected_chats.items():
            if connected_id: # подключенный чат
                connected_chat_settings, connected_chat_connected_chats = await db.get_chat(connected_service, connected_id)
                if chat['id_db'] in connected_chat_connected_chats.values(): # подключенный чат подкючен к этому
                    chats_to_send[connected_service] = connected_id
                    logger.debug(f'чат {service_from} {chat['id_db']} подключен к чату {connected_service} c ID {connected_id}')
                else: logger.debug(f'чат {service_from} {chat['id_db']} невзаимно подключен к чату {connected_service} c ID {connected_id}')
            else: logger.debug(f'чат {service_from} {chat['id_db']} не подключен к чату {connected_service}')
        if not chats_to_send and chat['is_private']: 
            return await message_send_queue.put(([service_from, chat['id_db']], None, strings.chat_has_no_connected_chats))
        for service, to_id in chats_to_send.items():
            await message_buffer_queue.put(([service, to_id], [service_from, chat['id_db']], message)) 
    except Exception as e: logger.error(e, exc_info=True)

# = = = = = DC = = = = =

async def dc_get_name(id): 
    if 'tread' in id: id = id.split('tread')[0]
    channel = dc_bot.get_channel(id) or await dc_bot.fetch_channel(id)
    #logger.debug(channel)
    if isinstance(channel, discord.DMChannel): return channel.recipient.global_name
    if channel is None: return None
    return channel.name

async def dc_parse_message(msg_obj, reply_parse=False): 
    try:
        #if True:#getattr(msg_obj, 'reference', None):
        #    for attr in dir(msg_obj):
        #        if not attr.startswith("_"):
        #            try:
        #                value = getattr(msg_obj, attr)
        #                logger.debug(f'{attr} = {value}')
        #            except Exception: pass
        chat = {}
        chat['id'] = msg_obj.channel.id
        chat['id_db'] = str(msg_obj.channel.id)
        chat['is_private'] = True if isinstance(msg_obj.channel, discord.DMChannel) else False
        if chat['is_private']: chat['name'] = msg_obj.author.global_name
        else: chat['name'] = msg_obj.channel.guild.name
        if getattr(msg_obj.channel, 'category_id', None): # msg_obj.tread # msg_obj.category_id
            chat['id_db'] = f'{msg_obj.channel.id}tread{msg_obj.channel.category_id}'
            chat['tread'] = {'id':msg_obj.channel.category_id, 'name':msg_obj.channel.name}#.name
        message = {}
        message['id'] = msg_obj.id
        message['sender'] = {'id':msg_obj.author.id}
        if getattr(msg_obj.author, 'nick', None): message['sender']['name'] = msg_obj.author.nick
        elif getattr(msg_obj.author, 'global_name', None): message['sender']['name'] = msg_obj.author.global_name
        elif getattr(msg_obj.author, 'display_name', None): message['sender']['name'] = msg_obj.author.display_name
        else: message['sender']['name'] = None
        if getattr(msg_obj, 'clean_content', None): message['text'] = msg_obj.clean_content #content
        if getattr(msg_obj, 'type', None):
            if msg_obj.type == discord.MessageType.reply: 
                message['reply_to_message'], reply_to_message_chat = await dc_parse_message(msg_obj.reference.resolved, reply_parse=True)
            elif msg_obj.type == discord.MessageType.default and getattr(msg_obj, 'reference', None) and msg_obj.reference.type == discord.MessageReferenceType.forward:
                try: 
                    fwd_msg = await msg_obj.channel.fetch_message(msg_obj.reference.message_id)
                    fwd_msg, fwd_chat = await dc_parse_message(fwd_msg)
                    logger.debug(f'forward message = {fwd_msg}')
                    message['forward_from'] = {'id': fwd_msg['sender']['id'], 'name': fwd_msg['sender']['name']}
                    if 'text' in fwd_msg: message['text'] = fwd_msg['text']
                except discord.errors.NotFound:
                    #fwd_channel = await dc_bot.fetch_channel(msg_obj.reference.channel_id)
                    #fwd_msg = await fwd_channel.fetch_message(msg_obj.reference.message_id)
                    logger.debug('forward message not found')
                    message['forward_from'] = {'id': None, 'name': None}
                    message['text'] = '[message not found]'
            if msg_obj.type == discord.MessageType.recipient_add: message['if_invite']=True
            if msg_obj.type == discord.MessageType.new_member: message['text'] = strings.action_join_in_chat
            if msg_obj.type == discord.MessageType.channel_name_change: message['text'] = strings.action_chat_title_update
            if msg_obj.type == discord.MessageType.channel_icon_change: message['text'] = strings.action_chat_photo_update
        #if msg_obj.poll
        if msg_obj.stickers: logger.debug(f'msg_obj.stickers = {msg_obj.stickers}')
        if getattr(msg_obj, 'attachments', None): 
            message["attachments"] = []
            if len(msg_obj.attachments)>1: group_id = f'{chat['id']}_{message['id']}'
            else: group_id = None
            for attachment in msg_obj.attachments:
                logger.debug(f'attachment.content_type={attachment.content_type}')
                att = {}
                match attachment.content_type:
                    case 'image/webp': att['type'] = 'photo'
                    case 'video/quicktime': att['type'] = 'video'
                    case 'audio/ogg': att['type'] = 'audio_message'
                    case _: att['type'] = 'doc'
                att['file_name'] = attachment.filename
                att['size'] = attachment.size
                if config.attachments_forward and att['size']/1024/1024 < config.attachments_max_size_mb and not reply_parse:
                    att['bytes'] = BytesIO(await attachment.read())
                    att['bytes'].seek(0)
                if group_id: att['group_id'] = group_id
                message["attachments"].append(att)
        return message, chat
    except Exception as e:
        logger.error(e, exc_info=True)
        return None, None

# = = = = = TG = = = = =

async def tg_check_message_access(chat_id):
    try:
        member = await tg_bot.get_chat_member(chat_id, config.services['tg']['token'].split(':')[0])
        if member.status in ["left", "kicked"]: return False
        if member.status == "restricted" and member.can_send_messages == False: return False
        if member.status in ["administrator", "creator"]: return True
        return True
    except Exception as e: return False

async def tg_get_name(id):
    try:
        chat = await tg_bot.get_chat(id)
        return chat.title or chat.full_name
    except Exception as e:
        logger.warning(f'error while getting name for id {id}: {e}')
        return '[неизвестно]'

async def tg_download_attachment(attachment, reply_parse=False, type=None): 
    # for photo, video, video_note, animation, audio, voice, document, sticker
    logger.debug(f'attachment = {attachment}')
    file = None
    file_size = getattr(attachment, 'file_size', None)
    need_extension = False
    if getattr(attachment, 'file_name', False): file_name = attachment.file_name
    elif type in ['photo','sticker']: file_name = f"{type}_{attachment.file_unique_id}.png"
    elif type in ['sticker_video']: file_name = f"sticker_video_{attachment.file_unique_id}.webm"
    elif type in ['sticker_animated']: file_name = f"sticker_{attachment.file_unique_id}.tgs"
    elif type in ['video','video_message']: file_name = f"{type}_{attachment.file_unique_id}.mp4"
    else: 
        file_name = f'attachment_{attachment.file_unique_id}'
        if getattr(attachment, 'mime_type', False): file_name += f"_{attachment.mime_type.split('/')[1]}"
        else: need_extension = True
    try: 
        if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb and not reply_parse:
            file = BytesIO()
            file_obj = await tg_bot.get_file(attachment.file_id) 
            if need_extension: file_name += f"_{attachment.file_path.split('.')[1]}"
            await tg_bot.download_file(file_obj.file_path, destination=file)
            file.seek(0)
    except TelegramBadRequest as e: 
        logger.warning(e)
        file = None
    except Exception as e: 
        logger.error(e, exc_info=True)
        file = None
    return file_name, file_size, file

async def tg_parse_message(msg_obj, reply_parse=False):
    try:
        message={'sender':{}}
        chat={}
        attachment={}
        chat['id'] = int(msg_obj.chat.id)
        chat['id_db'] = str(msg_obj.chat.id)
        chat['name'] = msg_obj.chat.title or f'{msg_obj.chat.first_name} {msg_obj.chat.last_name if msg_obj.chat.last_name else ''}'
        chat['is_private'] = True if msg_obj.chat.type=='private' else False
        if msg_obj.chat.is_forum and msg_obj.message_thread_id: 
            chat['id_db'] = f"{chat['id']}tread{msg_obj.message_thread_id}"
            chat['tread']={}
            chat['tread']['id'] = int(msg_obj.message_thread_id)
            if msg_obj.reply_to_message and msg_obj.reply_to_message.forum_topic_created: chat['tread']['name'] = msg_obj.reply_to_message.forum_topic_created.name
        message['id'] = int(msg_obj.message_id)
        message['sender']['id'] = int(msg_obj.from_user.id)
        message['sender']['name'] = f"{msg_obj.from_user.first_name} {msg_obj.from_user.last_name}" if msg_obj.from_user.last_name else msg_obj.from_user.first_name
        message['text'] = getattr(msg_obj, 'text', False) or getattr(msg_obj, 'caption', False) or '' # msg_obj . text html_text md_text
        # --- action parse --- 
        if msg_obj.new_chat_members: # invite check
            for user in msg_obj.new_chat_members:
                if int(config.services['tg']['token'].split(':')[0]) == user.id: chat['if_invite'] = True
                else: message['text'] = strings.action_join_in_chat
        if getattr(msg_obj, 'left_chat_participant', False): 
            if msg_obj.left_chat_participant['id'] == message['sender']['id']: message['text'] = strings.action_left_from_chat
            else: message['text'] = strings.action_chat_kick_user.format(kicked_user=msg_obj.left_chat_participant['first_name'])
        if getattr(msg_obj, 'chat_owner_left', False): message['text'] = strings.action_chat_without_owner_admin
        if getattr(msg_obj, 'new_chat_title', False): message['text'] = strings.action_chat_title_update.format(new_chat_name=msg_obj.new_chat_title)
        if getattr(msg_obj, 'new_chat_photo', False): 
            message['text'] = strings.action_chat_photo_update
            attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.new_chat_photo[-1], reply_parse)
            attachment['type'] = 'photo'
        # reply / forward parse 
        if msg_obj.reply_to_message:
            message['reply_to_message'], reply_chat = await tg_parse_message(msg_obj.reply_to_message, reply_parse=True)
        if msg_obj.forward_from: 
            message['forward_from']={}
            message['forward_from']['id'] = msg_obj.forward_from.id
            message['forward_from']['name'] = f'{msg_obj.forward_from.first_name} {msg_obj.forward_from.last_name if msg_obj.forward_from.last_name else ""}'
        elif msg_obj.forward_from_chat: 
            message['forward_from']={}
            message['forward_from']['id'] = msg_obj.forward_from_chat.id
            message['forward_from']['name'] = msg_obj.forward_from_chat.title or f'{msg_obj.forward_from_chat.first_name} {msg_obj.forward_from_chat.last_name if msg_obj.forward_from_chat.last_name else ""}'
        elif msg_obj.forward_sender_name: 
            message['forward_from']={}
            message['forward_from']['name'] = msg_obj.forward_sender_name
        if msg_obj.photo: 
            attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.photo[-1], reply_parse, 'photo')
            attachment['type'] = 'photo'
        if msg_obj.video: 
            attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.video, reply_parse, 'video')
            attachment['type'] = 'video'
        if msg_obj.video_note: 
            attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.video_note, reply_parse, 'video_message')
            attachment['type'] = 'video_message'
        if msg_obj.animation: 
            attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.document, reply_parse)
            attachment['type'] = 'gif'
        if msg_obj.audio:
            attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.audio, reply_parse)
            attachment['type'] = 'audio'
        if msg_obj.voice:
            attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.voice, reply_parse)
            attachment['type'] = 'audio_message'
        if msg_obj.document and not msg_obj.animation: 
            attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.document, reply_parse)
            attachment['type'] = 'gif' if attachment['file_name'].endswith('.gif') else 'doc'
        if msg_obj.sticker:
            if msg_obj.sticker.is_animated:
                attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.sticker, reply_parse, 'sticker_animated')
                attachment['type'] = 'sticker_animated'
                if attachment['bytes']: 
                    attachment['type'] = 'gif'
                    attachment['file_name'] = attachment['file_name'][:-4]+'.gif'
                    attachment['bytes'] = await convert.to_gif(tgs=attachment['bytes'])
            elif msg_obj.sticker.is_video:
                attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.sticker, reply_parse, 'sticker_video')
                attachment['type'] = 'sticker_video'
                if attachment['bytes']: 
                    attachment['type'] = 'gif'
                    attachment['file_name'] = attachment['file_name'][:-5]+'.gif'
                    if attachment['bytes']: attachment['bytes'] = await convert.to_gif(webm=attachment['bytes'])
            else: 
                attachment['file_name'], attachment['size'], attachment['bytes'] = await tg_download_attachment(msg_obj.sticker, reply_parse, 'sticker')
                attachment['type'] = 'sticker'
        if msg_obj.story:
            attachment['type'] = 'story'
            attachment['file_name'] = strings.attachment_story.format(first_name=msg_obj.story.chat.first_name, last_name=msg_obj.story.chat.last_name)
            attachment['size'] = None
        if msg_obj.location: 
            attachment['type'] = 'location'
            attachment['file_name'] = [msg_obj.location.latitude, msg_obj.location.longitude]
            attachment['size'] = None
        if msg_obj.poll: 
            options=[]
            for option in msg_obj.poll.options: options.append(option.text)
            attachment['type'] = 'poll'
            attachment['file_name'] = [msg_obj.poll.question, options]
            attachment['size'] = None
        if msg_obj.contact: 
            name = ''
            if msg_obj.contact.first_name is not None: name += msg_obj.contact.first_name
            if msg_obj.contact.last_name is not None: name += msg_obj.contact.last_name
            attachment['type'] = 'contact'
            attachment['file_name'] = [name, msg_obj.contact.phone_number]
            attachment['size'] = None
        if attachment:
            if msg_obj.media_group_id: attachment['group_id'] = msg_obj.media_group_id
            message['attachments'] = [attachment] # по одному в каждом сообщениии

        return message, chat
    except Exception as e: 
        logger.error(e, exc_info=True)
        return None, None

# = = = = = VK = = = = =

async def vk_check_message_access(chat_id):
    try:
        vk_group_api.messages.getConversationMembers(peer_id=chat_id)
        return True
    except Exception as e: return False

async def vk_get_name(id):
    try:
        id = int(id)
        if id >= 2000000000:
            сonversation = vk_group_api.messages.getConversationsById(peer_ids=[id])
            return сonversation['items'][0]['chat_settings']['title']
        elif id > 0: 
            user = vk_group_api.users.get(user_ids=id)
            return f"{user[0]['first_name']} {user[0]['last_name']}"
        else: 
            return vk_group_api.groups.getById(group_id=abs(id))[0]['name']
    except Exception as e:
        logger.info(f'error while getting name for id {id}: {e}')
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
                upload_server = vk_user_api.video.save(name=name, description=video_description, group_id=config.services['vk']['tag'], wallpost=0, is_private=1, privacy_comment='nobody')
                with open(temp_file.name, 'rb') as file: response = requests.post(upload_server['upload_url'], files={'video_file': file})
                video=json.loads(response.text)
            return f"video{video['owner_id']}_{video['video_id']}"
        elif file_doc or file_gif:
            file_obj = file_doc if file_doc else file_gif
            file_obj.seek(0)
            upload_url = vk_group_api.docs.getMessagesUploadServer(peer_id=to_id)['upload_url']
            if file_gif and name.lower().endswith('.mp4'): 
                name = name[:-4]+'.gif'
                file_obj = await convert.to_gif(mp4=file_obj)
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
    
    except Exception as e: 
        if "'error': 'no extension found', 'error_descr': 'no extension found'" in str(e) and file_gif: name = name+'.gif' if name else 'file.gif'
        logger.warning(e) # vk govno
        if file_video:
            file_doc = file_video
            file_video = None
        if not retry:
            await asyncio.sleep(1)
            args = {'name': name, 'to_id': to_id, 'video_description': video_description, 'file_photo': file_photo, 'file_video': file_video, 'file_gif': file_gif, 'file_doc': file_doc, 'file_audio': file_audio, 'file_audio_message': file_audio_message}
            args = {k: v for k, v in args.items() if v is not None}
            return await vk_attachment_upload(retry=True,**args)
        else: return False
    
async def vk_parse_message(msg_obj):
    try:
        chat={}
        message={'sender':{}}
        chat['id'] = int(msg_obj.get('peer_id') or msg_obj.get('from_id'))
        chat['id_db'] = str(msg_obj.get('peer_id') or msg_obj.get('from_id'))
        chat['is_private'] = False if chat['id'] >= 2000000000 else True
        message['id'] = int(msg_obj.get('conversation_message_id') or msg_obj.get('id')) 
        message['sender']['id'] = msg_obj.get('from_id')
        vk_user_info = vk_group_api.users.get(user_ids=msg_obj.get('from_id'))
        if vk_user_info: message['sender']['name'] = f"{vk_user_info[0]['first_name']} {vk_user_info[0]['last_name']}"
        else: message['sender']['name'] = vk_group_api.groups.getById(group_id=abs(msg_obj.get('from_id')))[0]['name']
        message['text'] = msg_obj.get('text') 
        if msg_obj.get('text') and msg_obj.get('format_data'): 
            message['text_format'] = msg_obj['format_data'].get('items')
        # --- action parse --- 
        if msg_obj.get('action'): 
            action_type = msg_obj.get('action').get('type')
            if action_type == "chat_invite_user": 
                if msg_obj['action']['member_id'] == -config.services['vk']['group_id']: chat['if_invite'] = True
                else: 
                    if msg_obj['action']['member_id'] == msg_obj.get('from_id'): message['text'] = strings.action_join_in_chat
                    else: message['text'] = strings.action_chat_invite_user.format(added_user=(await vk_get_name(msg_obj['action']['member_id'])))
            elif action_type == "chat_invite_user_by_link": message['text'] = strings.action_chat_invite_user_by_link
            elif action_type == "chat_kick_user": 
                if msg_obj['action']['member_id'] == msg_obj.get('from_id'): message['text'] = strings.action_left_from_chat
                else: message['text'] = strings.action_chat_kick_user.format(kicked_user=(await vk_get_name(msg_obj['action']['member_id'])))
            elif action_type == "chat_title_update": message['text'] = strings.action_chat_title_update.format(new_chat_name=msg_obj['action']['text'])
            elif action_type == "chat_photo_update": message['text'] = strings.action_chat_photo_update
            elif action_type == "chat_without_owner_admin": message['text'] = strings.action_chat_without_owner_admin
            elif action_type == "chat_pin_message": message['text'] = strings.action_chat_pin_message
            elif action_type == "chat_unpin_message": message['text'] = strings.action_chat_unpin_message
            else: message['text'] = f'ℹ️ action: {action_type}'
        # --- reply parse --- 
        if msg_obj.get('reply_message', False):
            message['reply_to_message']={}
            message['reply_to_message']['id'] = int(msg_obj['reply_message'].get('conversation_message_id') or msg_obj.get('id'))
            message['reply_to_message']['text'] = msg_obj['reply_message'].get('text')
            if not msg_obj['reply_message'].get('text') and msg_obj['reply_message'].get('attachments'): 
                message['reply_to_message']['attachments'] = []
                for reply_attachment in msg_obj['reply_message']['attachments']:
                    if 'title' in reply_attachment: message['reply_to_message']['attachments'].append([reply_attachment['type'],reply_attachment['title'],None,None])
                    else: message['reply_to_message']['attachments'].append([reply_attachment['type'],reply_attachment['type'],None,None])
        # --- forward parse --- 
        for fwd_msg in msg_obj.get('fwd_messages', []):
            if not message['text']: message['text'] = '' # пихаем в текст, пушо их может быть бесконечно много
            fwd_message, fwd_chat = await vk_parse_message(fwd_msg)
            if 'attachments' in fwd_message:
                for attachment in fwd_message['attachments']:
                    if attachment['type'] in strings.attachments_emoji: fwd_message['text']+=f"\n{strings.attachments_emoji[attachment['type']]} {attachment['file_name'] or attachment['type']}"
                    else: fwd_message['text']+=f"\n{strings.attachments_emoji['unknown']} {attachment['type']}"
            message['text'] += f"\n{strings.msg_forward.format(forward_from=fwd_message['sender']['name'])}{fwd_message['text']}"
        # --- attachment parse --- [type, file_name, size, bytes]
        attachment_list=[]
        if msg_obj.get('attachments'): 
            attachment_list = await vk_parse_attachments(msg_obj['attachments'], (f'{chat['id']}_{message['id']}' if len(msg_obj['attachments'])>1 else None))
        if msg_obj.get('geo'): 
            attachment_list.append({
                'type':'location',
                'file_name':[msg_obj.get('geo')['coordinates']['latitude'],msg_obj.get('geo')['coordinates']['longitude']],
                'size': None
            })
        if attachment_list: message['attachments'] = attachment_list

        return message, chat
    except Exception as e: 
        logger.error(e,exc_info=True)
        return None, None

async def vk_parse_attachments(attachment_list, group_id_name=None):
    try:
        group_id = False
        attachment_list_parsed = []
        for attachment in attachment_list: 
            attachment_parsed = {}
            attachment_parsed['type'] = attachment['type']
            if attachment['type']=='photo':
                file_url = attachment["photo"]["orig_photo"]["url"]
                attachment_parsed['file_name'] = f'photo{attachment["photo"]["id"]}.{file_url.split("?")[0].split(".")[-1]}'
                attachment_parsed['size'] = requests.get(file_url, stream=True).headers.get('Content-Length')
                if len(attachment)>1: group_id = group_id_name
            elif attachment['type']=='video':
                video_info = vk_user_api.video.get(videos=f"{attachment['video']['owner_id']}_{attachment['video']['id']}_{attachment['video']['access_key']}")['items'][0]
                logger.debug(f'video_info = {video_info}')
                if 'direct_url' in video_info: 
                    file_url = video_info['direct_url']
                    attachment_parsed['file_name'] = attachment['video']['title'] or video_info['title']
                    attachment_parsed['size'] = video_info['duration']*1024*1024/6 # примерная оценка размера видео по его длительности (1c=170кб|120с=20мб)
                elif video_info['type'] == 'video_message':
                    file_url = None #video_info['player']
                    attachment_parsed['file_name'] = attachment['video']['title'] or f'video_message{attachment["video"]["id"]}'
                    attachment_parsed['size'] = None
                    attachment['type']='video_message'
                else:
                    file_url = None
                    attachment_parsed['file_name'] = attachment["video"]["title"] or f'video{attachment["video"]["id"]}'
                    attachment_parsed['size'] = None
                attachment_parsed['file_name'] = f'{attachment_parsed['file_name']}.mp4'
            elif attachment['type']=='audio':
                file_url = attachment["audio"]["url"] if attachment["audio"]["url"] != '' else None
                attachment_parsed['file_name'] = f'{attachment["audio"]["artist"]} - {attachment["audio"]["title"]}' # .m3u8
                if file_url is not None: attachment_parsed['size'] = requests.get(file_url, stream=True).headers.get('Content-Length')
                else: attachment_parsed['size'] = None
            elif attachment['type']=='audio_message':
                file_url = attachment["audio_message"]["link_ogg"]
                attachment_parsed['file_name'] = f'audio_message{attachment["audio_message"]["id"]}.ogg'
                attachment_parsed['size'] = requests.get(file_url, stream=True).headers.get('Content-Length')
            elif attachment['type']=='doc':
                file_url = attachment["doc"]["url"]
                attachment_parsed['file_name'] = attachment["doc"]["title"]
                attachment_parsed['size'] = attachment["doc"]["size"]
                if len(attachment)>1: group_id = group_id_name
            elif attachment['type']=='sticker':
                animated = False # 'animation_url' in attachment["sticker"]
                file_url = attachment["sticker"]["animation_url"] if animated else attachment["sticker"]["images_with_background"][-1]["url"]
                attachment_parsed['file_name'] = f'sticker{attachment["sticker"]["sticker_id"]}.{"tgs" if animated else "png"}'
                attachment_parsed['size'] = requests.get(file_url, stream=True).headers.get('Content-Length') if not animated else 1
            elif attachment['type']=='graffiti':
                file_url = attachment["graffiti"]["url"]
                attachment_parsed['file_name'] = f'graffiti{attachment["graffiti"]["id"]}.png'
                attachment_parsed['size'] = requests.get(file_url, stream=True).headers.get('Content-Length')
            elif attachment['type']=='wall':
                if 'from' in attachment["wall"]:
                    if attachment["wall"]["from"].get('name'): attachment_parsed['file_name'] = strings.attachment_wall.format(wall_from=attachment["wall"]["from"]["name"], wall_text=attachment["wall"]["text"])
                    elif attachment["wall"]["from"].get('first_name'): attachment_parsed['file_name'] = strings.attachment_wall.format(wall_from=f'{attachment["wall"]["from"]["first_name"]} {attachment["wall"]["from"]["last_name"]}', wall_text=attachment["wall"]["text"])
                    else: attachment_parsed['file_name'] = strings.attachment_wall.format(wall_from='', wall_text=attachment["wall"]["text"])
                elif 'from_id' in attachment["wall"]: 
                    wall_from = await vk_get_name(attachment["wall"]['from_id'])
                    attachment_parsed['file_name'] = strings.attachment_wall.format(wall_from=wall_from, wall_text=attachment["wall"]["text"])
                else: attachment_parsed['file_name'] = strings.attachment_wall.format(wall_from='', wall_text=attachment["wall"]["text"])
                if attachment["wall"].get('attachments'):
                    group_id = f'{group_id_name}_{attachment["wall"]["id"]}'
                    for wall_attachment in await vk_parse_attachments(attachment["wall"]['attachments'], group_id_name=group_id): 
                        attachment_list_parsed.append(wall_attachment)
                attachment_parsed['size'] = None
            elif attachment['type']=='story':
                attachment_parsed['file_name'] = strings.attachment_story.format(first_name=attachment["story"]["owner_id"], last_name='')
                attachment_parsed['size'] = None
            elif attachment['type']=='link':
                attachment_parsed['file_name'] = attachment["link"]["url"]
                attachment_parsed['size'] = None
            elif attachment['type']=='poll':
                options=[]
                for option in attachment["poll"]["answers"]: options.append(option["text"])
                attachment_parsed['file_name'] = attachment["poll"]["question"]
                attachment_parsed['size'] = None
                file = options
            else:
                attachment_parsed['file_name'] = attachment["type"]
                attachment_parsed['size'] = None
            if config.attachments_forward and attachment_parsed['size'] is not None:
                attachment_parsed['size'] = int(attachment_parsed['size'])
                if attachment_parsed['size']/1024/1024 < config.attachments_max_size_mb and attachment_parsed['size']>0 and file_url is not None:
                    try: 
                        if attachment['type']=='audio': 
                            file = BytesIO((await convert.to_mp3(url=file_url)))
                        elif attachment['type'] in ['video','video_message']:
                            file = await convert.to_mp4(url_vk=file_url)
                            attachment_parsed['size'] = len(file)
                            file = BytesIO(file)
                        elif attachment['type']=='sticker' and animated:
                            file = BytesIO((await convert.to_tgs(json_file=requests.get(file_url).content)))
                        else:
                            file = BytesIO(requests.get(file_url).content)
                    except Exception as e:
                        logger.warning(e, exc_info=True)
                        file = None
                else: file = None
            elif not attachment['type']=='poll': file = None
            attachment_parsed['bytes'] = file
            if group_id: attachment_parsed['group_id'] = group_id
            attachment_list_parsed.append(attachment_parsed)
        return attachment_list_parsed
    except Exception as e: logger.error(e,exc_info=True)

# === DC catcher ===
intents = discord.Intents.default()
intents.message_content = True  # нужно для чтения сообщений
dc_bot = commands.Bot(command_prefix="/", intents=intents)
@dc_bot.event
async def on_reaction_add(reaction, user): logger.debug(reaction, user)
@dc_bot.event
async def on_raw_reaction_add(payload): logger.debug(payload)
#@dc_bot.event
#async def on_error(event, *args, **kwargs): logger.warning(event, *args)
#@dc_bot.event
#async def on_member_join(member): logger.debug(member)
#@dc_bot.event
#async def on_raw_member_remove(payload): logger.debug(payload)
@dc_bot.event
async def on_message(message):
    if message.author == dc_bot.user: return
    await message_navigator(service_from='dc',msg_obj=message)
    
# === TG catcher ===
tg_bot = Bot(token=config.services['tg']['token'])
tg_dispatcher = Dispatcher(storage=MemoryStorage())
@tg_dispatcher.message()
async def handle_telegram_message(message: Message):
    try: await message_navigator(service_from='tg',msg_obj=message)
    except Exception as e: logger.critical(e, exc_info=True)
# === VK catcher ===
vk_group_session = vk_api.VkApi(token=config.services['vk']['token'])
vk_group_api = vk_group_session.get_api() # group session api
vk_upload = vk_api.upload.VkUpload(vk_group_session)
vk_user_api = vk_api.VkApi(token=config.services['vk']['admin_user_token']).get_api() # group admin (user) session api
def run_vk_bot_polling(loop):
    try:
        for event in VkBotLongPoll(vk_group_session, config.services['vk']['group_id']).listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                if event.object.message['from_id'] == -config.services['vk']['group_id']: continue  # пропускаем сообщения от самого бота
                asyncio.run_coroutine_threadsafe(message_navigator(service_from='vk', msg_obj=event.object.message), loop)
    except requests.exceptions.ReadTimeout as e:
        logger.warning(e)
        run_vk_bot_polling(loop)  # перезапуск при ошибке
    except Exception as e:
        logger.error(e, exc_info=True)
        run_vk_bot_polling(loop)  # перезапуск при ошибке
# === START ===
async def main():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_vk_bot_polling, args=(loop,), daemon=True).start() 
    asyncio.create_task(message_sender())
    asyncio.create_task(message_buffer_worker())
    asyncio.create_task(dc_bot.start(config.services['dc']['token']))
    await db.initialization()
    if config.message_max_len + config.message_reply_max_len > 4000: logger.warning("telegram message len limit is 4096 symbols. check limits in config file")
    if config.attachments_max_size_mb > 8: logger.warning('discord file size limit is 8 MB. check limits in config file')
    if config.attachments_max_size_mb > 20: logger.warning('telegram file size limit is 20 MB. check limits in config file')
    logger.info("bot started")
    await tg_dispatcher.start_polling(tg_bot)
    logger.warning("bot stopped")
if __name__ == "__main__":
    asyncio.run(main())
