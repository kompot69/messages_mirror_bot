import ast
import config
import db

msg_nick_prefix='👤'
msg_reply_prefix='↪' # ↪ ➥ ⮩ ⤥ ⤷ ⮎ ⮱
no_connected_chat='ℹ️ Нет подключенного чата. Напишите /start'
connected_chat_no_connect='ℹ️ Подключенный чат не подключен в ответ. Напишите /mirror'
unknown_attachment='[неизвестное вложение]'

def get_strings(this_service):
    if this_service == 'vk': return 'ВКонтакте', 'Телеграм', 'tg', 't.me/'+str(config.bot_tag_tg)
    if this_service == 'tg': return 'Телеграм', 'ВКонтакте', 'vk', 'vk.me/'+str(config.group_tag_vk)

def command(from_service,msg_text,from_chat_id): 
    if not msg_text.startswith('/'): return None
    if msg_text.endswith('@messages_mirror_bot'): msg_text = msg_text[:-20]
    args=msg_text.lower().split(" ")
    with open(__file__, "r") as f: tree = ast.parse(f.read())
    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    function = args[0][1:]+'_cmd'
    if function in functions: return globals()[function](from_service,from_chat_id,args)

def start_cmd(from_service,chat_id,args):
    this_service_name, other_service_name, other_service, other_service_bot_link = get_strings(from_service)
    return f'''Для подключения зеркалирования этого чата {this_service_name} в чат {other_service_name}:
1. Добавьте бота {other_service_bot_link} в Ваш чат {other_service_name}
2. Разрешите боту доступ к сообщениям
3. Введите команду " /mirror {chat_id} " в чате {other_service_name}
'''

def mirror_cmd(from_service,chat_id,args):
    this_service_name, other_service_name, other_service, other_service_bot_link = get_strings(from_service)
    
    connected_to_id = db.get_connected_chat(from_service,chat_id)
    
    if len(args) == 1 : # команда без аргументов - просмотр статуса
        if not connected_to_id: return f"ℹ️ Сейчас этот чат {this_service_name} не подключен к чату {other_service_name}"
        if db.get_connected_chat(other_service,connected_to_id) != chat_id: 
            return f"ℹ️ Сейчас этот чат {this_service_name} подключен к чату {other_service_name} c ID {connected_to_id}.\n❗ Чат {this_service_name} c ID {connected_to_id} не подключен к этому чату. Для подключения введите в чате {this_service_name} команду \" /mirror {chat_id} \""
        return f"✅ Сейчас этот чат {this_service_name} подключен к чату {other_service_name} c ID {connected_to_id}.\nℹ️ Для отключения используйте команду \" /mirror off \""
    
    # привязка - проверка аргументов 
    if len(args) != 2 : return "❗ Неверное количество аргументов!"
    if args[1]=='off': # отключение чата
        db.disconnect_chat(from_service,chat_id)
        return f'ℹ️ Теперь этот чат {this_service_name} отключен от чата {other_service_name}'
    if args[1].startswith('-'): #обход для бесед вк
        if not args[1][1:].isdigit(): return f'❗ Недопустимое значение ID " {args[1]} "'
    elif not args[1].isdigit(): return f'❗ Недопустимое значение ID " {args[1]} "'
    if config.min_id_len > len(args[1]) or len(args[1])  > config.max_id_len: return f'❗ Неверная длина ID " {args[1]} "'

    db.connect_chats(from_service,chat_id,args[1]) # привязка 
    if db.get_connected_chat(other_service,int(args[1])) != chat_id: 
        return f"ℹ️ Теперь этот чат {this_service_name} подключен к чату {other_service_name} c ID {args[1]}.\nОсталось подключить чат {other_service_name} к этому чату. Для подключения введите в чате {other_service_name} команду \" /mirror {chat_id} \""
    return f'✅ Теперь сообщения из этого чата {this_service_name} будут пересылаться в чат {other_service_name} с ID {args[1]} и наоборот!'