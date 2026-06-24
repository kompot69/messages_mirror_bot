import ast, config, db, strings

async def get_strings(service0):
    if service0 == 'vk': return 'ВКонтакте', 'Телеграм', 'tg', 't.me/'+str(config.tg_bot_tag)
    if service0 == 'tg': return 'Телеграм', 'ВКонтакте', 'vk', 'vk.me/'+str(config.vk_group_tag)

async def if_command(service0, msg_text, service0_chat_id, service0_chat_is_private): 
    if not msg_text.startswith('/'): return None
    if msg_text.endswith(f'@{config.tg_bot_tag}'): msg_text = msg_text[:-(len(config.tg_bot_tag)+1)]
    if msg_text.endswith(f'@{config.vk_group_tag}'): msg_text = msg_text[:-(len(config.vk_group_tag)+1)]
    args=msg_text.lower().split(" ")
    with open(__file__, "r") as f: tree = ast.parse(f.read())
    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]
    function = args[0][1:]+'_cmd'
    if function in functions: return await globals()[function](service0, service0_chat_id, args, service0_chat_is_private)

async def start_cmd(service0, service0_chat_id, args, service0_chat_is_private):
    service0_name, service1_name, service1, service1_bot_link = await get_strings(service0)
    if service0_chat_is_private: return strings.cmd_start_private_chat.format(time=strings.time_now,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id)
    else: return strings.cmd_start_public_chat

async def mirror_cmd(service0,service0_chat_id,args,service0_chat_is_private):
    service0_name, service1_name, service1, service1_bot_link = await get_strings(service0)
    service1_chat_id = await db.get_connected_chat(service0, service0_chat_id)
    forward_state = strings.forward_on if config.attachments_forward else strings.forward_off
    forward_limit = config.attachments_max_size_mb
    if (service0 == 'vk' and service0_chat_id in config.vk_admins_ids) or (service0 == 'tg' and service0_chat_id in config.tg_admins_ids):
        admin_text = f'Версия: {config.bot_version}\nМакс.длина сообщения: {config.message_max_len}\nЗаблокировано чатов:'

    if len(args) == 1 : # без аргументов - просмотр статуса
        if not service1_chat_id: 
            return strings.cmd_mirror_no_connect.format(time=strings.time_now,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id)
        if await db.get_connected_chat(service1,service1_chat_id) != service0_chat_id: 
            return strings.cmd_mirror_no_connect_mutually.format(time=strings.time_now,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id,service1_chat_id=service1_chat_id)
        return strings.cmd_mirror.format(forward_state=forward_state,forward_limit=forward_limit,time=strings.time_now,service0_name=service0_name,service1_name=service1_name,service1_chat_id=service1_chat_id)
    
    # с аргументами - настройка привязки
    if len(args) != 2 : return strings.cmd_mirror_arg_uncorrect.format(service1_name=service1_name)

    if args[1]=='off':
        await db.disconnect_chat(service0,service0_chat_id)
        return strings.cmd_mirror_disconnect.format(time=strings.time_current,service1_name=service1_name,service0_name=service0_name)
    
    if 'tread' in args[1]: chat_id, tread_id = args[1].split('tread')
    else: chat_id = args[1]
    
    if chat_id.startswith('-'): #обход для бесед вк
        if not chat_id[1:].isdigit(): return strings.cmd_mirror_arg_uncorrect.format(service1_name=service1_name)
    elif not chat_id.isdigit(): return strings.cmd_mirror_arg_uncorrect.format(service1_name=service1_name)
    if config.id_len[0] > len(chat_id) or len(chat_id) > config.id_len[1]: return strings.cmd_mirror_arg_uncorrect.format(service1_name=service1_name)

    await db.connect_chats(service0,service0_chat_id,args[1]) # привязка 
    if await db.get_connected_chat(service1,args[1]) != service0_chat_id: 
        return strings.cmd_mirror_no_connect_mutually.format(time=strings.time_current,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id,service1_chat_id=args[1])
    return strings.cmd_mirror.format(forward_state=forward_state,forward_limit=forward_limit,time=strings.time_current,service0_name=service0_name,service1_name=service1_name,service1_bot_link=service1_bot_link,service0_chat_id=service0_chat_id,service1_chat_id=args[1])
