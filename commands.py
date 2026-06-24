import ast, config, db, strings

async def get_strings(this_service):
    if this_service == 'vk': return 'ВКонтакте', 'Телеграм', 'tg', 't.me/'+str(config.tg_bot_tag)
    if this_service == 'tg': return 'Телеграм', 'ВКонтакте', 'vk', 'vk.me/'+str(config.vk_group_tag)

async def if_command(from_service,msg_text,from_chat_id,from_chat_is_private): 
    if not msg_text.startswith('/'): return None
    if msg_text.endswith(f'@{config.tg_bot_tag}'): msg_text = msg_text[:-(len(config.tg_bot_tag)+1)]
    if msg_text.endswith(f'@{config.vk_group_tag}'): msg_text = msg_text[:-(len(config.vk_group_tag)+1)]
    args=msg_text.lower().split(" ")
    with open(__file__, "r") as f: tree = ast.parse(f.read())
    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]
    function = args[0][1:]+'_cmd'
    if function in functions: return await globals()[function](from_service,from_chat_id,args,from_chat_is_private)

async def start_cmd(from_service,from_chat_id,args,from_chat_is_private):
    this_service_name, other_service_name, other_service, other_service_bot_link = await get_strings(from_service)
    if from_chat_is_private: return strings.cmd_start_private_chat.format(time=strings.time_now,this_service_name=this_service_name,other_service_name=other_service_name,other_service_bot_link=other_service_bot_link,this_chat_id=from_chat_id)
    else: return strings.cmd_start_public_chat

async def mirror_cmd(from_service,from_chat_id,args,from_chat_is_private):
    this_service_name, other_service_name, other_service, other_service_bot_link = await get_strings(from_service)
    connected_to_id = await db.get_connected_chat(from_service,from_chat_id)
    if config.attachments_forward: forward_state=strings.forward_on
    if not config.attachments_forward: forward_state=strings.forward_off
    forward_limit=config.attachments_max_size_mb
    
    if len(args) == 1 : # без аргументов - просмотр статуса
        if not connected_to_id: 
            return strings.cmd_mirror_no_connect.format(time=strings.time_now,this_service_name=this_service_name,other_service_name=other_service_name,other_service_bot_link=other_service_bot_link,this_chat_id=from_chat_id)
        if await db.get_connected_chat(other_service,connected_to_id) != from_chat_id: 
            return strings.cmd_mirror_no_connect_mutually.format(time=strings.time_now,this_service_name=this_service_name,other_service_name=other_service_name,other_service_bot_link=other_service_bot_link,this_chat_id=from_chat_id,connected_to_id=connected_to_id)
        return strings.cmd_mirror.format(forward_state=forward_state,forward_limit=forward_limit,time=strings.time_now,this_service_name=this_service_name,other_service_name=other_service_name,connected_to_id=connected_to_id)
    
    # с аргументами - настройка привязки
    if len(args) != 2 : return strings.cmd_mirror_arg_uncorrect.format(other_service_name=other_service_name)

    if args[1]=='off':
        await db.disconnect_chat(from_service,from_chat_id)
        return strings.cmd_mirror_disconnect.format(time=strings.time_current,other_service_name=other_service_name,this_service_name=this_service_name)
    
    if args[1].startswith('-'): #обход для бесед вк
        if not args[1][1:].isdigit(): return strings.cmd_mirror_arg_uncorrect.format(other_service_name=other_service_name)
    elif not args[1].isdigit(): return strings.cmd_mirror_arg_uncorrect.format(other_service_name=other_service_name)
    if config.id_len[0] > len(args[1]) or len(args[1])  > config.id_len[1]: return strings.cmd_mirror_arg_uncorrect.format(other_service_name=other_service_name)

    await db.connect_chats(from_service,from_chat_id,args[1]) # привязка 
    if await db.get_connected_chat(other_service,int(args[1])) != from_chat_id: 
        return strings.cmd_mirror_no_connect_mutually.format(time=strings.time_current,this_service_name=this_service_name,other_service_name=other_service_name,other_service_bot_link=other_service_bot_link,this_chat_id=from_chat_id,connected_to_id=args[1])
    return strings.cmd_mirror.format(forward_state=forward_state,forward_limit=forward_limit,time=strings.time_current,this_service_name=this_service_name,other_service_name=other_service_name,other_service_bot_link=other_service_bot_link,this_chat_id=from_chat_id,connected_to_id=args[1])
