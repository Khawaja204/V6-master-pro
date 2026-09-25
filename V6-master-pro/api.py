import requests

def get_binance_prices():
    """Fetch live prices from Binance"""
    coins = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']
    prices = {}
    
    try:
        for coin in coins:
            try:
                url = f'https://api.binance.com/api/v3/ticker/price?symbol={coin}'
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    symbol = coin.replace('USDT', '')
                    prices[symbol] = {
                        'price': float(data['price']),
                        'symbol': symbol
                    }
            except Exception as e:
                print(f"Error fetching {coin}: {e}")
                continue
                
    except Exception as e:
        print(f"API Error: {e}")
    
    return prices if prices else {'BTC': {'price': 0, 'symbol': 'BTC'}, 'ETH': {'price': 0, 'symbol': 'ETH'}, 'SOL': {'price': 0, 'symbol': 'SOL'}, 'XRP': {'price': 0, 'symbol': 'XRP'}}

def get_price_change():
    """Get 24h price change from Binance"""
    coins = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']
    changes = {}
    
    try:
        for coin in coins:
            try:
                url = f'https://api.binance.com/api/v3/ticker/24hr?symbol={coin}'
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    symbol = coin.replace('USDT', '')
                    changes[symbol] = float(data['priceChangePercent'])
            except Exception as e:
                print(f"Error fetching change for {coin}: {e}")
                changes[coin.replace('USDT', '')] = 0
                continue
    except Exception as e:
        print(f"API Error: {e}")
    
    return changes
