from flask import Flask, request, render_template, jsonify
from config import FLASK_SECRET_KEY, TELEGRAM_BOT_TOKEN
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import secrets
from sqlalchemy.exc import IntegrityError
from flask_migrate import Migrate
from sqlalchemy import or_, desc

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sabapp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(32), unique=True, nullable=False)
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    photo_url = db.Column(db.String(256))
    balance = db.Column(db.Float, default=0)
    card_bg = db.Column(db.String(256))
    ref_code = db.Column(db.String(16), unique=True)
    ref_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_mining_at = db.Column(db.DateTime)
    mining_locked_until = db.Column(db.DateTime)
    pending_claim = db.Column(db.Float, default=0)
    referrals = db.relationship('Referral', backref='user', lazy=True, foreign_keys='Referral.user_id')

class Referral(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    referred_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProfileCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    image_url = db.Column(db.String(256), nullable=False)
    price = db.Column(db.Integer, nullable=False)

class UserProfileCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey('profile_card.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'card_id', name='uix_user_card'),)

class Upgrade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(32), nullable=False)  # Например: 'speed', 'income', 'multiplier'
    level = db.Column(db.Integer, default=0, nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'type', name='uix_user_upgrade'),)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(8), nullable=False)  # 'in' или 'out'

# --- Конфиг апгрейдов (можно вынести в config.py) ---
UPGRADE_TYPES = [
    {
        'type': 'speed',
        'title': 'Скорость майнинга',
        'desc': 'Уменьшает время майнинга',
        'base_price': 50,
        'price_mult': 1.8,
        'effect': lambda lvl: max(0.3, 1.0 - 0.05 * lvl),  # 5% быстрее за уровень, минимум 30% от базового времени
        'unit': 'x',
    },
    {
        'type': 'income',
        'title': 'Доход за цикл',
        'desc': 'Увеличивает SAB за майнинг',
        'base_price': 100,
        'price_mult': 2.2,
        'effect': lambda lvl: 1.0 + 0.08 * lvl,  # +8% за уровень
        'unit': 'x',
    },
    {
        'type': 'multiplier',
        'title': 'Мультипликатор',
        'desc': 'Умножает доход',
        'base_price': 500,
        'price_mult': 2.5,
        'effect': lambda lvl: 1.0 + 0.2 * lvl,  # +20% за уровень
        'unit': 'x',
    },
]

@app.before_request
def create_tables():
    db.create_all()
    # Заполняем магазин карточек, если пусто
    card_count = ProfileCard.query.count()
    print(f"[CREATE_TABLES] ProfileCard count: {card_count}")
    
    if card_count == 0:
        cards = [
            ProfileCard(name='BG 1', image_url='/static/profile_backgrounds/bg1.png', price=1),
            ProfileCard(name='BG 2', image_url='/static/profile_backgrounds/bg2.png', price=1),
            ProfileCard(name='BG 3', image_url='/static/profile_backgrounds/bg3.png', price=1),
            ProfileCard(name='BG 4', image_url='/static/profile_backgrounds/bg4.png', price=1),
            ProfileCard(name='BG 5', image_url='/static/profile_backgrounds/bg5.png', price=1),
            ProfileCard(name='BG 6', image_url='/static/profile_backgrounds/bg6.png', price=1),
            ProfileCard(name='BG 7', image_url='/static/profile_backgrounds/bg7.png', price=1),
            ProfileCard(name='BG 8', image_url='/static/profile_backgrounds/bg8.png', price=1),
            ProfileCard(name='BG 9', image_url='/static/profile_backgrounds/bg9.png', price=1),
        ]
        db.session.add_all(cards)
        db.session.commit()
        print(f"[CREATE_TABLES] Added {len(cards)} cards to shop")
    else:
        # Показываем существующие карточки
        existing_cards = ProfileCard.query.all()
        print(f"[CREATE_TABLES] Existing cards: {[(c.id, c.name, c.price) for c in existing_cards]}")

@app.route('/user')
def user_profile():
    return render_template(
        'index.html',
        bot_token=TELEGRAM_BOT_TOKEN
    )

