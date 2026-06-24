msg_nick_prefix='👤'
msg_reply_prefix='↪' # ↪ ➥ ⮩ ⤥ ⤷ ⮎ ⮱
msg_forward=' [⮎ переслано от {forward_from_name} ]'
msg_attachment_prefix_doc='📄'
msg_attachment_prefix_image='🖼'
msg_attachment_prefix_animation='🎦'
msg_attachment_prefix_video='🎦'
msg_attachment_prefix_audio='🎵'
msg_attachment_prefix_voice='🗣'
msg_attachment_prefix_video_note='▶️'
msg_attachment_unknown='[неизвестное вложение]'
# === команды ===
forward_on='Доступна'
forward_off='Выключена'
time_now='Сейчас'
time_current='Теперь'
cmd_start_private_chat='Привет! Чтобы настроить зеркалирование сообщений из этого чата напишите команду /mirror'
cmd_start_public_chat='Привет! Чтобы настроить зеркалирование сообщений из этого чата разрешите мне доступ к сообщениям, а затем напишите /mirror'
cmd_mirror_no_connect="""ℹ️ {time} этот чат {this_service_name} не подключен к чату {other_service_name}.\n
Для подключения зеркалирования этого чата {this_service_name} в чат {other_service_name}:
1. Добавьте бота {other_service_bot_link} в Ваш чат {other_service_name}
2. Разрешите боту доступ к сообщениям 
3. Введите команду " /mirror {this_chat_id} " в чате {other_service_name}\n
ℹ️ Для подключения приватного чата {other_service_name} - см. пункт 3"""
cmd_mirror_no_connect_mutually="""ℹ️ {time} этот чат {this_service_name} подключен к чату {other_service_name} c ID {connected_to_id}, но чат {other_service_name} не подключен в ответ.\n
Для подключения зеркалирования этого чата {this_service_name} в чат {other_service_name}:
1. Добавьте бота {other_service_bot_link} в Ваш чат {other_service_name}
2. Разрешите боту доступ к сообщениям 
3. Введите команду " /mirror {this_chat_id} " в чате {other_service_name}\n
ℹ️ Для подключения приватного чата {other_service_name} - см. пункт 3"""
cmd_mirror="""✅ {time} этот чат {this_service_name} подключен к чату {other_service_name} c ID {connected_to_id}.
ℹ️ Для отключения используйте команду " /mirror off "
ℹ️ {forward_state} пересылка файлов весом до {forward_limit}МБ
ℹ️ Если бот не видит Ваши сообщения - проверьте что у него есть доступ к сообщениям"""
cmd_mirror_arg_uncorrect="""❗ Неправильно указан ID подключаемого чата. 
Для подключения введите /mirror и ID чата {other_service_name}.
Пример: /mirror 123456789"""
cmd_mirror_disconnect='ℹ️ {time} этот чат {this_service_name} отключен от чата {other_service_name}'
