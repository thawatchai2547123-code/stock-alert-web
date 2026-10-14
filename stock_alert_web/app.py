from flask import Flask, render_template, request, redirect, url_for, jsonify
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
import random
import os
import requests
import json

app = Flask(__name__)
DB_FILE = 'alerts_db.json'

# ================= 1. ตั้งค่า URL ของ Google Apps Script =================
# วาง URL ที่ได้จากการ Deploy Google Apps Script ไว้ในเครื่องหมายคำพูดนี้
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwvOdsnzgzG26xGegG_g9BpONWh5bKgdeKVdjaREcTtwgQHayMiQ-PkoP7OwsqO_USr/exec"

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
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })
    try:
        stock = yf.Ticker(symbol, session=session)
        try:
            val = stock.fast_info.get('lastPrice')
            if val and float(val) > 0: return round(float(val), 2)
        except: pass
        try:
            df = stock.history(period="1d", session=session)
            if not df.empty:
                val = df['Close'].iloc[-1]
                if val and float(val) > 0: return round(float(val), 2)
        except: pass
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d"
        res = session.get(url, timeout=5)
        data = res.json()
        val = data['chart']['result'][0]['meta']['regularMarketPrice']
        if val and float(val) > 0: return round(float(val), 2)
    except Exception as e:
        print(f"❌ ดึงราคา {symbol} ไม่สำเร็จ: {e}")
    return 0.0

# ================= 2. ฟังก์ชันส่งเมลผ่าน Google Apps Script (ไม่ติดบล็อก Render) =================
def send_email(to_email, subject, body):
    try:
        print(f"📧 กำลังส่งคำขอให้ Google Apps Script ส่งเมลไปยัง {to_email}...")
        payload = {
            "email": to_email,
            "subject": subject,
            "body": body
        }
        headers = {"Content-Type": "application/json"}
        
        response = requests.post(APPS_SCRIPT_URL, data=json.dumps(payload), headers=headers, timeout=15)
        result = response.json()
        
        if result.get("status") == "success":
            print(f"✅ ส่งอีเมลผ่าน Apps Script สำเร็จ!")
            return True
        else:
            print(f"❌ Apps Script แจ้งข้อผิดพลาด: {result.get('message')}")
            return False
    except Exception as e:
        print(f"❌ เชื่อมต่อ Apps Script ล้มเหลว: {e}")
        return False

def check_stock_prices():
    alerts = load_alerts()
    if not alerts: return
        
    updated = False
    print(f"🔄 บอทกำลังตรวจราคา... (มี {len(alerts)} รายการเฝ้าดู)")
    
    for alert in alerts:
        if alert.get('alerted'): 
            continue
            
        current_price = get_live_price(alert['symbol'])
        if current_price <= 0: continue
        
        if alert['sell'] is not None and current_price >= float(alert['sell']):
            print(f"🚀 {alert['symbol']} ถึงเป้าขาย! กำลังส่งอีเมล...")
            if send_email(alert['email'], f"📈 หุ้น {alert['symbol']} ถึงเป้าขายแล้ว!", f"ราคาหุ้น {alert['symbol']} ขึ้นมาถึงเป้าหมาย {alert['sell']} (ราคาปัจจุบัน {current_price})"):
                alert['alerted'] = True
                updated = True

        elif alert['buy'] is not None and current_price <= float(alert['buy']):
            print(f"📉 {alert['symbol']} ถึงเป้าซื้อ! กำลังส่งอีเมล...")
            if send_email(alert['email'], f"📉 หุ้น {alert['symbol']} ถึงเป้าซื้อแล้ว!", f"ราคาหุ้น {alert['symbol']} ลงมาถึงเป้าหมาย {alert['buy']} (ราคาปัจจุบัน {current_price})"):
                alert['alerted'] = True
                updated = True

    if updated:
        save_alerts(alerts)

scheduler = BackgroundScheduler()
scheduler.add_job(func=check_stock_prices, trigger="interval", minutes=1)
scheduler.start()

@app.route('/get_price')
def get_price():
    symbol = request.args.get('symbol', '').upper().strip()
    if not symbol: return jsonify({'price': 0})
    price = get_live_price(symbol)
    return jsonify({'price': price})

@app.route('/ping')
def ping():
    check_stock_prices()
    return "OK", 200

@app.route('/')
def index():
    alerts = load_alerts()
    selected_symbol = request.args.get('symbol', '').upper().strip()
    error_msg = request.args.get('error')
    
    news_data = []
    ai_data = None

    if selected_symbol:
        try:
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            stock = yf.Ticker(selected_symbol, session=session)
            raw_news = stock.news[:3]
            for n in raw_news:
                news_data.append({'title': n.get('title', ''), 'link': n.get('link', '#'), 'publisher': n.get('publisher', '')})
        except: pass

        random.seed(selected_symbol) 
        buy_pct = random.randint(20, 80)
        ai_data = {
            'buy': buy_pct, 
            'sell': 100 - buy_pct,
            'status': 'สะสม (Accumulate)' if buy_pct >= 50 else 'ชะลอลงทุน (Wait)'
        }

    return render_template('index.html', alerts=alerts, selected=selected_symbol, news=news_data, ai=ai_data, error=error_msg)

@app.route('/add_alert', methods=['POST'])
def add_alert():
    symbol = request.form['symbol'].upper().strip()
    user_email = request.form['user_email'].strip()
    target_buy_str = request.form.get('target_buy', '').strip()
    target_sell_str = request.form.get('target_sell', '').strip()

    if not symbol: return redirect(url_for('index', error="กรุณาระบุชื่อหุ้น"))
    if not target_buy_str and not target_sell_str: return redirect(url_for('index', symbol=symbol, error="กรุณากำหนดราคาอย่างน้อย 1 ช่อง"))

    current_price = get_live_price(symbol)
    if current_price <= 0: return redirect(url_for('index', symbol=symbol, error=f"ไม่สามารถดึงราคาปัจจุบันได้"))

    target_buy = float(target_buy_str) if target_buy_str else None
    target_sell = float(target_sell_str) if target_sell_str else None

    alerts = load_alerts()
    alerts.append({
        'symbol': symbol,
        'email': user_email,
        'buy': target_buy,
        'sell': target_sell,
        'alerted': False
    })
    save_alerts(alerts)
    
    check_stock_prices()
    
    return redirect(f"/?symbol={symbol}")

@app.route('/delete/<int:index>', methods=['POST'])
def delete_index(index):
    alerts = load_alerts()
    if 0 <= index < len(alerts):
        alerts.pop(index)
        save_alerts(alerts)
    return redirect('/')

@app.route('/test_email', methods=['POST'])
def test_email_route():
    test_email = request.form.get('test_email', '').strip()
    if not test_email:
        return jsonify({'status': 'error', 'message': 'กรุณากรอกอีเมลก่อนกดทดสอบ'})
    
    print(f"🛠️ เริ่มการทดสอบส่งอีเมลผ่าน Apps Script ไปยัง: {test_email}")
    success = send_email(test_email, "🛠️ ทดสอบระบบแจ้งเตือน Stock Alert", "สวัสดี! นี่คืออีเมลทดสอบผ่าน Google Apps Script สำเร็จเรียบร้อยดีครับ 🎉")
    
    if success:
        return jsonify({'status': 'success', 'message': f'ส่งอีเมลทดสอบสำเร็จ! เช็คกล่องจดหมายของคุณได้เลย'})
    else:
        return jsonify({'status': 'error', 'message': 'ส่งล้มเหลว! โปรดเช็ค Log ของ Render'})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
