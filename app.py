import os
import hashlib
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect

app = Flask(__name__)
app.secret_key = "super_secret_tg_email_key_bof"

class JEMailSystem:
    def __init__(self):
        self.users_file = "users.json"
        self.emails_file = "emails.json"
        self.lock_file = "system_lock.json"
        self.guests_file = "guests.json"
        self.admin_email = "crocorembo@gmail.com"
        self.admin_password = "admibof" 
        self.load_data()
    
    def load_data(self):
        self.users = json.load(open(self.users_file, 'r')) if os.path.exists(self.users_file) else {}
        self.emails = json.load(open(self.emails_file, 'r')) if os.path.exists(self.emails_file) else []
        self.guests = json.load(open(self.guests_file, 'r')) if os.path.exists(self.guests_file) else {}
        
        if os.path.exists(self.lock_file):
            self.system_locked = json.load(open(self.lock_file, 'r')).get('locked', False)
        else:
            self.system_locked = False
    
    def save_data(self):
        json.dump(self.users, open(self.users_file, 'w'), ensure_ascii=False, indent=4)
        json.dump(self.emails, open(self.emails_file, 'w'), ensure_ascii=False, indent=4)
        json.dump(self.guests, open(self.guests_file, 'w'), ensure_ascii=False, indent=4)
        json.dump({'locked': self.system_locked}, open(self.lock_file, 'w'))
    
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_admin_password(self, password):
        return password == self.admin_password
    
    def validate_password(self, password):
        if len(password) < 9:
            return False, "❌ Пароль має бути не менше 9 символів!"
        forbidden_sequences = ['123', '234', '345', '456', '567', '678', '789', '000', '111', '222']
        for seq in forbidden_sequences:
            if seq in password:
                return False, f"❌ Заборонена послідовність '{seq}' у паролі!"
        forbidden_chars = ['!', '#', '.', '?']
        for char in forbidden_chars:
            if char in password:
                return False, f"❌ Заборонений символ '{char}' у паролі!"
        return True, "✅ Пароль підходить"

    def create_guest_account(self):
        guest_id = f"guest_{len(self.guests) + 1}"
        self.guests[guest_id] = {
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'expires_at': (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            'messages_sent': 0,
            'messages_received': 0
        }
        self.save_data()
        return guest_id

    def check_guest_expired(self, guest_id):
        if guest_id not in self.guests:
            return True
        expires_at = datetime.strptime(self.guests[guest_id]['expires_at'], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires_at:
            del self.guests[guest_id]
            self.save_data()
            return True
        return False

system = JEMailSystem()

@app.route('/')
def index():
    if 'user' in session:
        if session.get('is_guest') and system.check_guest_expired(session['user']):
            session.clear()
            return redirect('/')
        return render_template('main.html', user=session['user'], is_guest=session.get('is_guest', False), is_admin=session.get('is_admin', False))
    return render_template('auth.html', locked=system.system_locked)

@app.route('/api/login', methods=['POST'])
def api_login():
    if system.system_locked:
        return jsonify({'success': False, 'error': 'Система заблокована!'})
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    # 1. ПЕРЕВІРКА НА АДМІНА (Логін може бути і "admin", і твоя пошта "crocorembo@gmail.com")
    if username == "admin" or username == system.admin_email:
        if system.verify_admin_password(password):
            session['user'] = "admin"
            session['is_guest'] = False
            session['is_admin'] = True
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Невірний пароль адміна!'})

    # 2. ПЕРЕВІРКА ДЛЯ ОБИЧНОГО ЧОЛОВІКА (Звичайні користувачі з бази)
    if username in system.users:
        if system.users[username].get('blocked'):
            return jsonify({'success': False, 'error': f"Акаунт заблоковано! Причина: {system.users[username].get('block_reason')}"})
        if system.users[username]['password'] == system.hash_password(password):
            session['user'] = username
            session['is_guest'] = False
            # Про всяк випадок, якщо звичайний юзер має адмінську пошту
            session['is_admin'] = (system.users[username].get('email') == system.admin_email)
            return jsonify({'success': True})
            
    return jsonify({'success': False, 'error': 'Невірний логін або пароль!'})

@app.route('/api/register', methods=['POST'])
def api_register():
    if system.system_locked:
        return jsonify({'success': False, 'error': 'Система заблокована!'})
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    if username in system.users or username.startswith('guest_') or username == "admin":
        return jsonify({'success': False, 'error': 'Цей логін уже зайнятий!'})
    
    is_valid, msg = system.validate_password(password)
    if not is_valid:
        return jsonify({'success': False, 'error': msg})
        
    system.users[username] = {
        'password': system.hash_password(password),
        'email': email,
        'registered_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'blocked': False
    }
    system.emails.append({
        'id': len(system.emails) + 1,
        'from': 'admin@jemail.com',
        'to': username,
        'subject': 'Ласкаво просимо до JEmail! 🎉',
        'message': f'Привіт, {username}!\n\nТвій акаунт успішно створено.\nПароль закритий та надійно зашифрований.',
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'read': False
    })
    system.save_data()
    return jsonify({'success': True})

@app.route('/api/guest_login', methods=['POST'])
def api_guest_login():
    if system.system_locked:
        return jsonify({'success': False, 'error': 'Система заблокована!'})
    guest_id = system.create_guest_account()
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
    user = session['user']
    user_emails = [e for e in system.emails if e['to'] == user or e['from'] == user]
    return jsonify(user_emails[::-1])

@app.route('/api/send', methods=['POST'])
def send_email():
    if 'user' not in session: return jsonify({'success': False})
    data = request.json
    to_user = data.get('to')
    subject = data.get('subject')
    msg_text = data.get('message')
    
    if to_user not in system.users and not to_user.startswith('guest_') and to_user != "admin":
        return jsonify({'success': False, 'error': 'Отримувача не знайдено!'})
        
    if session.get('is_guest'):
        for forbidden in ['http://', 'https://', '.com', '.ru', '.ua']:
            if forbidden in msg_text.lower() or forbidden in subject.lower():
                return jsonify({'success': False, 'error': 'Гостям заборонено надсилати посилання!'})
        subject = f"[ГОСТЬ] {subject}"
        msg_text += f"\n\n---\nНадіслано з гостьового акаунту: {session['user']}"
        system.guests[session['user']]['messages_sent'] += 1
        
    new_email = {
        'id': len(system.emails) + 1,
        'from': session['user'],
        'to': to_user,
        'subject': subject,
        'message': msg_text,
        'timestamp': datetime.now().strftime("%H:%M"),
        'read': False,
        'is_guest': session.get('is_guest', False)
    }
    system.emails.append(new_email)
    system.save_data()
    return jsonify({'success': True})

@app.route('/api/admin/unlock', methods=['POST'])
def admin_unlock():
    data = request.json
    if system.verify_admin_password(data.get('password')):
        system.system_locked = False
        system.save_data()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Невірний пароль адміна!'})

if __name__ == '__main__':
    # Налаштування порту для Render, щоб він знову не падав
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
