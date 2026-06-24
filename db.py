import aiosqlite, logging, config

loggerDB = logging.getLogger(__name__)
loggerDB.setLevel(logging.INFO)
formatterDB = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
handlerDB = logging.StreamHandler()
handlerDB.setFormatter(formatterDB)
loggerDB.addHandler(handlerDB)

async def initialization():
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS chats_tg (
            tg_id TEXT PRIMARY KEY,
            connected_to_vk_id TEXT
            )''') #last_msg_from_id INTEGER,
        await db.execute('''CREATE TABLE IF NOT EXISTS chats_vk (
            vk_id TEXT PRIMARY KEY,
            connected_to_tg_id TEXT
            )''') #last_msg_from_id INTEGER,
        await db.commit()

async def get_table_and_column_name(from_service):
    if from_service == 'vk': return 'chats_vk', 'vk_id', 'connected_to_tg_id'#, 'last_msg_from_id'
    elif from_service == 'tg': return 'chats_tg', 'tg_id', 'connected_to_vk_id'#, 'last_msg_from_id'

async def get_connected_chat(from_service, from_chat_id):
    table, id_col, connected_col = await get_table_and_column_name(from_service)
    sql = f"""SELECT * FROM {table} WHERE {id_col} = ?"""
    async with aiosqlite.connect(config.database_path) as db:
        async with db.execute(sql, (from_chat_id,)) as cursor:
            result = await cursor.fetchone()
            loggerDB.debug(f'{from_service} {from_chat_id} connected to {result[1]}')
            if result: result=result[1]
            return result
    
async def connect_chats(service_to_connect, chat_to_connect_id, chat_to_be_connected_id):
    table, id_col, connected_col = await get_table_and_column_name(service_to_connect)
    sql = f"""INSERT INTO {table} ({id_col}, {connected_col}) VALUES (?, ?) ON CONFLICT({id_col}) DO UPDATE SET {connected_col} = excluded.{connected_col}"""
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute(sql, (chat_to_connect_id, chat_to_be_connected_id))
        await db.commit()
        loggerDB.info(f'{service_to_connect} {chat_to_connect_id} was connected to {chat_to_be_connected_id}')

async def disconnect_chat(from_service, from_chat_id):
    table, id_col, connected_col = await get_table_and_column_name(from_service)
    sql = f"""DELETE FROM {table} WHERE {id_col} = ?"""
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute(sql, (from_chat_id,))
        loggerDB.debug(sql)
        loggerDB.info(f'{from_service} {from_chat_id} was disconnected')
        await db.commit()