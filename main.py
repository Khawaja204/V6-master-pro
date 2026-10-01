from flask import Flask, jsonify
from api import get_binance_prices, get_price_change
import os

app = Flask(__name__, static_folder='.')

@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/api/prices')
def get_prices():
    """API endpoint for live prices"""
    prices = get_binance_prices()
    changes = get_price_change()
    
    result = {}
    for symbol in prices:
        result[symbol] = {
            'price': prices[symbol]['price'],
            'change': changes.get(symbol, 0)
        }
    
    return jsonify(result)

@app.route('/api/test')
def test():
    return {'status': 'ok', 'message': 'V6 Master Pro API Live'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
