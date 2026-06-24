import aiosqlite, sqlite3, config
from config import logger

def get_columns_names(service):
    other_services = [key for key in config.services if key != service]
    other_services_columns = []
    for other_service in other_services:
        other_services_columns.append(f'connected_to_{other_service}_id')
    return [f'chats_{service}', f'{service}_id', other_services_columns]

async def initialization():
    all_services = [key for key in config.services]
    async with aiosqlite.connect(config.database_path) as db:
        async with db.execute("""SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';""") as cursor:
            rows = await cursor.fetchall()
            current_tables = [row[0] for row in rows]
        for service in all_services:
            if f'chats_{service}' not in current_tables and len(current_tables)>0: logger.warning(f'new service detected: {service}. you may to recreate DB!')
            other_services_columns = get_columns_names(service)[2]
            sql = f'CREATE TABLE IF NOT EXISTS chats_{service} ({service}_id TEXT PRIMARY KEY, settings TEXT'
            for column in other_services_columns: sql += f', {column}'
            sql += ')'
            await db.execute(sql) 
        # sql = f'CREATE TABLE IF NOT EXISTS attachments_cache ({service}_attachment_id TEXT, {service}_attachment_id TEXT,
        await db.commit()

async def get_chat(service, service_chat_id):
    sql = f"""SELECT * FROM chats_{service} WHERE {service}_id = ?"""
    async with aiosqlite.connect(config.database_path) as db:
        async with db.execute(f"PRAGMA table_info(chats_{service});") as cursor:
            rows = await cursor.fetchall()
            table_columns = [row[1] for row in rows]
        async with db.execute(sql, (service_chat_id,)) as cursor:
            columns_content = await cursor.fetchone()
        connected_services = {}
        if columns_content is None: 
            columns_content = []
            for i in table_columns: columns_content.append(None)
        for field, value in zip(table_columns, columns_content):
            if field == 'settings': chat_settings = value
            elif field.startswith('connected_to_') and field.endswith('_id'):
                connected_service = field[len('connected_to_'):-len('_id')]
                connected_services[connected_service] = value
        if service_chat_id is not None: logger.debug(f'{service} {service_chat_id} connected_services: {connected_services}, setings: {chat_settings}')
        return chat_settings, connected_services
    
async def connect_chats(service0, service0_chat_id, service1, service1_chat_id):
    columns = get_columns_names(service0)
    sql = f"""INSERT INTO {columns[0]} ({columns[1]}, connected_to_{service1}_id) VALUES (?, ?) ON CONFLICT({columns[1]}) DO UPDATE SET connected_to_{service1}_id = excluded.connected_to_{service1}_id"""
    try:
        async with aiosqlite.connect(config.database_path) as db:
            await db.execute(sql, (service0_chat_id, service1_chat_id))
            await db.commit()
            sql = f"""SELECT connected_to_{service0}_id FROM chats_{service1} WHERE {service1}_id = ?"""
            async with db.execute(sql, (service1_chat_id,)) as cursor:
                connected_chat_connected_to_id = await cursor.fetchone()
                if connected_chat_connected_to_id and service0_chat_id in connected_chat_connected_to_id:
                    logger.debug(f'chat {service0} {service0_chat_id} was mutually connected to {service1} chat {service1_chat_id}')
                    return True
                else: 
                    logger.debug(f'chat {service0} {service0_chat_id} was connected to {service1} chat {service1_chat_id} (not mutually)')
                    return False
    except sqlite3.OperationalError: 
        logger.debug(f'chat {service0} {service0_chat_id} was try to connect to service {service1}, but service {service1} was not exist')
        return None
        
async def disconnect_chat(service0, service0_chat_id):
    columns = get_columns_names(service0)
    sql = f"""DELETE FROM {columns[0]} WHERE {columns[1]} = ?"""
    async with aiosqlite.connect(config.database_path) as db:
        await db.execute(sql, (service0_chat_id,))
        logger.debug(f'{service0} {service0_chat_id} was disconnected')
        await db.commit()