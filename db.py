import sqlite3
import config

def get_strings(from_service):
    if from_service == 'vk': return 'chats_vk', 'vk_id', 'connected_to_tg_id'
    else: return 'chats_tg', 'tg_id', 'connected_to_vk_id'

def get_connected_chat(from_service, from_chat_id):
    conn = sqlite3.connect(config.db_name)
    cursor = conn.cursor()
    table, id_col, connected_col = get_strings(from_service)
    sql = f"""SELECT {connected_col} FROM {table} WHERE {id_col} = ?"""
    cursor.execute(sql, (int(from_chat_id),))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None
    
def connect_chats(service_to_connect, chat_to_connect_id, chat_to_be_connected_id):
    conn = sqlite3.connect(config.db_name)
    cursor = conn.cursor()
    table, id_col, connected_col = get_strings(service_to_connect)
    sql = f"""INSERT INTO {table} ({id_col}, {connected_col}) VALUES (?, ?) ON CONFLICT({id_col}) DO UPDATE SET {connected_col} = excluded.{connected_col}"""
    cursor.execute(sql, (int(chat_to_connect_id), int(chat_to_be_connected_id)))
    conn.commit()
    conn.close()
    print(f'[i] DB: {service_to_connect} {chat_to_connect_id} chat was connected to {chat_to_be_connected_id}')

def disconnect_chat(from_service, from_chat_id):
    conn = sqlite3.connect(config.db_name)
    cursor = conn.cursor()
    table, id_col, connected_col = get_strings(from_service)
    sql = f"""DELETE FROM {table} WHERE {id_col} = ?"""
    print(sql)
    cursor.execute(sql, (from_chat_id,))
    conn.close()
    print(f'[i] DB: {from_service} {from_chat_id} chat was disconnected')

def create_db():
    conn = sqlite3.connect(config.db_name)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS chats_tg (
        tg_id INTEGER PRIMARY KEY,
        connected_to_vk_id INTEGER
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS chats_vk (
        vk_id INTEGER PRIMARY KEY,
        connected_to_tg_id INTEGER
    )""")
    conn.commit()
    conn.close()