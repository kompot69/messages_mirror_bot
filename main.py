import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import threading
import config, commands, db
import time

VK_TOKEN = config.token_vk_user

# === Очередь обмена сообщениями ===
message_bus = asyncio.Queue()
async def msg_catcher(): # ловим cooбщения
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    while True:
        service_to, msg, to_id = await message_bus.get()
        if service_to == "tg": 
            try: await tg_bot.send_message(to_id, msg) 
            except Exception as e: print(f'[E] send to {service_to} {to_id}: {e}')
        if service_to == "vk": 
            try: vk.messages.send( peer_id=to_id, message=f"{msg}", random_id=0 )
            except Exception as e: print(f'[E] send to {service_to} {to_id}: {e}')

# === Обмен сообщениями ===
async def msg_navigator(from_service,msg_obj):

    #print(str(msg_obj))
    try:
        if from_service == 'tg':
            to_service = 'vk'
            from_chat_id = int(msg_obj.chat.id)
            from_msg_text = msg_obj.text or ''
            from_chat_is_private = msg_obj.chat.type == 'private'
            from_user_nick = f"{msg_obj.from_user.first_name} {msg_obj.from_user.last_name}" if msg_obj.from_user.last_name else msg_obj.from_user.first_name
            reply_to_msg_text = getattr(msg_obj.reply_to_message, 'text', None)
            if msg_obj.forward_from or getattr(msg_obj, 'forward_sender_name', None) or getattr(msg_obj, 'forward_from_chat', None):
                if getattr(msg_obj, 'forward_sender_name', None): from_user_nick += f' [ переслано от {msg_obj.forward_sender_name} ]'
                elif getattr(msg_obj.forward_from, 'first_name', None) and getattr(msg_obj.forward_from, 'last_name', None): from_user_nick += f' [ переслано от {msg_obj.forward_from.first_name} {msg_obj.forward_from.last_name} ]'
                elif getattr(msg_obj.forward_from, 'first_name', None): from_user_nick += f' [ переслано от {msg_obj.forward_from.first_name} ]'
                elif getattr(msg_obj, 'forward_from_chat', None): from_user_nick += f' [ переслано из {msg_obj.forward_from_chat.title} ]'
                else: from_user_nick += ' [ переслано ] '

        elif from_service == 'vk':
            to_service = 'tg'
            from_chat_id = int(msg_obj.get('peer_id', 0))
            from_msg_text = msg_obj.get('text', '')
            from_chat_is_private = True         # хз как узнать
            from_user_nick = 'id'+str(from_chat_id)  # хз как узнать
            reply_to_msg_text = msg_obj.get('reply_message', {}).get('text') # не видит ответ на пересланые сообщения 
            for fwd_msg in msg_obj.get('fwd_messages', []):
                text = fwd_msg.get('text') if fwd_msg.get('text') else '[unknown_message_type]'
                from_msg_text += f"\n [ переслано от id {fwd_msg.get('from_id')} ] \n {text}"

        print(f'msg from {from_service} {from_chat_id}: {from_msg_text}')

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        
    if not from_msg_text: from_msg_text = commands.unknown_attachment #защита от хуйни 

    # если команда - возврат говна
    command_answer = commands.command(from_service,from_msg_text,from_chat_id)
    if command_answer: return await message_bus.put((from_service, command_answer, from_chat_id))

    else: # раскид если не команда
        from_msg_text = f'{commands.msg_nick_prefix} {from_user_nick}\n{from_msg_text}'# добавление ника
        if len(from_msg_text)>config.message_max_len: from_msg_text=from_msg_text[:config.message_max_len]

        # подкл. ли этот чат к 2 чату
        connected_to_id = db.get_connected_chat(from_service,from_chat_id)
        # если не подкл. вообще
        if not connected_to_id: 
            if from_chat_is_private: await message_bus.put((from_service, commands.no_connected_chat, from_chat_id))
            return
        # если 2 чат подкл. не к этому чату 
        if db.get_connected_chat(to_service,connected_to_id) != from_chat_id:
            if from_chat_is_private: await message_bus.put((from_service, commands.connected_chat_no_connect, from_chat_id))
            return
        
        # добавление реплаев
        if reply_to_msg_text:
            if reply_to_msg_text.startswith(commands.msg_reply_prefix): reply_to_msg_text=reply_to_msg_text[reply_to_msg_text.find('\n')+1:] # обрезка реплаев в реплаях
            if reply_to_msg_text.startswith(commands.msg_nick_prefix): reply_to_msg_text=reply_to_msg_text[reply_to_msg_text.find('\n')+1:] # обрезка ников в реплаях
            if len(reply_to_msg_text)>config.message_reply_max_len: reply_to_msg_text = reply_to_msg_text[:config.message_reply_max_len]+'...' # обрезка длины
            from_msg_text = f'{commands.msg_reply_prefix} {reply_to_msg_text}\n{from_msg_text}'
        print(f'└ send to {to_service} {connected_to_id}')
        await message_bus.put((to_service, from_msg_text, connected_to_id)) 

# === Telegram бот (aiogram 3.x) ===
tg_bot = Bot(token=config.token_tg)
dp = Dispatcher(storage=MemoryStorage())
@dp.message()
async def handle_telegram_message(message: Message):
    await msg_navigator('tg',message)

# === VK бот (vk_api) в отдельном потоке ===
def run_vk_bot_polling(loop):
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    last_message_ids = {}
    while True:
        try: 
            response = vk.messages.getConversations(offset=0, count=20)
            for item in response['items']:
                message = item['last_message']
                if message['from_id'] == -config.group_id_vk: continue # если сообщение от группы
                if last_message_ids.get(message['peer_id']) == message['id']: continue # если сообщение уже видели 
                # иначе — запоминаем и обрабатываем
                last_message_ids[message['peer_id']] = message['id']
                asyncio.run_coroutine_threadsafe( msg_navigator('vk', message), loop)
            time.sleep(0.1)
        except Exception as e:
            print(f"[E] Eбал ВК по причине {e}")
            time.sleep(3)

# === Основной запуск ===
async def main():
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_vk_bot_polling, args=(loop,), daemon=True).start() 
    asyncio.create_task(msg_catcher())
    db.create_db()
    print("[i] bot started")
    await dp.start_polling(tg_bot)
    print("[i] bot stopped")

if __name__ == "__main__":
    asyncio.run(main())