# Регистрация пользователя и выдача бонусов
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json(force=True) or {}
    telegram_id = str(data.get('telegram_id', ''))
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    photo_url = data.get('photo_url', '')
    ref_code = data.get('ref_code')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    was_new = False
    was_bonus = False
    if user:
        print(f"[REGISTER] User already exists: {telegram_id}")
        return jsonify({'ok': True, 'user_id': user.id, 'balance': user.balance, 'ref_code': user.ref_code, 'was_new': was_new, 'was_bonus': was_bonus})
    # Генерируем уникальный рефкод
    new_ref_code = secrets.token_hex(4)
    while User.query.filter_by(ref_code=new_ref_code).first():
        new_ref_code = secrets.token_hex(4)
    inviter = None
    inviter_id = None
    if ref_code:
        inviter = User.query.filter_by(ref_code=ref_code).first()
        if inviter:
            inviter_id = inviter.id
    user = User(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        photo_url=photo_url,
        balance=25.0,  # стартовый бонус
        ref_code=new_ref_code,
        ref_by=inviter_id
    )
    db.session.add(user)
    db.session.commit()
    was_new = True
    # Если есть пригласивший — начисляем ему 25 SAB
    if inviter:
        inviter.balance += 25.0
        db.session.add(Referral(user_id=inviter.id, referred_id=user.id))
        db.session.commit()
        was_bonus = True
        print(f"[REFERRAL] Bonus +25 SAB to inviter {inviter.telegram_id} for new user {telegram_id}")
    print(f"[REGISTER] New user: {telegram_id}, ref_by: {inviter_id}")
    return jsonify({'ok': True, 'user_id': user.id, 'balance': user.balance, 'ref_code': user.ref_code, 'was_new': was_new, 'was_bonus': was_bonus})

# Получить профиль
@app.route('/api/profile', methods=['GET'])
def get_profile():
    telegram_id = request.args.get('telegram_id', '')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    return jsonify({
        'ok': True,
        'user_id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'photo_url': user.photo_url,
        'balance': user.balance,
        'card_bg': user.card_bg,
        'ref_code': user.ref_code,
        'ref_by': user.ref_by
    })

@app.route('/api/mine', methods=['POST'])
def start_mining():
    data = request.get_json(force=True) or {}
    telegram_id = str(data.get('telegram_id', ''))
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    now = datetime.utcnow()
    if user.mining_locked_until and user.mining_locked_until > now:
        return jsonify({'ok': False, 'error': 'Mining already in progress', 'locked_until': user.mining_locked_until.isoformat()})
    if user.pending_claim and user.pending_claim > 0:
        return jsonify({'ok': False, 'error': 'Claim your reward first', 'pending_claim': user.pending_claim})
    # Начинаем майнинг: pending_claim = 0
    user.last_mining_at = now
    
    # Базовое время майнинга
    base_mining_time = 28800  # 8 часов (8 * 60 * 60 = 28800 секунд)
    
    # Получаем апгрейды пользователя
    upgrades = {u.type: u.level for u in Upgrade.query.filter_by(user_id=user.id).all()}
    
    # Применяем апгрейд скорости
    speed_lvl = upgrades.get('speed', 0)
    if speed_lvl > 0:
        speed_effect = UPGRADE_TYPES[0]['effect'](speed_lvl)  # speed upgrade
        mining_time = int(base_mining_time * speed_effect)
    else:
        mining_time = base_mining_time
    
    user.mining_locked_until = now + timedelta(seconds=mining_time)
    user.pending_claim = 0
    db.session.commit()
    return jsonify({'ok': True, 'locked_until': user.mining_locked_until.isoformat(), 'pending_claim': user.pending_claim, 'balance': user.balance})

@app.route('/api/claim', methods=['POST'])
def claim():
    data = request.get_json(force=True) or {}
    telegram_id = str(data.get('telegram_id', ''))
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    now = datetime.utcnow()
    if not user.pending_claim or user.pending_claim <= 0:
        return jsonify({'ok': False, 'error': 'Nothing to claim'})
    if user.mining_locked_until and user.mining_locked_until > now:
        return jsonify({'ok': False, 'error': 'Mining not finished'})
    # Начисляем награду
    user.balance += user.pending_claim
    user.pending_claim = 0
    user.mining_locked_until = None
    db.session.commit()
    return jsonify({'ok': True, 'balance': user.balance})

@app.route('/api/mining_status', methods=['GET'])
def mining_status():
    telegram_id = request.args.get('telegram_id', '')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    now = datetime.utcnow()
    locked = False
    seconds_left = 0
    pending_claim = user.pending_claim or 0
    if user.mining_locked_until and user.mining_locked_until > now:
        locked = True
        seconds_left = int((user.mining_locked_until - now).total_seconds())
    elif user.mining_locked_until and user.mining_locked_until <= now and pending_claim == 0:
        # Время истекло, выставляем pending_claim с учётом апгрейдов
        base_reward = user.balance * 0.35
        
        # Получаем апгрейды пользователя
        upgrades = {u.type: u.level for u in Upgrade.query.filter_by(user_id=user.id).all()}
        
        # Применяем апгрейды
        income_mult = upgrades.get('income', 0)
        if income_mult > 0:
            income_effect = UPGRADE_TYPES[1]['effect'](income_mult)  # income upgrade
            base_reward *= income_effect
        
        multiplier_lvl = upgrades.get('multiplier', 0)
        if multiplier_lvl > 0:
            multiplier_effect = UPGRADE_TYPES[2]['effect'](multiplier_lvl)  # multiplier upgrade
            base_reward *= multiplier_effect
        
        pending_claim = round(base_reward, 2)
        user.pending_claim = pending_claim
        db.session.commit()
    return jsonify({'ok': True, 'locked': locked, 'seconds_left': seconds_left, 'balance': user.balance, 'pending_claim': pending_claim})

