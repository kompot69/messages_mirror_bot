msg_nick_prefix='👤'
msg_reply_prefix='↪' # ↪ ➥ ⮩ ⤥ ⤷ ⮎ ⮱
msg_forward=' [⮎ переслано от {forward_from} ]'
attachment_wall='Запись со стены {wall_from} \n\n{wall_text}'
attachment_story='История от {first_name} {last_name}'
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

forward_on='Включена'
forward_off='Выключена'
time_now='Сейчас'
time_current='Теперь'
join_in_chat='Присоеденился(ась) к чату'
added_in_chat='➕ {added_by} добавляет {added_user} в чат'
kicked_from_chat='✖️ {kicked_by} удаляет {kicked_user} из чата'

# === команды ===
cmd_start_private_chat='Привет! Чтобы настроить зеркалирование сообщений из этого чата напишите команду /mirror'
cmd_start_public_chat='Привет! Чтобы настроить зеркалирование сообщений из этого чата разрешите мне доступ к сообщениям, а затем напишите /mirror'

cmd_mirror_no_connect="""ℹ️ {time} этот чат {service0_name} не подключен к чату {service1_name}.\n
Для подключения зеркалирования этого чата {service0_name} в чат {service1_name}:
1. Добавьте бота {service1_bot_link} в Ваш чат {service1_name}
2. Разрешите боту доступ к сообщениям 
3. Введите команду " /mirror {service0_chat_id} " в чате {service1_name}
\nℹ️ Для подключения личного диалога {service1_name} - см. пункт 3"""

cmd_mirror_no_connect_mutually="""ℹ️ {time} этот чат {service0_name} подключен к чату {service1_name} c ID {service1_chat_id}, но чат {service1_name} не подключен в ответ.\n
Для подключения зеркалирования этого чата {service0_name} в чат {service1_name}:
1. Добавьте бота {service1_bot_link} в Ваш чат {service1_name}
2. Разрешите боту доступ к сообщениям 
3. Введите команду " /mirror {service0_chat_id} " в чате {service1_name}
\nℹ️ Для подключения личного диалога {service1_name} - см. пункт 3"""

cmd_mirror="""✅ {time} этот чат {service0_name} подключен к чату {service1_name} c ID {service1_chat_id}.
ℹ️ Для отключения используйте команду " /mirror off "
ℹ️ {forward_state} пересылка файлов весом до {forward_limit}МБ
ℹ️ Если бот не видит Ваши сообщения - проверьте что у него есть доступ к сообщениям"""

cmd_mirror_arg_uncorrect="""❗ Неправильно указан ID подключаемого чата. 
Для подключения введите /mirror и ID чата {service1_name}.
Пример: /mirror 123456789"""

cmd_mirror_disconnect='ℹ️ {time} этот чат {service0_name} отключен от чата {service1_name}'
