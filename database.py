import sqlite3

DB_PATH = "users.db"

def init_db():
    """Initialize database tables for users and chat history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone_number TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lesson_id INTEGER,
            user_message TEXT,
            assistant_reply TEXT,
            has_screenshot BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            mimetype TEXT,
            data BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (message_id) REFERENCES chat_messages(id)
        )
    ''')

    conn.commit()
    conn.close()

def create_user(first_name, last_name, email, phone_number, password_hash):
    """Create a user and return their new id. Raises sqlite3.IntegrityError if the email is taken."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (first_name, last_name, email, phone_number, password_hash)
            VALUES (?, ?, ?, ?, ?)
        ''', (first_name, last_name, email, phone_number, password_hash))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def get_user_by_email(email):
    """Get user by email."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_id(user_id):
    """Get user by ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def save_chat_message(user_id, lesson_id, user_message, assistant_reply, screenshot_data=None, screenshot_mimetype=None):
    """Save a chat message and optional screenshot to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    has_screenshot = 1 if screenshot_data else 0

    cursor.execute('''
        INSERT INTO chat_messages (user_id, lesson_id, user_message, assistant_reply, has_screenshot)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, lesson_id, user_message, assistant_reply, has_screenshot))

    message_id = cursor.lastrowid

    if screenshot_data:
        cursor.execute('''
            INSERT INTO chat_uploads (message_id, mimetype, data)
            VALUES (?, ?, ?)
        ''', (message_id, screenshot_mimetype, screenshot_data))

    conn.commit()
    conn.close()

    return message_id

def get_chat_history(user_id, lesson_id, limit=50):
    """Get the most recent chat messages for a user on one lesson, oldest first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM chat_messages
        WHERE user_id = ? AND lesson_id = ?
        ORDER BY id DESC
        LIMIT ?
    ''', (user_id, lesson_id, limit))
    messages = cursor.fetchall()
    conn.close()
    return list(reversed(messages))

def get_upload_for_message(message_id, user_id):
    """Get the screenshot upload for a message, but only if the message belongs to user_id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chat_uploads.mimetype, chat_uploads.data
        FROM chat_uploads
        JOIN chat_messages ON chat_messages.id = chat_uploads.message_id
        WHERE chat_uploads.message_id = ? AND chat_messages.user_id = ?
    ''', (message_id, user_id))
    upload = cursor.fetchone()
    conn.close()
    return upload
