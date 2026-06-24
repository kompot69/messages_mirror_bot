import config
welcome_message='Привет! Чтобы настроить зеркалирование сообщений из этого чата разрешите мне доступ к сообщениям, а затем напишите /mirror'

msg_nick_prefix='👤'
msg_reply_prefix='↪' # ↪ ➥ ⮩ ⤥ ⤷ ⮎ ⮱
msg_forward=' [⮎ переслано от {forward_from} ]'

attachment_wall='Запись со стены {wall_from} \n\n{wall_text}'
attachment_story='История от {first_name} {last_name}'
attachment_video_description='Видеозапись от {sender_name}'
attachments_emoji = { # type : icon
    'photo':'🖼',
    'video':'🎦',
    'gif':'🎦',
    'story':'▶️',
    'audio':'🎵',
    'doc':'📄',
    'sticker':'🔘',
    'graffiti':'🔘',
    'audio_message':'🗣',
    'video_message':'▶️',
    'location':'📍',
    'poll':'📊',
    'contact':'📞',
    'link':'🌐',
    'wall':'📝',
    'unknown':'❔'
}

action_join_in_chat='Присоеденяется к чату'
action_added_in_chat='Добавляет {added_user} в чат'
action_kicked_from_chat='Удаляет {kicked_user} из чата'
action_new_chat_name='Изменяет название чата на "{new_chat_name}"'
action_new_chat_avatar='Изменяет аватар чата'
notificate_attachments_error='ℹ️ Не удалось переслать вложение: {attachment}'
chat_connect_to_request='ℹ️ Запрос на подключение этого чата к чату {service_name} "{service_chat_name}" (ID: {service_chat_id})' # btn "Подключить этот чат к чату ID"
chat_disconnected_from='ℹ️ Этот чат отключен от чата {service_name} "{service_chat_name}" (ID: {service_chat_id})'
chat_connected_to='☑️ Этот чат подключен к чату {service_name} "{service_chat_name}" (ID: {service_chat_id})'

chat_has_no_connected_chats='Проверьте настройки поключенных чатов командой /mirror'
connect_instruction='Для подключения: \n1. Добавьте бота в Ваш чат {other_service_name}: {other_service_link} \n2. Разрешите боту доступ к сообщениям \n3. Введите команду " /mirror {service0_cutag}{service0_chat_id} " в чате {other_service_name}'
admin_text='Версия: {bot_version}\nМакс.длина сообщения: {message_max_len}'
def cmd_mirror_status(service0, service0_chat_id, other_services:dict, service0_message_access=True, admin_text=False): # other_services service: [cutag, chat_id, chat_name, connected_mutually]
    answer = f'ℹ️ Статус зеркалирования для этого чата {config.services[service0]['name']}:'
    for service in other_services:
        if service[1]: 
            if service[2] and service[2]!='[неизвестно]': answer += f'\n\n🔘 Подключен чат {config.services[service[0]]['name']} "{service[2]}" (ID: {service[1]}).'
            else: answer += f'\n\n🔘 Подключен чат {config.services[service[0]]['name']} c ID {service[1]}.'
            if not service[3]: 
                answer += f'\n Чат не подключен в ответ. '
                answer += connect_instruction.format(other_service_name=config.services[service[0]]['name'], other_service_link=config.services[service[0]]['link'], service0_cutag=service0, service0_chat_id=service0_chat_id)
        else: 
            answer += f'\n\n🔘 Чат {config.services[service[0]]['name']} не подключен. '
            answer += connect_instruction.format(other_service_name=config.services[service[0]]['name'], other_service_link=config.services[service[0]]['link'], service0_cutag=service0, service0_chat_id=service0_chat_id)
    if not service0_message_access: answer += '\n\n❗️ У бота нет доступа к сообщениям в этом чате, разрешите боту доступ к сообщениям для их пересылки!'
    if config.attachments_forward: answer += f'\n\nℹ️ Доступна пересылка вложений весом до {config.attachments_max_size_mb} МБ'
    else: answer += f'\n\nℹ️ Пересылка вложений отключена'
    if admin_text: answer += f'\n{admin_text}'
    return answer
    # btns Отключить Добавить в чат
def cmd_mirror_connecting(service0, service0_chat_id, other_service:list, service0_message_access=True, connected_mutually=True): # other_service: [cutag, chat_id, chat_name]
    if other_service == 'disconnect': 
        answer = f'☑️ Теперь этот чат {config.services[service0]['name']} отключен от всех других чатов'
    elif other_service == 'wrong_id': 
        answer = f'❗ Неправильно указан ID подключаемого чата. \nДля подключения введите /mirror и ID чата.\nПример: /mirror vk123456789'
    else:
        if other_service[2] and other_service[2]!='[неизвестно]': answer = f'☑️ Теперь этот чат {config.services[service0]['name']} подключен к чату {config.services[other_service[0]]['name']} "{other_service[2]}" (ID: {other_service[1]})'
        else: answer = f'☑️ Теперь этот чат {config.services[service0]['name']} подключен к чату {config.services[other_service[0]]['name']} c ID {other_service[1]}'
        if not connected_mutually:
            answer += f', но чат {config.services[other_service[0]]['name']} не подключен в ответ. '
            answer += connect_instruction.format(other_service_name=config.services[other_service[0]]['name'], other_service_link=config.services[other_service[0]]['link'], service0_cutag=service0, service0_chat_id=service0_chat_id)
    if not service0_message_access: answer += '\n\n❗️ У бота нет доступа к сообщениям в этом чате, разрешите боту доступ к сообщениям для их пересылки!'
    return answer
