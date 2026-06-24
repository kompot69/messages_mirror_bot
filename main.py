import asyncio, threading, time, logging, vk_api, requests, re
from io import BytesIO
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
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

# === очередь отправки сообщений ===
message_bus = asyncio.Queue()
async def msg_sender(): # ловим cooбщения
    vk_session = vk_api.VkApi(token=config.vk_user_token)
    vk = vk_session.get_api()
    vk_upload = VkUpload(vk_session)
    chat_last_sender_nick = {}
    while True:
        service_to, message, to_id, attachments = await message_bus.get()
        logger.debug(f'sending message to {service_to} {to_id}')

        if isinstance(message, list):
            logger.debug(f'message = {message}')
            if message[1] == chat_last_sender_nick.get(service_to+str(to_id)): message_text = message[0]+message[2]
            else: message_text = message[0]+message[1]+message[2]
            chat_last_sender_nick[service_to+str(to_id)] = message[1]
        else: message_text = message

        if service_to == "tg": 
            try: 
                if 'tread' in to_id: to_id, tread = to_id.split('tread')
                else: tread = False
                
                if message_text: 
                    if tread: await tg_bot.send_message(to_id, message_text, message_thread_id=tread) 
                    else: await tg_bot.send_message(to_id, message_text) 

                if attachments:
                    for attachment in attachments: # [attachment_type, file_name, file_size, bytes]
                        if attachment[3] is None and attachment[2] is not None and attachment[2] != 0 and attachment[0] != 'wall' and attachment[0] in strings.attachments_emoji:
                            if tread: await tg_bot.send_message(to_id, f'{strings.attachments_emoji[attachment[0]]} {attachment[1]} ({round(attachment[2]/1024/1024,2)}МБ)', message_thread_id=tread)
                            else: await tg_bot.send_message(to_id, f'{strings.attachments_emoji[attachment[0]]} {attachment[1]} ({round(attachment[2]/1024/1024,2)}МБ)')
                        else:
                            if attachment[0] == 'photo': 
                                if tread: await tg_bot.send_photo(to_id, attachment[3], message_thread_id=tread)
                                else: await tg_bot.send_photo(to_id, attachment[3])
                            elif attachment[0] == 'video': 
                                if tread: await tg_bot.send_video(to_id, attachment[3], caption=attachment[1], message_thread_id=tread)
                                else: await tg_bot.send_video(to_id, attachment[3], caption=attachment[1])
                            elif attachment[0] == 'audio': 
                                if tread: await tg_bot.send_audio(to_id, attachment[3], caption=attachment[1], message_thread_id=tread)
                                else: await tg_bot.send_audio(to_id, attachment[3], caption=attachment[1])
                            elif attachment[0] == 'doc': 
                                if tread: await tg_bot.send_document(to_id, attachment[3], message_thread_id=tread)
                                else: await tg_bot.send_document(to_id, attachment[3])
                            elif attachment[0] == 'sticker' or attachment[0] == 'graffiti' : 
                                if tread: await tg_bot.send_sticker(to_id, attachment[3], message_thread_id=tread)
                                else: await tg_bot.send_sticker(to_id, attachment[3])
                            elif attachment[0] == 'audio_message': 
                                if tread: await tg_bot.send_voice(to_id, attachment[3], message_thread_id=tread)
                                else: await tg_bot.send_voice(to_id, attachment[3])
                            elif attachment[0] == 'video_message': 
                                if tread: await tg_bot.send_video_note(to_id, attachment[3], message_thread_id=tread)
                                else: await tg_bot.send_video_note(to_id, attachment[3])
                            elif attachment[0] == 'location': 
                                if tread: await tg_bot.send_location(to_id, latitude=attachment[3][0], longitude=attachment[3][1], message_thread_id=tread)
                                else: await tg_bot.send_location(to_id, latitude=attachment[3][0], longitude=attachment[3][1])
                            elif attachment[0] == 'wall': 
                                if tread: await tg_bot.send_message(to_id, f'{strings.attachments_emoji["wall"]} {attachment[1]}', message_thread_id=tread)
                                else: await tg_bot.send_message(to_id, f'{strings.attachments_emoji["wall"]} {attachment[1]}')
                            elif attachment[0] == 'story': 
                                if tread: await tg_bot.send_message(to_id, f'{strings.attachments_emoji["story"]} {attachment[1]}', message_thread_id=tread)
                                else: await tg_bot.send_message(to_id, f'{strings.attachments_emoji["story"]} {attachment[1]}')
                            else: 
                                if tread: await tg_bot.send_message(to_id, f'{strings.attachments_emoji["unknown"]} {attachment[1]}', message_thread_id=tread)
                                else: await tg_bot.send_message(to_id, f'{strings.attachments_emoji["unknown"]} {attachment[1]}')

            except TelegramForbiddenError as e: logger.warning(f'error send to {service_to} {to_id}: {e}')
            except Exception as e: logger.error(e,exc_info=True)
        elif service_to == "vk": 
            try: 
                if message_text: vk.messages.send( peer_id=to_id, message=message_text, random_id=0 )
                if attachments:
                    for attachment in attachments: # [attachment_type, file_name, file_size, bytes]
                        if attachment[3] is None and attachment[0] !='story':
                            vk.messages.send( peer_id=to_id, message=f'{strings.attachments_emoji[attachment[0]]} {attachment[1]} ({round(attachment[2]/1024/1024,2)}МБ)', random_id=0 )
                        else:
                            if attachment[0] == 'photo': 
                                vk_attachment = vk_upload.photo_messages(attachment[3])
                                vk.messages.send(peer_id=to_id, random_id=0, attachment=f"photo{vk_attachment[0]['owner_id']}_{vk_attachment[0]['id']}")
                            elif attachment[0] == 'video' or attachment[0] == 'gif': # [27] Group authorization failed: method is unavailable with group auth.
                                vk_attachment = vk_upload.video(video_file=attachment[3], name=attachment[1])
                                vk.messages.send(peer_id=to_id, random_id=0, attachment=f"video{vk_attachment['owner_id']}_{vk_attachment['video_id']}")
                            elif attachment[0] == 'audio': vk.messages.send( peer_id=to_id, message=f'{strings.attachments_emoji[attachment[0]]} {attachment[1]} ({round(attachment[2]/1024/1024,2)}МБ)', random_id=0 )
                                #vk_attachment = vk_upload.photo_messages(attachment[3])
                                #vk.messages.send(peer_id=to_id, random_id=0, attachment=f"photo{vk_attachment[0]['owner_id']}_{vk_attachment[0]['id']}")
                            elif attachment[0] == 'doc':
                                file_obj = attachment[3]
                                file_obj.seek(0)
                                upload_url = vk.docs.getMessagesUploadServer(peer_id=to_id)['upload_url']
                                r = requests.post(upload_url, files={'file': (attachment[1], file_obj)})
                                result = r.json()
                                doc = vk.docs.save(file=result['file'])['doc']
                                attachment_str = f"doc{doc['owner_id']}_{doc['id']}"
                                vk.messages.send(peer_id=to_id, random_id=0, attachment=attachment_str )
                            elif attachment[0] == 'sticker': 
                                vk_attachment = vk_upload.photo_messages(attachment[3])
                                vk.messages.send(peer_id=to_id, random_id=0, attachment=f"photo{vk_attachment[0]['owner_id']}_{vk_attachment[0]['id']}")
                            elif attachment[0] == 'audio_message': vk.messages.send( peer_id=to_id, message=f'{strings.attachments_emoji[attachment[0]]} {attachment[1]} ({round(attachment[2]/1024/1024,2)}МБ)', random_id=0 )
                                #vk_attachment = vk_upload.audio_message(audio=("voice.ogg", attachment[3]),peer_id=to_id)
                                #vk.messages.send(peer_id=to_id, random_id=0, attachment=f"audio{vk_attachment['audio_message']['owner_id']}_{vk_attachment['audio_message']['id']}")
                            elif attachment[0] == 'video_message': vk.messages.send( peer_id=to_id, message=f'{strings.attachments_emoji[attachment[0]]} {attachment[1]} ({round(attachment[2]/1024/1024,2)}МБ)', random_id=0 )
                                #vk_attachment = vk_upload.photo_messages(attachment[3])
                                #vk.messages.send(peer_id=to_id, random_id=0, attachment=f"photo{vk_attachment[0]['owner_id']}_{vk_attachment[0]['id']}")
                            elif attachment[0] == 'story': 
                                vk.messages.send( peer_id=to_id, message=f'{strings.attachments_emoji[attachment[0]]} {attachment[1]}', random_id=0)
                            elif attachment[0] == 'location': 
                                vk.messages.send( peer_id=to_id, lat=attachment[3][0], long=attachment[3][1], random_id=0)
                            elif attachment[0] == 'poll': 
                                poll = f'{strings.attachments_emoji["poll"]} {attachment[1]}'
                                for option in attachment[3]: poll += f'\n ● {option}'
                                vk.messages.send( peer_id=to_id, message=poll, random_id=0 )
                            elif attachment[0] == 'contact':
                                vk.messages.send( peer_id=to_id, message = f'{strings.attachments_emoji["contact"]} {attachment[1]}\n{attachment[3]}', random_id=0 )
                            else: vk.messages.send( peer_id=to_id, message=f'{strings.attachments_emoji["unknown"]} {attachment[1]}', random_id=0)

            except vk_api.exceptions.ApiError as e: logger.warning(f'error send to {service_to} {to_id}: {e}', exc_info=True)
            except Exception as e: logger.error(e, exc_info=True)

