from flask import Flask, render_template, request, redirect, url_for, jsonify
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from apscheduler.schedulers.background import BackgroundScheduler
import random
import os
import requests

app = Flask(__name__)
alerts_db = []

# ================= การตั้งค่า Session ป้องกันการบล็อกราคาหุ้น =================
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})
# ==========================================================================

# ================= การตั้งค่าอีเมลแบบปลอดภัย =================
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "thawatchai2547123@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "vqjx fivg sgkd edyk")
# ==========================================================

def send_email(to_email, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"❌ ส่งอีเมลไม่สำเร็จ: {e}")

def check_stock_prices():
    for alert in alerts_db:
        if alert.get('alerted'): continue
        try:
            stock = yf.Ticker(alert['symbol'], session=session)
            current_price = stock.history(period="1d")['Close'].iloc[-1]
            
            if alert['sell'] and current_price >= float(alert['sell']):
                send_email(alert['email'], f"📈 แจ้งเตือน: {alert['symbol']} ถึงเป้าขาย!", f"ราคาถึง {alert['sell']} แล้ว")
                alert['alerted'] = True
            elif alert['buy'] and current_price <= float(alert['buy']):
                send_email(alert['email'], f"📉 แจ้งเตือน: {alert['symbol']} ถึงเป้าซื้อ!", f"ราคาลงมาถึง {alert['buy']} แล้ว")
                alert['alerted'] = True
        except:
            pass

scheduler = BackgroundScheduler()
scheduler.add_job(func=check_stock_prices, trigger="interval", minutes=1)
scheduler.start()

@app.route('/get_price')
def get_price():
    symbol = request.args.get('symbol', 'AAPL').upper().strip()
    try:
        stock = yf.Ticker(symbol, session=session)
        try:
            price = round(float(stock.fast_info['lastPrice']), 2)
        except:
            hist = stock.history(period="5d")
            price = round(float(hist['Close'].iloc[-1]), 2) if not hist.empty else 0
        return jsonify({'price': price})
    except:
        return jsonify({'price': 0})

@app.route('/')
def index():
    selected_symbol = request.args.get('symbol', 'AAPL').upper().strip()
    error_msg = request.args.get('error')
    
    news_data = []
    try:
        stock = yf.Ticker(selected_symbol, session=session)
        raw_news = stock.news[:3]
        for n in raw_news:
            news_data.append({'title': n.get('title', ''), 'link': n.get('link', '#'), 'publisher': n.get('publisher', '')})
    except:
        pass

    random.seed(selected_symbol) 
    buy_pct = random.randint(20, 80)
    ai_data = {
        'buy': buy_pct, 
        'sell': 100 - buy_pct,
        'status': 'สะสม (Accumulate)' if buy_pct >= 50 else 'ชะลอลงทุน (Wait)'
    }

    return render_template('index.html', alerts=alerts_db, selected=selected_symbol, news=news_data, ai=ai_data, error=error_msg)

@app.route('/add_alert', methods=['POST'])
def add_alert():
    symbol = request.form['symbol'].upper().strip()
    user_email = request.form['user_email'].strip()
    target_buy_str = request.form.get('target_buy', '').strip()
    target_sell_str = request.form.get('target_sell', '').strip()

    if not target_buy_str and not target_sell_str:
        return redirect(url_for('index', symbol=symbol, error="กรุณากำหนดราคาแนวรับหรือแนวต้านอย่างน้อย 1 ช่อง"))

    try:
        stock = yf.Ticker(symbol, session=session)
        try:
            current_price = float(stock.fast_info['lastPrice'])
        except:
            hist = stock.history(period="5d")
            if hist.empty:
                return redirect(url_for('index', symbol=symbol, error=f"ไม่พบข้อมูลหุ้น '{symbol}' บนระบบตลาด"))
            current_price = float(hist['Close'].iloc[-1])
    except:
        return redirect(url_for('index', symbol=symbol, error="ไม่สามารถดึงราคาปัจจุบันได้"))

    target_buy = float(target_buy_str) if target_buy_str else None
    target_sell = float(target_sell_str) if target_sell_str else None

    if target_buy is not None and target_buy >= current_price:
        return redirect(url_for('index', symbol=symbol, error=f"ราคาแนวรับ ({target_buy}) ต้องต่ำกว่าราคาปัจจุบัน ({current_price:.2f})"))

    if target_sell is not None and target_sell <= current_price:
        return redirect(url_for('index', symbol=symbol, error=f"ราคาแนวต้าน ({target_sell}) ต้องสูงกว่าราคาปัจจุบัน ({current_price:.2f})"))

    alerts_db.append({
        'symbol': symbol,
        'email': user_email,
        'buy': target_buy,
        'sell': target_sell,
        'alerted': False
    })
    return redirect(f"/?symbol={symbol}")

@app.route('/delete/<int:index>', methods=['POST'])
def delete_index(index):
    if 0 <= index < len(alerts_db):
        alerts_db.pop(index)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
