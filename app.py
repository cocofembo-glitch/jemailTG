import os
import hashlib
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
import urllib.parse as urlparse
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = "super_secret_tg_email_key_bof"

# Отримуємо URL бази даних з налаштувань Render
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL variable is missing! Please configure it in Render.")
    
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    conn = psycopg2.connect(url)
    return conn

# Автоматичне створення таблиць у PostgreSQL
def init_db():
    if not DATABASE_URL:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username VARCHAR(50) PRIMARY KEY,
            password VARCHAR(64) NOT NULL,
            email VARCHAR(100),
            registered_at VARCHAR(30),
            blocked BOOLEAN DEFAULT FALSE,
            block_reason TEXT DEFAULT ''
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS guests (
            guest_id VARCHAR(50) PRIMARY KEY,
            created_at VARCHAR(30)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id SERIAL PRIMARY KEY,
            from_user VARCHAR(50) NOT NULL,
            to_user VARCHAR(50) NOT NULL,
            subject VARCHAR(200),
            message TEXT,
            timestamp VARCHAR(10)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS moderation (
            mod_id SERIAL PRIMARY KEY,
            from_user VARCHAR(50) NOT NULL,
            to_user VARCHAR(50) NOT NULL,
            subject VARCHAR(200),
            message TEXT,
            timestamp VARCHAR(10)
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key VARCHAR(50) PRIMARY KEY,
            value BOOLEAN DEFAULT FALSE
        )
    ''')
    
    cur.execute("INSERT INTO system_config (key, value) VALUES ('locked', FALSE) ON CONFLICT (key) DO NOTHING")
    cur.execute("INSERT INTO system_config (key, value) VALUES ('troll_mode', FALSE) ON CONFLICT (key) DO NOTHING")
    
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"Помилка ініціалізації бази даних: {e}")

class JEMailSystem:
    def __init__(self):
        self.admin_email = "crocorembo@gmail.com"
        self.admin_password = "admibof" 
        
    @property
    def system_locked(self):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT value FROM system_config WHERE key = 'locked'")
            res = cur.fetchone()
            cur.close()
            conn.close()
            return res[0] if res else False
        except:
            return False
            
    @system_locked.setter
    def system_locked(self, value):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE system_config SET value = %s WHERE key = 'locked'", (value,))
        conn.commit()
        cur.close()
        conn.close()

    @property
    def troll_mode(self):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT value FROM system_config WHERE key = 'troll_mode'")
            res = cur.fetchone()
            cur.close()
            conn.close()
            return res[0] if res else False
        except:
            return False
            
    @troll_mode.setter
    def troll_mode(self, value):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE system_config SET value = %s WHERE key = 'troll_mode'", (value,))
        conn.commit()
        cur.close()
        conn.close()

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_admin_password(self, password):
        return password == self.admin_password

system = JEMailSystem()

@app.route('/')
def index():
    if 'user' in session:
        display_user = "🤡 Жертва Тролінгу" if (system.troll_mode and not session.get('is_admin')) else session['user']
        return render_template('main.html', user=display_user, is_guest=session.get('is_guest', False), is_admin=session.get('is_admin', False))
    return render_template('auth.html', locked=system.system_locked)

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('.', 'sw.js')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if username == "admin" or username == system.admin_email:
        if system.verify_admin_password(password):
            session['user'] = "admin"
            session['is_guest'] = False
            session['is_admin'] = True
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Невірний пароль адміна!'})

    if system.system_locked:
        return jsonify({'success': False, 'error': 'Зачекайте, будь ласка, йде оновлення системи — технічна перерва.'})

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user:
        if user['blocked']:
            return jsonify({'success': False, 'error': f"Акаунт заблоковано! Причина: {user['block_reason']}"})
        if user['password'] == system.hash_password(password):
            session['user'] = username
            session['is_guest'] = False
            session['is_admin'] = False
            return jsonify({'success': True})
            
    return jsonify({'success': False, 'error': 'Невірний логін або пароль!'})

@app.route('/api/register', methods=['POST'])
def api_register():
    if system.system_locked: return jsonify({'success': False, 'error': 'Система заблокована!'})
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    if username == "admin":
        return jsonify({'success': False, 'error': 'Цей логін уже зайнятий!'})
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE username = %s", (username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': 'Цей логін уже зайнятий!'})
        
    hashed_pw = system.hash_password(password)
    reg_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cur.execute("INSERT INTO users (username, password, email, registered_at) VALUES (%s, %s, %s, %s)",
                (username, hashed_pw, email, reg_time))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/guest_login', methods=['POST'])
def api_guest_login():
    if system.system_locked: return jsonify({'success': False, 'error': 'Система заблокована!'})
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM guests")
    count = cur.fetchone()[0]
    
    guest_id = f"guest_{count + 1}"
    reg_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cur.execute("INSERT INTO guests (guest_id, created_at) VALUES (%s, %s)", (guest_id, reg_time))
    conn.commit()
    cur.close()
    conn.close()
    
    session['user'] = guest_id
    session['is_guest'] = True
    session['is_admin'] = False
    return jsonify({'success': True})

@app.route('/api/logout')
def api_logout():
    session.clear()
    return redirect('/')

@app.route('/api/emails', methods=['GET'])
def get_emails():
    if 'user' not in session: return jsonify([])
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if session.get('is_admin'):
        cur.execute("SELECT id, from_user AS \"from\", to_user AS \"to\", subject, message, timestamp FROM emails ORDER BY id DESC")
    else:
        user = session['user']
        cur.execute("SELECT id, from_user AS \"from\", to_user AS \"to\", subject, message, timestamp FROM emails WHERE to_user = %s OR from_user = %s ORDER BY id DESC", (user, user))
        
    emails_list = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(emails_list)

@app.route('/api/send', methods=['POST'])
def send_email():
    if 'user' not in session: return jsonify({'success': False})
    data = request.json
    to_user = data.get('to')
    subject = data.get('subject')
    msg_text = data.get('message')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    is_valid_recipient = False
    if to_user == "admin" or to_user.startswith('guest_'):
        is_valid_recipient = True
    else:
        cur.execute("SELECT username FROM users WHERE username = %s", (to_user,))
        if cur.fetchone():
            is_valid_recipient = True
            
    if not is_valid_recipient:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': 'Отримувача не знайдено!'})
        
    if system.troll_mode and session.get('is_guest') and len(msg_text) > 10:
         cur.close()
         conn.close()
         return jsonify({'success': False, 'error': '🔊 Режим Троля: Гостям заборонено писати листи довші за 10 символів!'})

    has_link = False
    for link_trigger in ['http://', 'https://', '.com', '.ru', '.ua', 'www.']:
        if link_trigger in msg_text.lower() or link_trigger in subject.lower():
            has_link = True
            break
            
    timestamp = datetime.now().strftime("%H:%M")
            
    if has_link and not session.get('is_admin'):
        cur.execute("INSERT INTO moderation (from_user, to_user, subject, message, timestamp) VALUES (%s, %s, %s, %s, %s)",
                    (session['user'], to_user, f"[🔗 НА ПЕРЕВІРЦІ] {subject}", msg_text, timestamp))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'moderated': True, 'message': '✉️ Вашого листа відправлено адміну на перевірку посилань!'})

    cur.execute("INSERT INTO emails (from_user, to_user, subject, message, timestamp) VALUES (%s, %s, %s, %s, %s)",
                (session['user'], to_user, subject, msg_text, timestamp))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'moderated': False})

@app.route('/api/admin/data', methods=['GET'])
def admin_get_data():
    if not session.get('is_admin'): return jsonify({'success': False}), 403
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT username, email, registered_at, blocked, block_reason FROM users")
    users = {u['username']: dict(u) for u in cur.fetchall()}
    
    cur.execute("SELECT guest_id, created_at FROM guests")
    guests = {g['guest_id']: dict(g) for g in cur.fetchall()}
    
    cur.execute("SELECT mod_id, from_user AS \"from\", to_user AS \"to\", subject, message, timestamp FROM moderation")
    mod_list = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return jsonify({
        'users': users, 'guests': guests, 'system_locked': system.system_locked,
        'moderation_list': mod_list, 'troll_mode': system.troll_mode
    })

@app.route('/api/admin/toggle_system', methods=['POST'])
def admin_toggle_system():
    data = request.json or {}
    password = data.get('password')
    
    if session.get('is_admin') or system.verify_admin_password(password):
        system.system_locked = data.get('lock', False)
        return jsonify({'success': True, 'message': 'Статус системи успішно змінено!'})
    return jsonify({'success': False, 'error': 'Немає доступу / Невірний пароль!'})

@app.route('/api/admin/moderate', methods=['POST'])
def admin_moderate_email():
    if not session.get('is_admin'): return jsonify({'success': False}), 403
    data = request.json
    mod_id = data.get('mod_id')
    action = data.get('action')
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM moderation WHERE mod_id = %s", (mod_id,))
    email_to_mod = cur.fetchone()
    
    if not email_to_mod:
        cur.close()
        conn.close()
        return jsonify({'success': False, 'error': 'Листа не знайдено!'})
        
    if action == 'approve':
        new_subject = email_to_mod['subject'].replace("[🔗 НА ПЕРЕВІРЦІ] ", "[✓ ПЕРЕВІРЕНО] ")
        cur.execute("INSERT INTO emails (from_user, to_user, subject, message, timestamp) VALUES (%s, %s, %s, %s, %s)",
                    (email_to_mod['from_user'], email_to_mod['to_user'], new_subject, email_to_mod['message'], email_to_mod['timestamp']))
        
    cur.execute("DELETE FROM moderation WHERE mod_id = %s", (mod_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': 'Дію виконано!'})

@app.route('/api/admin/troll', methods=['POST'])
def admin_toggle_troll():
    if not session.get('is_admin'): return jsonify({'success': False}), 403
    system.troll_mode = request.json.get('troll', False)
    return jsonify({'success': True, 'troll_mode': system.troll_mode})

@app.route('/api/admin/block_user', methods=['POST'])
def admin_block_user():
    if not session.get('is_admin'): return jsonify({'success': False}), 403
    data = request.json
    target = data.get('username')
    block = data.get('block', True)
    reason = data.get('reason', 'Порушення правил') if block else ''
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET blocked = %s, block_reason = %s WHERE username = %s", (block, reason, target))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Статус юзера {target} змінено!'})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
