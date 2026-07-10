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
        self.mod_file = "moderation.json"  # Файл для посилань на перевірку
        self.admin_email = "crocorembo@gmail.com"
        self.admin_password = "admibof" 
        self.troll_mode = False  # Адмінський прикол
        self.load_data()
    
    def load_data(self):
        self.users = json.load(open(self.users_file, 'r')) if os.path.exists(self.users_file) else {}
        self.emails = json.load(open(self.emails_file, 'r')) if os.path.exists(self.emails_file) else []
        self.guests = json.load(open(self.guests_file, 'r')) if os.path.exists(self.guests_file) else {}
        self.moderation_emails = json.load(open(self.mod_file, 'r')) if os.path.exists(self.mod_file) else []
        
        if os.path.exists(self.lock_file):
            self.system_locked = json.load(open(self.lock_file, 'r')).get('locked', False)
        else:
            self.system_locked = False
    
    def save_data(self):
        json.dump(self.users, open(self.users_file, 'w'), ensure_ascii=False, indent=4)
        json.dump(self.emails, open(self.emails_file, 'w'), ensure_ascii=False, indent=4)
        json.dump(self.guests, open(self.guests_file, 'w'), ensure_ascii=False, indent=4)
        json.dump(self.moderation_emails, open(self.mod_file, 'w'), ensure_ascii=False, indent=4)
        json.dump({'locked': self.system_locked}, open(self.lock_file, 'w'))
    
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

    if username in system.users:
        if system.users[username].get('blocked'):
            return jsonify({'success': False, 'error': f"Акаунт заблоковано! Причина: {system.users[username].get('block_reason')}"})
        if system.users[username]['password'] == system.hash_password(password):
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
    
    if username in system.users or username == "admin":
        return jsonify({'success': False, 'error': 'Цей логін уже зайнятий!'})
        
    system.users[username] = {
        'password': system.hash_password(password), 'email': email, 'registered_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'blocked': False, 'block_reason': ''
    }
    system.save_data()
    return jsonify({'success': True})

@app.route('/api/guest_login', methods=['POST'])
def api_guest_login():
    if system.system_locked: return jsonify({'success': False, 'error': 'Система заблокована!'})
    guest_id = f"guest_{len(system.guests) + 1}"
    system.guests[guest_id] = {'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    session['user'] = guest_id
    session['is_guest'] = True
    session['is_admin'] = False
    system.save_data()
    return jsonify({'success': True})

@app.route('/api/logout')
def api_logout():
    session.clear()
    return redirect('/')

@app.route('/api/emails', methods=['GET'])
def get_emails():
    if 'user' not in session: return jsonify([])
    if session.get('is_admin'): return jsonify(system.emails[::-1])
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
    
    if to_user not in system.users and to_user != "admin" and not to_user.startswith('guest_'):
        return jsonify({'success': False, 'error': 'Отримувача не знайдено!'})
        
    if system.troll_mode and session.get('is_guest') and len(msg_text) > 10:
         return jsonify({'success': False, 'error': '🔊 Режим Троля: Гостям заборонено писати листи довші за 10 символів!'})

    # Перевірка на посилання для ВСІХ КРІМ АДМІНА
    has_link = False
    for link_trigger in ['http://', 'https://', '.com', '.ru', '.ua', 'www.']:
        if link_trigger in msg_text.lower() or link_trigger in subject.lower():
            has_link = True
            break
            
    if has_link and not session.get('is_admin'):
        # Замість відправки — кладемо в модерацію
        mod_id = len(system.moderation_emails) + 1
        pending_email = {
            'mod_id': mod_id, 'from': session['user'], 'to': to_user, 'subject': f"[🔗 НА ПЕРЕВІРЦІ] {subject}",
            'message': msg_text, 'timestamp': datetime.now().strftime("%H:%M")
        }
        system.moderation_emails.append(pending_email)
        system.save_data()
        return jsonify({'success': True, 'moderated': True, 'message': '✉️ Вашого листа відправлено адміну на перевірку посилань!'})

    # Звичайна відправка
    new_email = {
        'id': len(system.emails) + 1, 'from': session['user'], 'to': to_user, 'subject': subject,
        'message': msg_text, 'timestamp': datetime.now().strftime("%H:%M")
    }
    system.emails.append(new_email)
    system.save_data()
    return jsonify({'success': True, 'moderated': False})

# --- АДМІН СЕКЦІЯ ---

@app.route('/api/admin/data', methods=['GET'])
def admin_get_data():
    if not session.get('is_admin'): return jsonify({'success': False}), 403
    return jsonify({
        'users': system.users, 'guests': system.guests, 'system_locked': system.system_locked,
        'moderation_list': system.moderation_emails, 'troll_mode': system.troll_mode
    })

@app.route('/api/admin/toggle_system', methods=['POST'])
def admin_toggle_system():
    data = request.json or {}
    password = data.get('password')
    
    # Можна відкрити або через панель, або з вікна блокування за паролем
    if session.get('is_admin') or system.verify_admin_password(password):
        system.system_locked = data.get('lock', False)
        system.save_data()
        return jsonify({'success': True, 'message': 'Статус системи успішно змінено!'})
    return jsonify({'success': False, 'error': 'Немає доступу / Невірний пароль!'})

@app.route('/api/admin/moderate', methods=['POST'])
def admin_moderate_email():
    if not session.get('is_admin'): return jsonify({'success': False}), 403
    data = request.json
    mod_id = data.get('mod_id')
    action = data.get('action') # 'approve' або 'reject'
    
    email_to_mod = next((e for e in system.moderation_emails if e['mod_id'] == mod_id), None)
    if not email_to_mod: return jsonify({'success': False, 'error': 'Листа не знайдено!'})
    
    if action == 'approve':
        # Переносимо в основну базу листів
        new_email = {
            'id': len(system.emails) + 1, 'from': email_to_mod['from'], 'to': email_to_mod['to'],
            'subject': email_to_mod['subject'].replace("[🔗 НА ПЕРЕВІРЦІ] ", "[✓ ПЕРЕВІРЕНО] "),
            'message': email_to_mod['message'], 'timestamp': email_to_mod['timestamp']
        }
        system.emails.append(new_email)
        
    system.moderation_emails.remove(email_to_mod)
    system.save_data()
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
    if target in system.users:
        system.users[target]['blocked'] = block
        system.users[target]['block_reason'] = data.get('reason', 'Порушення правил') if block else ''
        system.save_data()
        return jsonify({'success': True, 'message': f'Статус юзера {target} змінено!'})
    return jsonify({'success': False, 'error': 'Користувача не знайдено!'})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
