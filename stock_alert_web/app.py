from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
import random
import os
import requests
import json

app = Flask(__name__)
# ตั้งค่า Secret Key สำหรับใช้งาน Session (Login)
app.secret_key = 'stock_alert_pro_secret_key_neon'
DB_FILE = 'alerts_db.json'

# ================= 1. ตั้งค่า URL ของ Google Apps Script =================
APPS_SCRIPT_URL = "script.google.com/macros/s/AKfycbwvOdsnzgzG26xGegG_g9BpONWh5bKgdeKVdjaREcTtwgQHayMiQ-PkoP7OwsqO_USr/exec"

def load_alerts():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_alerts(alerts):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=4)

def get_live_price(symbol):
    if not symbol: return 0.0
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0"})
    try:
        stock = yf.Ticker(symbol, session=sess)
        try:
            val = stock.fast_info.get('lastPrice')
            if val and float(val) > 0: return round(float(val), 2)
        except: pass
        try:
            df = stock.history(period="1d", session=sess)
            if not df.empty:
                val = df['Close'].iloc[-1]
                if val and float(val) > 0: return round(float(val), 2)
        except: pass
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d"
        res = sess.get(url, timeout=5)
        data = res.json()
        val = data['chart']['result'][0]['meta']['regularMarketPrice']
        if val and float(val) > 0: return round(float(val), 2)
    except Exception as e:
        print(f"❌ ดึงราคา {symbol} ไม่สำเร็จ: {e}")
    return 0.0

def send_email(to_email, subject, body):
    try:
        payload = {"email": to_email, "subject": subject, "body": body}
        headers = {"Content-Type": "application/json"}
        response = requests.post(APPS_SCRIPT_URL, data=json.dumps(payload), headers=headers, timeout=15)
        result = response.json()
        if result.get("status") == "success":
            return True
        return False
    except Exception:
        return False

def check_stock_prices():
    alerts = load_alerts()
    if not alerts: return
    updated = False
    
    for alert in alerts:
        if alert.get('alerted'): continue
        current_price = get_live_price(alert['symbol'])
        if current_price <= 0: continue
        
        if alert['sell'] is not None and current_price >= float(alert['sell']):
            subject = f"[แจ้งเตือน] หุ้น {alert['symbol']} ถึงราคาเป้าหมาย (ขาย)"
            body = f"เรียน คุณผู้ใช้งาน,\n\nหุ้น {alert['symbol']} ปรับตัวขึ้นมาถึง {alert['sell']} บาทแล้ว (ล่าสุด: {current_price} บาท)\n\nจาก Stock Alert Dashboard"
            if send_email(alert['email'], subject, body):
                alert['alerted'] = True
                updated = True

        elif alert['buy'] is not None and current_price <= float(alert['buy']):
            subject = f"[แจ้งเตือน] หุ้น {alert['symbol']} ถึงราคาเป้าหมาย (ซื้อ)"
            body = f"เรียน คุณผู้ใช้งาน,\n\nหุ้น {alert['symbol']} ปรับตัวลดลงมาถึง {alert['buy']} บาทแล้ว (ล่าสุด: {current_price} บาท)\n\nจาก Stock Alert Dashboard"
            if send_email(alert['email'], subject, body):
                alert['alerted'] = True
                updated = True

    if updated: save_alerts(alerts)

scheduler = BackgroundScheduler()
scheduler.add_job(func=check_stock_prices, trigger="interval", minutes=1)
scheduler.start()

# ================= ระบบ Login / Logout =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if email:
            session['user_email'] = email
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('login'))

@app.route('/get_price')
def get_price_route():
    symbol = request.args.get('symbol', '').upper().strip()
    return jsonify({'price': get_live_price(symbol) if symbol else 0})

@app.route('/ping')
def ping():
    check_stock_prices()
    return "OK", 200

@app.route('/')
def index():
    # บังคับ Login
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    user_email = session['user_email']
    all_alerts = load_alerts()
    # ดึงเฉพาะแจ้งเตือนของ User คนนี้
    user_alerts = [a for a in all_alerts if a['email'] == user_email]
    
    selected_symbol = request.args.get('symbol', '').upper().strip()
    error_msg = request.args.get('error')
    
    news_data = []
    ai_data = None

    if selected_symbol:
        try:
            sess = requests.Session()
            sess.headers.update({"User-Agent": "Mozilla/5.0"})
            stock = yf.Ticker(selected_symbol, session=sess)
            for n in stock.news[:3]:
                news_data.append({'title': n.get('title', ''), 'link': n.get('link', '#'), 'publisher': n.get('publisher', '')})
        except: pass
        random.seed(selected_symbol) 
        buy_pct = random.randint(20, 80)
        ai_data = {'buy': buy_pct, 'sell': 100 - buy_pct, 'status': 'สะสม (Accumulate)' if buy_pct >= 50 else 'ชะลอลงทุน (Wait)'}

    return render_template('index.html', alerts=user_alerts, selected=selected_symbol, news=news_data, ai=ai_data, error=error_msg, user_email=user_email)

@app.route('/add_alert', methods=['POST'])
def add_alert():
    if 'user_email' not in session: return redirect(url_for('login'))
    
    symbol = request.form['symbol'].upper().strip()
    user_email = session['user_email'] # ดึงจากระบบ ไม่ต้องให้กรอก
    target_buy_str = request.form.get('target_buy', '').strip()
    target_sell_str = request.form.get('target_sell', '').strip()

    if not symbol: return redirect(url_for('index', error="กรุณาระบุชื่อหุ้น"))
    
    target_buy = float(target_buy_str) if target_buy_str else None
    target_sell = float(target_sell_str) if target_sell_str else None

    alerts = load_alerts()
    alerts.append({'symbol': symbol, 'email': user_email, 'buy': target_buy, 'sell': target_sell, 'alerted': False})
    save_alerts(alerts)
    check_stock_prices()
    return redirect(f"/?symbol={symbol}")

@app.route('/delete/<symbol>/<buy>/<sell>', methods=['POST'])
def delete_alert(symbol, buy, sell):
    if 'user_email' not in session: return redirect(url_for('login'))
    user_email = session['user_email']
    
    alerts = load_alerts()
    buy_val = float(buy) if buy != 'None' else None
    sell_val = float(sell) if sell != 'None' else None
    
    # ลบเฉพาะรายการของตัวเองที่ตรงกับข้อมูล
    for i, a in enumerate(alerts):
        if a['email'] == user_email and a['symbol'] == symbol and a['buy'] == buy_val and a['sell'] == sell_val:
            alerts.pop(i)
            break
            
    save_alerts(alerts)
    return redirect('/')

@app.route('/test_email', methods=['POST'])
def test_email_route():
    if 'user_email' not in session:
        return jsonify({'status': 'error', 'message': 'กรุณาเข้าสู่ระบบ'})
    
    test_email = session['user_email']
    success = send_email(test_email, "[ทดสอบระบบ] Stock Alert", "การแจ้งเตือนทำงานปกติครับ!")
    if success:
        return jsonify({'status': 'success', 'message': 'ส่งสำเร็จ! ตรวจสอบกล่องข้อความของคุณ'})
    else:
        return jsonify({'status': 'error', 'message': 'ส่งล้มเหลว! โปรดเช็ค Google Apps Script'})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
