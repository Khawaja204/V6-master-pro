def calculate_54_point_score(symbol, klines, order_book, ticker, extra=None):
    return {'score': 50, 'signal': 'WAIT', 'badge': 'GREY',
            'sl': 0, 'tp1': 0, 'tp2': 0, 'tp3': 0,
            'rr_ratio': 0, 'atr': 0, 'rsi': 50,
            'breakdown': {}, 'category_scores': {}}