# === парсер входящих сообщений ===
async def msg_parser(service0, msg_obj):
    logger.debug(f'message from {service0} catched: {str(msg_obj)}')
    try:
        attachment_list=[]

        # === telegram parser ===
        if service0 == 'tg':
            service1 = 'vk'
            service0_chat_id = str(msg_obj.chat.id)
            if msg_obj.message_thread_id: service0_chat_id += f'tread{str(msg_obj.message_thread_id)}'
            service0_msg_text = msg_obj.text or msg_obj.caption or ''
            service0_chat_is_private = msg_obj.chat.type == 'private'
            service0_user_nick = f"{msg_obj.from_user.first_name} {msg_obj.from_user.last_name}" if msg_obj.from_user.last_name else msg_obj.from_user.first_name
            is_invite = False
            if msg_obj.new_chat_members: # invite check
                for user in msg_obj.new_chat_members:
                    if config.tg_bot_tag == user.username and int(config.tg_token.split(':')[0]) == user.id: is_invite = True
                    else: service0_msg_text = strings.join_in_chat
            # --- reply / forward parse ---
            reply_to_msg_text = getattr(msg_obj.reply_to_message, 'text', None)
            #if not reply_to_msg_text: reply_to_msg_text = getattr(msg_obj.reply_to_message, 'document', None)
            if msg_obj.forward_from or getattr(msg_obj, 'forward_sender_name', None) or getattr(msg_obj, 'forward_from_chat', None):
                forward_from_name='unknown'
                if getattr(msg_obj, 'forward_sender_name', None): forward_from_name={msg_obj.forward_sender_name}
                elif getattr(msg_obj.forward_from, 'first_name', None) and getattr(msg_obj.forward_from, 'last_name', None): forward_from_name=f'{msg_obj.forward_from.first_name} {msg_obj.forward_from.last_name}'
                elif getattr(msg_obj.forward_from, 'first_name', None): forward_from_name=msg_obj.forward_from.first_name
                elif getattr(msg_obj, 'forward_from_chat', None): forward_from_name=msg_obj.forward_from_chat.title
                service0_user_nick += strings.msg_forward.format(forward_from=forward_from_name)

            # --- attachment parse --- [attachment_type, file_name, file_size, bytes]

            if msg_obj.photo:
                file_obj = await tg_bot.get_file(msg_obj.photo[-1].file_id)
                file_name = f"photo{file_obj.file_unique_id}.{file_obj.file_path.split('.')[1]}"
                file_size = msg_obj.photo[-1].file_size
                if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                    try: 
                        file = BytesIO()
                        await tg_bot.download_file(file_obj.file_path, destination=file)
                        file.seek(0)
                    except Exception as e:
                        logger.warning(e, exc_info=True)
                        file = None
                else: file = None
                attachment_list.append(['photo', file_name, file_size, file])

            if msg_obj.video: 
                try: 
                    file_obj = await tg_bot.get_file(msg_obj.video.file_id)
                    file_name = msg_obj.video.file_name or f"video{file_obj.file_unique_id}.{file_obj.file_path.split('.')[1]}"
                    file_size = msg_obj.video.file_size
                    if config.attachments_forward and file_size/1024/1024 < config.attachments_max_size_mb:
                        try: 
                            file = BytesIO()
                            await tg_bot.download_file(file_obj.file_path, destination=file)
                            file.seek(0)
                        except Exception as e:
                            logger.warning(e, exc_info=True)
                            file = None
                    else: file = None
                except TelegramBadRequest as e: 
                    logger.warning(f'cannot get video from tg: {e}')
                    file_name = msg_obj.video.file_name or f"video{file_obj.file_unique_id}.{file_obj.file_path.split('.')[1]}"
                    file_size = msg_obj.video.file_size
                    file = None
                attachment_list.append(['video', file_name, file_size, file])

            if msg_obj.animation: 
                file_obj = await tg_bot.get_file(msg_obj.animation.file_id)
                file_name = msg_obj.animation.file_name
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
                attachment_list.append(['doc', file_name, file_size, file])

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

        # === vkontakte parser ===
        elif service0 == 'vk':
            service1 = 'tg'
            service0_chat_id = str(msg_obj.get('peer_id', 0))
            service0_msg_text = msg_obj.get('text', '')
            service0_chat_is_private = False if int(service0_chat_id) >= 2000000000 else True
            service0_user_profile_info=vk_api.VkApi(token=config.vk_user_token).get_api().users.get(user_ids=msg_obj.get('from_id'))[0]
            service0_user_nick = f"{service0_user_profile_info['first_name']} {service0_user_profile_info['last_name']}"
            is_invite = False 
            if msg_obj.get('action'): # invite check
                if msg_obj.get('action').get('type') == "chat_invite_user": 
                    if msg_obj['action']['member_id'] < 0: is_invite = True # id < 0 = bot
                    else: service0_msg_text = strings.added_in_chat.format(added_by=msg_obj['from_id'], added_user=msg_obj['action']['member_id'])
                elif msg_obj.get('action').get('type') == "chat_kick_user": 
                    service0_msg_text = strings.kicked_from_chat.format(kicked_by=msg_obj['from_id'], kicked_user=msg_obj['action']['member_id'])
            # --- reply / forward parse --- 
            reply_to_msg_text = msg_obj.get('reply_message', {}).get('text') # не видит ответ на пересланые сообщения 
            for fwd_msg in msg_obj.get('fwd_messages', []):
                text = fwd_msg.get('text') if fwd_msg.get('text') else '[unknown_message_type]'
                forward_from_name=fwd_msg.get('from_id')
                service0_user_nick += f" {strings.msg_forward.format(forward_from=forward_from_name)}\n{text}"
            # --- attachment parse --- [attachment_type, file_name, file_size, bytes]
            if msg_obj.get('geo'):
                attachment_list.append(['location', 'location', 0, [msg_obj.get('geo')['coordinates']['latitude'],msg_obj.get('geo')['coordinates']['longitude']]])

            if msg_obj.get('attachments'):
                for attachment in msg_obj.get('attachments'): 
                    if attachment['type']=='photo':
                        file_url = attachment["photo"]["orig_photo"]["url"]
                        file_name = f'photo{attachment["photo"]["id"]}.{file_url.split("?")[0].split(".")[-1]}'
                        file_size = requests.get(file_url, stream=True).headers.get('Content-Length')

                    elif attachment['type']=='video':
                        if attachment['video']['type']['tracking_info']=='video_message':
                            attachment['type']='video_message'
                            file_url = None
                            file_name = f'video_message{attachment["video"]["id"]}'
                            file_size = 0
                        else:
                            file_url = None
                            file_name = f'video{attachment["video"]["id"]}'
                            file_size = 0

                    elif attachment['type']=='audio':
                        file_url = attachment["audio"]["url"]
                        file_name = f'{attachment["audio"]["artist"]} - {attachment["audio"]["title"]}' # .m3u8
                        file_size = 0 #requests.get(file_url, stream=True).headers.get('Content-Length')

                    elif attachment['type']=='doc':
                        file_url = attachment["doc"]["url"]
                        file_name = attachment["doc"]["title"]
                        file_size = attachment["doc"]["size"]

                    elif attachment['type']=='sticker':
                        file_url = attachment["sticker"]["images_with_background"][-1]["url"]
                        file_name = f'sticker{attachment["sticker"]["sticker_id"]}.png'
                        file_size = requests.get(file_url, stream=True).headers.get('Content-Length')
                    
                    elif attachment['type']=='graffiti':
                        file_url = attachment["graffiti"]["url"]
                        file_name = f'graffiti{attachment["graffiti"]["id"]}.png'
                        file_size = requests.get(file_url, stream=True).headers.get('Content-Length')
                        
                    elif attachment['type']=='audio_message':
                        file_url = attachment["audio_message"]["link_ogg"]
                        file_name = f'audio_message{attachment["audio_message"]["id"]}.ogg'
                        file_size = requests.get(file_url, stream=True).headers.get('Content-Length')

                    elif attachment['type']=='wall':
                        if attachment["wall"]["from"].get('name'): file_name = strings.attachment_wall.format(wall_from=attachment["wall"]["from"]["name"], wall_text=attachment["wall"]["text"])
                        elif attachment["wall"]["from"].get('first_name'): file_name = strings.attachment_wall.format(wall_from=f'{attachment["wall"]["from"]["first_name"]} {attachment["wall"]["from"]["last_name"]}', wall_text=attachment["wall"]["text"])
                        else: file_name = strings.attachment_wall.format(wall_from='', wall_text=attachment["wall"]["text"])
                        file_size = None

                    elif attachment['type']=='story':
                        file_name = strings.attachment_story.format(first_name=attachment["story"]["owner_id"], last_name='') # f'story{attachment["story"]["id"]}'
                        file_size = None

                    elif attachment['type']=='link':
                        file_name = attachment["link"]["url"]
                        file_size = None

                    else:
                        file_name = attachment["type"]
                        file_size = 0

                    if config.attachments_forward and file_size is not None:
                        file_size = int(file_size)
                        if file_size/1024/1024 < config.attachments_max_size_mb and file_size>0 and file_url is not None:
                            try: file = BufferedInputFile(requests.get(file_url).content,filename=file_name)
                            except Exception as e:
                                logger.warning(e, exc_info=True)
                                file = None
                        else: file = None
                    else: file = None
                    attachment_list.append([attachment['type'], file_name, file_size, file])
                
    except Exception as e: logger.error(e, exc_info=True)

    logger.debug(f'new message from {service0} {service0_chat_id} parsed: {service0_msg_text}')
    if len(attachment_list) > 0 : logger.debug('attachment_list = '+str(attachment_list))

    # === command / invite parse ===
    command_answer = await commands.if_command(service0, service0_msg_text, service0_chat_id, service0_chat_is_private)
    if command_answer is not None and command_answer != False: 
        return await message_bus.put((service0, command_answer, service0_chat_id, None))
    elif is_invite: 
        logger.info(f'bot was invited to {service0_chat_id} {service0} chat')
        return await message_bus.put((service0, strings.cmd_start_public_chat, service0_chat_id, None))

    # === setting message to send ===
    if True: 
        service0_name, service1_name, service1, service1_bot_link = await commands.get_strings(service0)
        # --- connect check ---
        service1_chat_id = await db.get_connected_chat(service0, service0_chat_id) # чек подключения
        if not service1_chat_id: # нет подключения вообще
            if service0_chat_is_private: await message_bus.put((service0, strings.cmd_mirror_no_connect.format(time=strings.time_now,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id), service0_chat_id, None))
            return logger.debug(f'чат {service0} {service0_chat_id} не подключен к чату {service1}')
        if await db.get_connected_chat(service1, service1_chat_id) != service0_chat_id: # нет ответного подключения
            if service0_chat_is_private: await message_bus.put((service0, strings.cmd_mirror_no_connect_mutually.format(time=strings.time_now,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id,service1_chat_id=service1_chat_id), service0_chat_id, None))
            return logger.info(f'чат {service0} {service0_chat_id} подключен к чату {service1} {service1_chat_id}, который не подключен в ответ')
        # --- replys ---
        if reply_to_msg_text:
            if reply_to_msg_text.startswith(strings.msg_reply_prefix): reply_to_msg_text=reply_to_msg_text[reply_to_msg_text.find('\n')+1:] # обрезка реплаев в реплаях
            if reply_to_msg_text.startswith(strings.msg_nick_prefix): reply_to_msg_text=reply_to_msg_text[reply_to_msg_text.find('\n')+1:] # обрезка ников в реплаях
            if len(reply_to_msg_text)>config.message_reply_max_len: reply_to_msg_text = reply_to_msg_text[:config.message_reply_max_len]+'...' # обрезка длины
            reply_to_msg_text = reply_to_msg_text.replace("\n", " ")
            reply_to_msg_text = f'{strings.msg_reply_prefix} {reply_to_msg_text}\n'
        if len(service0_msg_text) > config.message_max_len: service0_msg_text=service0_msg_text[:config.message_max_len]+"\n [ ... ]"
        message = [reply_to_msg_text or '', f'{strings.msg_nick_prefix} {service0_user_nick}\n', service0_msg_text]
        await message_bus.put((service1, message, service1_chat_id, attachment_list)) 

# === TG catcher ===
tg_bot = Bot(token=config.tg_token)
dp = Dispatcher(storage=MemoryStorage())
@dp.message()
async def handle_telegram_message(message: Message):
    try: await msg_parser(service0='tg',msg_obj=message)
    except Exception as e: logger.critical(e, exc_info=True)
# === VK catcher ===
def run_vk_bot_polling(loop):
    vk_session = vk_api.VkApi(token=config.vk_user_token)
    try:
        for event in VkBotLongPoll(vk_session, config.vk_group_id).listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                if event.object.message['from_id'] == -config.vk_group_id: continue  # пропускаем сообщения от самого бота
                asyncio.run_coroutine_threadsafe(msg_parser(service0='vk', msg_obj=event.object.message), loop)
    except Exception as e:
        logger.critical(e, exc_info=True)
        time.sleep(3)
        run_vk_bot_polling(loop)  # перезапуск при ошибке

# === MAIN ===
async def main():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_vk_bot_polling, args=(loop,), daemon=True).start() 
    asyncio.create_task(msg_sender())
    await db.initialization()
    logger.debug("bot started")
    await dp.start_polling(tg_bot)
    logger.debug("bot stopped")
if __name__ == "__main__":
    asyncio.run(main())
