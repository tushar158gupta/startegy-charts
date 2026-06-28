from pathlib import Path
import json
import re

SRC_DIR = Path('charts/dojiHammer_v2')
DEST_DIR = Path('charts-next/public/data/dojiHammer_v2')
DEST_DIR.mkdir(parents=True, exist_ok=True)

META_RE = re.compile(r'<span\s+class="sub">\s*Token:\s*(\d+)\s*(?:&nbsp;|)\s*·\s*(?:&nbsp;|)\s*(v\d+)\s*</span>', re.IGNORECASE)
STAT_RE = re.compile(r'<div\s+class="stat">\s*<div\s+class="v"[^>]*>([^<]+)</div>\s*<div\s+class="l">([^<]+)</div>\s*</div>', re.IGNORECASE)

paths = sorted(SRC_DIR.glob('*.html'))
if not paths:
    raise SystemExit(f'No HTML files found in {SRC_DIR}')

index = []

for html_path in paths:
    if html_path.name == 'index.html':
        continue

    html = html_path.read_text(encoding='utf-8')
    symbol = html_path.stem

    meta = META_RE.search(html)
    if not meta:
        raise SystemExit(f'Missing token/version metadata in {html_path}')
    token = int(meta.group(1))
    version = meta.group(2)

    stats = {match.group(2).strip(): match.group(1).strip() for match in STAT_RE.finditer(html)}
    required_stats = ['Signals', 'Wins', 'SL Hits', 'Win Rate']
    if not all(name in stats for name in required_stats):
        raise SystemExit(f'Missing summary stats in {html_path}: {stats}')

    signals_count = int(stats['Signals'])
    wins = int(stats['Wins'])
    sl = int(stats['SL Hits'])
    wr = stats['Win Rate'].strip()
    if wr.endswith('%'):
        wr = wr[:-1].strip()

    start = html.find('const DATA')
    if start == -1:
        raise SystemExit(f'No DATA definition found in {html_path}')
    data_section = html[start:]
    brace_start = data_section.find('{')
    if brace_start == -1:
        raise SystemExit(f'No opening brace for DATA in {html_path}')

    depth = 0
    end = None
    for i, ch in enumerate(data_section[brace_start:], start=brace_start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f'Failed to parse DATA object in {html_path}')

    data_text = data_section[brace_start:end]
    data = json.loads(data_text)

    timeframes = {}
    for tf, tfdata in data.items():
        if not isinstance(tfdata, dict):
            continue
        candles = tfdata.get('candleData', [])
        signals_list = tfdata.get('sigData', []) or []
        if not isinstance(candles, list):
            raise SystemExit(f'Bad candleData for {symbol} {tf}')
        if not isinstance(signals_list, list):
            raise SystemExit(f'Bad sigData for {symbol} {tf}')

        time_index = {c['time']: idx for idx, c in enumerate(candles) if isinstance(c, dict) and 'time' in c}
        signals = []
        for sig in signals_list:
            if not isinstance(sig, dict):
                continue
            c2unix = sig.get('c2Unix')
            if c2unix is None:
                continue
            idx = time_index.get(c2unix, 0)
            signal = {
                'time': int(c2unix),
                'candles': {
                    'c1Idx': max(idx - 1, 0),
                    'c2Idx': idx,
                    'c3Idx': min(idx + 1, len(candles) - 1) if candles else 0,
                },
                'entry': float(sig.get('entry') or 0),
                'sl': float(sig.get('sl') or 0),
                't1': float(sig.get('t1') or 0),
                't2': float(sig.get('t2') or 0),
                'outcome': sig.get('outcome') or '',
                'pnlPct': float(sig.get('pnl') or 0),
                'status': 'CONFIRMED',
                'datetime': sig.get('time', ''),
                'tf': tf,
            }
            if sig.get('t3') not in (None, ''):
                try:
                    signal['t3'] = float(sig.get('t3'))
                except ValueError:
                    signal['t3'] = sig.get('t3')
            if sig.get('rsi') not in (None, '', '—'):
                try:
                    signal['rsi'] = float(sig.get('rsi'))
                except ValueError:
                    signal['rsi'] = sig.get('rsi')
            if sig.get('adx') not in (None, '', '—'):
                try:
                    signal['adx'] = float(sig.get('adx'))
                except ValueError:
                    signal['adx'] = sig.get('adx')
            signals.append(signal)

        timeframes[tf] = {
            'candles': candles,
            'signals': signals,
        }

    out = {
        'symbol': symbol,
        'token': token,
        'stratLabel': 'Doji Hammer',
        'version': version,
        'signals': signals_count,
        'wins': wins,
        'sl': sl,
        'wr': wr,
        'timeframes': timeframes,
    }

    out_path = DEST_DIR / f'{symbol}.json'
    out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
    index.append({'symbol': symbol, 'total': signals_count, 'wins': wins, 'sl': sl, 'winRate': wr})
    print(f'Wrote {out_path}')

index.sort(key=lambda item: float(item['winRate']) if isinstance(item['winRate'], str) and item['winRate'] not in ('N/A', '') else -1, reverse=True)
index_path = DEST_DIR / 'index.json'
index_path.write_text(json.dumps(index, indent=2), encoding='utf-8')
print(f'Wrote {index_path} with {len(index)} entries')