@app.route('/api/referrals', methods=['GET'])
def get_referrals():
    telegram_id = request.args.get('telegram_id', '')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    # Находим всех, кого пригласил этот пользователь
    refs = User.query.filter_by(ref_by=user.id).all()
    result = []
    for ref in refs:
        result.append({
            'user_id': ref.id,
            'first_name': ref.first_name,
            'last_name': ref.last_name,
            'photo_url': ref.photo_url,
            'card_bg': ref.card_bg,
            'telegram_id': ref.telegram_id
        })
    return jsonify({'ok': True, 'referrals': result})

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    users = User.query.order_by(User.balance.desc()).limit(100).all()
    result = []
    for idx, user in enumerate(users):
        place = idx + 1
        trophy = ''
        if place == 1:
            trophy = '🥇'
        elif place == 2:
            trophy = '🥈'
        elif place == 3:
            trophy = '🥉'
        else:
            trophy = f'#{place}'
        result.append({
            'user_id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'photo_url': user.photo_url,
            'card_bg': user.card_bg,
            'balance': round(user.balance, 2),
            'place': place,
            'trophy': trophy,
            'telegram_id': user.telegram_id
        })
    return jsonify({'ok': True, 'leaderboard': result})

@app.route('/api/set_card_bg', methods=['POST'])
def set_card_bg():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    card_bg = data.get('card_bg')
    if not telegram_id:
        return jsonify({'ok': False, 'error': 'No telegram_id'}), 400
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    user.card_bg = card_bg
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/user_stats', methods=['GET'])
def user_stats():
    telegram_id = request.args.get('telegram_id', '')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    # Days played: days since registration
    days_played = (datetime.utcnow() - user.created_at).days + 1
    # Number of referrals
    num_referrals = User.query.filter_by(ref_by=user.id).count()
    return jsonify({'ok': True, 'days_played': days_played, 'num_referrals': num_referrals})

# --- API: получить список карточек магазина ---
@app.route('/api/shop_cards', methods=['GET'])
def shop_cards():
    cards = ProfileCard.query.all()
    return jsonify({
        'ok': True,
        'cards': [
            {'id': c.id, 'name': c.name, 'image_url': c.image_url, 'price': c.price}
            for c in cards
        ]
    })

# --- API: купить карточку ---
@app.route('/api/buy_card', methods=['POST'])
def buy_card():
    data = request.get_json(force=True) or {}
    telegram_id = str(data.get('telegram_id', ''))
    card_id = int(data.get('card_id', 0))
    user = User.query.filter_by(telegram_id=telegram_id).first()
    card = ProfileCard.query.get(card_id)
    
    print(f"[BUY_CARD] User {telegram_id} trying to buy card {card_id}")
    print(f"[BUY_CARD] User found: {user is not None}, Card found: {card is not None}")
    
    if not user or not card:
        return jsonify({'ok': False, 'error': 'User or card not found'}), 404
    
    # Проверка: уже куплена?
    existing = UserProfileCard.query.filter_by(user_id=user.id, card_id=card.id).first()
    if existing:
        print(f"[BUY_CARD] Card already owned by user {telegram_id}")
        return jsonify({'ok': False, 'error': 'Already owned'})
    
    # Проверка баланса
    if user.balance < card.price:
        print(f"[BUY_CARD] Not enough balance: {user.balance} < {card.price}")
        return jsonify({'ok': False, 'error': 'Not enough SAB'})
    
    # Списываем SAB, добавляем карточку
    user.balance -= card.price
    db.session.add(UserProfileCard(user_id=user.id, card_id=card.id))
    db.session.commit()
    
    print(f"[BUY_CARD] Success! User {telegram_id} bought card {card_id}, new balance: {user.balance}")
    return jsonify({'ok': True, 'new_balance': user.balance})

# --- API: получить купленные карточки пользователя ---
@app.route('/api/my_cards', methods=['GET'])
def my_cards():
    telegram_id = request.args.get('telegram_id', '')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    
    user_cards = UserProfileCard.query.filter_by(user_id=user.id).all()
    card_ids = [uc.card_id for uc in user_cards]
    cards = ProfileCard.query.filter(ProfileCard.id.in_(card_ids)).all()
    
    print(f"[MY_CARDS] User {telegram_id}: {len(user_cards)} user_cards, {len(cards)} cards found")
    print(f"[MY_CARDS] Card IDs: {card_ids}")
    
    return jsonify({
        'ok': True,
        'cards': [
            {'id': c.id, 'name': c.name, 'image_url': c.image_url, 'price': c.price}
            for c in cards
        ]
    })

