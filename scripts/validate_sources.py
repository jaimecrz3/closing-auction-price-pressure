"""Read-only source inventory and integrity diagnostics; no research variables.

Run after use_risklab.ps1, with python -B scripts/validate_sources.py.
Only JSON/CSV diagnostics under reports/source_diagnostics are written.
Uses stdlib to avoid installing dependencies. Timestamp windows are literal
clock labels, not asserted exchange sessions or timezone conversions.
"""
import csv
import gzip
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(os.environ['RISKLAB_DATA_ROOT'])
sys.path.insert(0, str(ROOT / '_catalog'))
import data_paths as dp

OUT = Path(__file__).resolve().parents[1] / 'reports' / 'source_diagnostics'
if dp.data_root() in OUT.parents:
    raise ValueError('Diagnostics must not be written under provider root')
OUT.mkdir(parents=True, exist_ok=True)


def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')


def write_csv(name, rows):
    if not rows:
        return
    with (OUT / name).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def normalized(text):
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


TERMS = ['closing auction imbalance', 'auction imbalance', 'NOII',
         'closing imbalance', 'indicative imbalance', 'paired shares',
         'auction volume', 'S&P 500 constituents', 'S&P 500 membership',
         'index membership', 'historical constituents']


def search_catalogs():
    matches, pilot, counts = [], [], {}
    for name, path in [('catalog', dp.catalog_root() / 'catalog.csv'),
                       ('bloomberg_inventory', dp.library_root() / 'inventory.csv'),
                       ('intraday_inventory', dp.catalog_root() / 'intraday_inventory.csv.gz')]:
        opener = gzip.open if path.suffix == '.gz' else open
        count = 0
        with opener(path, 'rt', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            for row in reader:
                count += 1
                # Split CamelCase as well as punctuation (AuctionVolumes, etc.).
                text = ' '.join(str(v) for v in row.values())
                text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
                norm = normalized(text)
                hits = [term for term in TERMS if normalized(term) in norm]
                if re.search(r'\b(imbalance|noii|paired shares|auction|constituent\w*|membership|members)\b', norm):
                    hits.append('broad construct/constituent/membership search')
                if hits:
                    matches.append({'inventory': name, 'matched_terms': hits, **row})
                if name == 'intraday_inventory' and row.get('path') in PILOTS.values():
                    pilot.append(row)
        counts[name] = {'rows_scanned': count, 'columns': columns}
    save('catalog_search.json', {'terms': TERMS, 'method': 'case/punctuation/CamelCase normalized; broad related-construct search', 'inventories': counts, 'matches': matches, 'pilot_records': pilot})
    print('Catalog matches', len(matches), 'pilot records', len(pilot), flush=True)


def parse_date(value):
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def auction():
    path = dp.get(id='RL-ED340E2FF91E')
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    header_idx = next(i for i, row in enumerate(rows) if row and row[0] == 'Dates')
    fields, labels, securities = rows[header_idx], rows[header_idx-1], rows[header_idx-2]
    ncols = len(fields)
    columns, security = [], ''
    for j in range(1, ncols):
        if securities[j].strip():
            security = securities[j].strip()
        columns.append({'column_index_zero_based': j, 'security': security,
                        'field': fields[j], 'label': labels[j]})
    date_rows, nondates = [], []
    all_date_cells = []
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            if re.fullmatch(r'\d{1,4}[-/]\d{1,2}[-/]\d{1,4}', cell.strip()):
                parsed = parse_date(cell.strip())
                if parsed:
                    all_date_cells.append({'row': i+1, 'column': j+1, 'value': cell, 'date': parsed, 'in_observation_date_column': i > header_idx and j == 0})
        if i > header_idx:
            date = parse_date(row[0].strip()) if row else None
            if date:
                date_rows.append((date, row))
            else:
                nondates.append({'row': i+1, 'first_cells': row[:5], 'nonempty': sum(bool(c.strip()) for c in row)})
    stats = [{'blank': 0, 'non_numeric': Counter(), 'numeric': 0, 'zero': 0,
              'negative': 0, 'nonintegral': 0, 'min': None, 'max': None,
              'first_numeric_date': None, 'last_numeric_date': None} for _ in columns]
    dates, meaningful = Counter(), []
    for date, row in date_rows:
        dates[date] += 1
        present = 0
        for j, stat in enumerate(stats, 1):
            value = row[j].strip() if j < len(row) else ''
            if not value:
                stat['blank'] += 1
                continue
            try:
                number = float(value.replace(',', ''))
                if not math.isfinite(number):
                    raise ValueError()
            except ValueError:
                stat['non_numeric'][value] += 1
                continue
            stat['numeric'] += 1
            present += 1
            stat['zero'] += number == 0
            stat['negative'] += number < 0
            stat['nonintegral'] += not number.is_integer()
            stat['min'] = number if stat['min'] is None else min(stat['min'], number)
            stat['max'] = number if stat['max'] is None else max(stat['max'], number)
            stat['first_numeric_date'] = min(date, stat['first_numeric_date'] or date)
            stat['last_numeric_date'] = max(date, stat['last_numeric_date'] or date)
        if present:
            meaningful.append({'date': date, 'numeric_values': present, 'first_three_securities_values': row[1:7]})
    for col, stat in zip(columns, stats):
        col.update(stat)
        col['non_numeric'] = dict(col['non_numeric'])
    write_csv('mm04_columns.csv', [{**col, 'non_numeric': json.dumps(col['non_numeric'])} for col in columns])
    keycounts = Counter((c['security'], c['field']) for c in columns)
    tokens = Counter()
    for stat in stats:
        tokens.update(stat['non_numeric'])
    result = {'path': str(path), 'size_bytes': path.stat().st_size,
              'catalog_record': dp.find(id='RL-ED340E2FF91E')[0],
              'physical_csv_rows_including_preamble': len(rows),
              'row_width_counts': dict(Counter(map(len, rows))),
              'field_header_row_one_based': header_idx+1,
              'preamble': [{'row': i+1, 'first_cells': r[:8]} for i,r in enumerate(rows[:header_idx-2])],
              'table_shape_date_rows_by_columns': [len(date_rows), ncols],
              'logical_columns': ['Dates'] + [c['security']+' | '+c['field'] for c in columns],
              'field_names': sorted(set(fields[1:])), 'field_labels': sorted(set(labels[1:])),
              'schema': {'Dates': 'M/D/YYYY text parsed as date', 'value_columns': 'nullable numeric; see per-column token and integrality diagnostics'},
              'unique_securities': len(set(c['security'] for c in columns)),
              'unique_dates': len(dates), 'min_date': min(dates), 'max_date': max(dates),
              'first_meaningful_rows': meaningful[:3], 'last_meaningful_rows': meaningful[-3:],
              'duplicate_date_rows': sum(n-1 for n in dates.values()),
              'duplicate_security_field_columns': {str(k):v for k,v in keycounts.items() if v>1},
              'numeric_values': sum(s['numeric'] for s in stats),
              'blank_values': sum(s['blank'] for s in stats),
              'non_numeric_tokens': dict(tokens),
              'zero_values': sum(s['zero'] for s in stats),
              'negative_values': sum(s['negative'] for s in stats),
              'nonintegral_values': sum(s['nonintegral'] for s in stats),
              'nondate_rows_after_header': nondates,
              'date_cells_outside_observation_date_column': [c for c in all_date_cells if not c['in_observation_date_column']],
              'observation_dates_before_2013_05_08': sorted(d for d in dates if d<'2013-05-08'),
              'all_date_cells_scanned': len(all_date_cells),
              'columns': columns}
    save('mm04.json', result)
    print('MM04', result['table_shape_date_rows_by_columns'], result['min_date'], result['max_date'], flush=True)


PILOTS = {'SPY': 'intraday_data/etfs/SPY_full_1min_adjsplitdiv.txt',
          'AAPL': 'intraday_data/stocks/AAPL_full_1min_adjsplitdiv.txt',
          'MSFT': 'intraday_data/stocks/MSFT_full_1min_adjsplitdiv.txt'}
WINDOWS = {'0930_0935': range(570,576), '1530_1559': range(930,960),
           '1531_1600': range(931,961)}


def pilot(symbol, relative):
    path = dp.resolve(relative)
    counts, widths, numeric_types = Counter(), Counter(), [Counter() for _ in range(5)]
    days, seconds_seen, examples, window_samples = {}, set(), [], []
    first_rows, last_rows = [], []
    min_ts, max_ts, previous = None, None, None
    minute_counts = Counter()
    for line_number, row in enumerate(csv.reader(path.open(encoding='utf-8-sig', newline='')), 1):
        counts['total_rows'] += 1
        widths[len(row)] += 1
        if len(first_rows)<3:
            first_rows.append(row)
        last_rows = (last_rows+[row])[-3:]
        if len(row) != 6:
            counts['malformed_width_rows'] += 1
            if len(examples)<20: examples.append({'line':line_number, 'issue':'width', 'row':row})
            continue
        try:
            ts = datetime.fromisoformat(row[0])
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', row[0]):
                counts['nonstandard_timestamp_format'] += 1
        except ValueError:
            counts['malformed_timestamp_rows'] += 1
            continue
        min_ts = ts if min_ts is None else min(min_ts,ts)
        max_ts = ts if max_ts is None else max(max_ts,ts)
        if previous is not None and ts < previous: counts['out_of_order_rows'] += 1
        previous = ts
        day, minute = row[0][:10], ts.hour*60+ts.minute
        info = days.setdefault(day, {'mask':0, 'rows':0, 'first':row[0], 'last':row[0]})
        info['rows'] += 1
        info['first'],info['last'] = min(info['first'],row[0]), max(info['last'],row[0])
        if ts.second == 0 and ts.microsecond == 0:
            if info['mask'] & (1<<minute): counts['duplicate_timestamps'] += 1
            info['mask'] |= 1<<minute
        else:
            counts['non_minute_aligned_rows'] += 1
            if row[0] in seconds_seen: counts['duplicate_timestamps'] += 1
            seconds_seen.add(row[0])
        minute_counts[minute] += 1
        if len(window_samples)<24 and minute in [569,570,571,575,930,959,960,961]:
            window_samples.append({'line':line_number,'row':row})
        try:
            nums = [float(v) for v in row[1:]]
            if not all(math.isfinite(v) for v in nums): raise ValueError()
        except ValueError:
            counts['malformed_or_non_numeric_ohlcv_rows'] += 1
            if len(examples)<20: examples.append({'line':line_number, 'issue':'non_numeric_ohlcv', 'row':row})
            continue
        o,h,l,c,v = nums
        for j,number in enumerate(nums): numeric_types[j]['integer' if number.is_integer() else 'noninteger'] += 1
        if not (l<=o<=h and l<=c<=h and l<=h):
            counts['ohlc_consistency_violations'] += 1
            if len(examples)<20: examples.append({'line':line_number, 'issue':'ohlc_consistency', 'row':row})
        counts['zero_volume_observations'] += v==0
        counts['negative_volume_observations'] += v<0
        counts['nonpositive_price_rows'] += min(o,h,l,c)<=0
        if line_number % 2000000 == 0: print(symbol, line_number, 'rows scanned', flush=True)
    ordered = sorted(days)
    daily = []
    for i,day in enumerate(ordered):
        info = days[day]
        rec = {'date':day, 'rows':info['rows'], 'first_timestamp':info['first'], 'last_timestamp':info['last']}
        for name, window in WINDOWS.items():
            missing = [f'{m//60:02d}:{m%60:02d}' for m in window if not info['mask']&(1<<m)]
            rec[name+'_present_minutes'] = len(window)-len(missing)
            rec[name+'_absent_labels'] = ';'.join(missing)
        for m in [569,570,571,959,960,961]: rec[f'has_{m//60:02d}{m%60:02d}'] = int(bool(info['mask']&(1<<m)))
        nxt = ordered[i+1] if i+1<len(ordered) else None
        rec['next_observed_date'] = nxt or ''
        rec['calendar_gap_to_next_observed_date'] = (datetime.fromisoformat(nxt)-datetime.fromisoformat(day)).days if nxt else ''
        rec['next_observed_date_has_0930'] = int(bool(days[nxt]['mask']&(1<<570))) if nxt else ''
        rec['next_observed_date_has_0931'] = int(bool(days[nxt]['mask']&(1<<571))) if nxt else ''
        daily.append(rec)
    write_csv(symbol.lower()+'_clock_windows.csv', daily)
    write_csv(symbol.lower()+'_minute_label_counts.csv', [{'clock_label':f'{m//60:02d}:{m%60:02d}', 'observations':n} for m,n in sorted(minute_counts.items())])
    result = {'symbol':symbol,'relative_path':relative,'path':str(path),'size_bytes':path.stat().st_size,
              'counts': {key:counts[key] for key in ['total_rows','malformed_width_rows','malformed_timestamp_rows','nonstandard_timestamp_format','out_of_order_rows','duplicate_timestamps','non_minute_aligned_rows','malformed_or_non_numeric_ohlcv_rows','ohlc_consistency_violations','zero_volume_observations','negative_volume_observations','nonpositive_price_rows']},
              'width_counts':dict(widths), 'schema_inferred':['timestamp','open','high','low','close','volume'],
              'numeric_integrality_by_field':dict(zip(['open','high','low','close','volume'],numeric_types)),
              'timestamp_format':'YYYY-MM-DD HH:MM:SS; no embedded timezone',
              'min_timestamp':str(min_ts), 'max_timestamp':str(max_ts), 'observed_dates':len(days),
              'first_rows':first_rows,'last_rows':last_rows,'anomaly_examples':examples,'early_window_examples':window_samples,
              'window_complete_date_counts':{name:sum(d[name+'_present_minutes']==len(window) for d in daily) for name,window in WINDOWS.items()},
              'window_present_minute_histograms':{name:dict(Counter(d[name+'_present_minutes'] for d in daily)) for name in WINDOWS},
              'key_label_date_counts':{key:sum(d[key] for d in daily) for key in daily[0] if key.startswith('has_')},
              'date_pair_count':len(daily)-1,
              'next_observed_date_with_0930_count':sum(d['next_observed_date_has_0930'] or 0 for d in daily),
              'next_observed_date_with_0931_count':sum(d['next_observed_date_has_0931'] or 0 for d in daily),
              'calendar_gap_histogram':dict(Counter(d['calendar_gap_to_next_observed_date'] for d in daily[:-1])),
              'daily_examples':daily[:3]+daily[-3:],
              'interpretation':'Clock-label diagnostics only. Next observed date is not certified next exchange session. Absent labels are not filled or presumed missing trades. Both 15:30-15:59 and 15:31-16:00 are shown without choosing bar convention.'}
    save(symbol.lower()+'.json', result)
    print(symbol,'DONE',result['counts'],result['min_timestamp'],result['max_timestamp'],flush=True)


if __name__ == '__main__':
    search_catalogs()
    auction()
    for symbol, relative in PILOTS.items():
        pilot(symbol, relative)