# --- API: получить список апгрейдов пользователя ---
@app.route('/api/upgrades', methods=['GET'])
def get_upgrades():
    telegram_id = request.args.get('telegram_id', '')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    upgrades = {u.type: u.level for u in Upgrade.query.filter_by(user_id=user.id).all()}
    result = []
    for upg in UPGRADE_TYPES:
        lvl = upgrades.get(upg['type'], 0)
        price = int(upg['base_price'] * (upg['price_mult'] ** lvl))
        result.append({
            'type': upg['type'],
            'title': upg['title'],
            'desc': upg['desc'],
            'level': lvl,
            'next_price': price,
            'effect': upg['effect'](lvl),
            'unit': upg['unit'],
        })
    return jsonify({'ok': True, 'upgrades': result})

# --- API: купить/прокачать апгрейд ---
@app.route('/api/buy_upgrade', methods=['POST'])
def buy_upgrade():
    data = request.get_json(force=True) or {}
    telegram_id = str(data.get('telegram_id', ''))
    upg_type = data.get('type')
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    upg_cfg = next((u for u in UPGRADE_TYPES if u['type'] == upg_type), None)
    if not upg_cfg:
        return jsonify({'ok': False, 'error': 'Unknown upgrade type'}), 400
    upg = Upgrade.query.filter_by(user_id=user.id, type=upg_type).first()
    lvl = upg.level if upg else 0
    price = int(upg_cfg['base_price'] * (upg_cfg['price_mult'] ** lvl))
    if user.balance < price:
        return jsonify({'ok': False, 'error': 'Not enough SAB'})
    # Списываем деньги и повышаем уровень
    user.balance -= price
    if upg:
        upg.level += 1
    else:
        upg = Upgrade(user_id=user.id, type=upg_type, level=1)
        db.session.add(upg)
    db.session.commit()
    return jsonify({'ok': True, 'new_balance': user.balance, 'type': upg_type, 'level': upg.level})

# --- API: добавить награду за игру ---
@app.route('/api/add_game_reward', methods=['POST'])
def add_game_reward():
    data = request.get_json(force=True) or {}
    telegram_id = str(data.get('telegram_id', ''))
    reward = float(data.get('reward', 0))
    
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    
    if reward <= 0:
        return jsonify({'ok': False, 'error': 'Invalid reward amount'})
    
    # Add reward to user balance
    user.balance += reward
    db.session.commit()
    
    print(f"[GAME_REWARD] User {telegram_id} earned {reward} SAB from game")
    return jsonify({'ok': True, 'new_balance': user.balance})

@app.route('/api/send', methods=['POST'])
def send():
    data = request.get_json(force=True) or {}
    from_id = str(data.get('from'))
    to_id = str(data.get('to'))
    amount = float(data.get('amount', 0))
    if not from_id or not to_id or amount <= 0:
        return jsonify({'ok': False, 'error': 'Invalid data'}), 400
    sender = User.query.filter_by(telegram_id=from_id).first()
    receiver = User.query.filter_by(telegram_id=to_id).first()
    if not sender or not receiver:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    if sender.balance < amount:
        return jsonify({'ok': False, 'error': 'Not enough balance'}), 400
    # Списать и зачислить
    sender.balance -= amount
    receiver.balance += amount
    db.session.add(Transaction(from_user_id=sender.id, to_user_id=receiver.id, amount=amount, type='transfer'))
    db.session.commit()
    return jsonify({'ok': True, 'new_balance': sender.balance})

@app.route('/api/history', methods=['GET'])
def history():
    telegram_id = request.args.get('telegram_id', '')
    page = int(request.args.get('page', 1))
    per_page = 10
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    q = Transaction.query.filter(or_(Transaction.from_user_id==user.id, Transaction.to_user_id==user.id)).order_by(desc(Transaction.timestamp))
    total = q.count()
    items = q.offset((page-1)*per_page).limit(per_page).all()
    result = []
    for tx in items:
        if tx.from_user_id == user.id:
            direction = 'out'
            peer = User.query.get(tx.to_user_id)
        else:
            direction = 'in'
            peer = User.query.get(tx.from_user_id)
        peer_id = peer.telegram_id if peer else 'unknown'
        result.append({
            'type': direction,
            'amount': tx.amount,
            'date': tx.timestamp.strftime('%Y-%m-%d %H:%M'),
            'peer_id': peer_id
        })
    return jsonify({'ok': True, 'items': result, 'page': page, 'pages': (total+per_page-1)//per_page})

if __name__ == '__main__':
    app.run(debug=True) 