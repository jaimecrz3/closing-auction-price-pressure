"""Reproduce workbook cross-checks of manually reviewed screenshot transcriptions.

This is not OCR: the fixed review ledger below was visually checked against the
five supplied images. Hash changes require a new manual review. No provider data
is changed; outputs are licensed diagnostic records, not an analysis dataset.
"""
import csv
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[1]
SUPPORT = BASE/'data/raw_bloomberg/support/bloomberg_hp_evidence_2026-11-02'
REVIEWED_HASHES = {
    'hp_spy_up_2016-05-09_to_05-10.png':'ff028ef306feebbead96b056fe58af11060907ee76ddf6fc0e58cc827c1c6595',
    'hp_spy_up_2016-09-06_to_09-08.png':'c8017ad0ab9242fa1d36b2042b4daeBA9802c818ce84b0d9310e00da264d8b9d'.lower(),
    'hp_spy_up_2016-09-13_to_09-14.png':'84b1d334cd0a787d2a5889a8c7d2d56bded2e33e987bfc327590a3ad6a594583',
    'hp_wmt_un_2025-12-08_to_12-31.png':'378dd4c7bef36bb25504fb1b08f7885a90891e5e31febf909d8a0edf22145cf0',
    'hp_wmt_uw_2025-12-09_to_12-31.png':'8da892f7a0886bf8dc596f1328fd9419af7e7bc1c0571d35c2bc513b6e4068c1',
    'terminal_field_notes_2026-11-02.md':'bc179e7f3f647bfd4160ea54c40187d2375ef2615fe885ead81415f9e7d88f2b',
}
# Security, date, displayed value, source filename. Values are diagnostic only.
VISUAL_REVIEW = [
    ('SPY UP EQUITY','2016-05-09',2890705,'hp_spy_up_2016-05-09_to_05-10.png'),
    ('SPY UP EQUITY','2016-05-10',100,'hp_spy_up_2016-05-09_to_05-10.png'),
    ('SPY UP EQUITY','2016-09-06',100,'hp_spy_up_2016-09-06_to_09-08.png'),
    ('SPY UP EQUITY','2016-09-07',1506352,'hp_spy_up_2016-09-06_to_09-08.png'),
    ('SPY UP EQUITY','2016-09-08',100,'hp_spy_up_2016-09-06_to_09-08.png'),
    ('SPY UP EQUITY','2016-09-13',100,'hp_spy_up_2016-09-13_to_09-14.png'),
    ('SPY UP EQUITY','2016-09-14',847609,'hp_spy_up_2016-09-13_to_09-14.png'),
    ('WMT UN EQUITY','2025-12-08',4167867,'hp_wmt_un_2025-12-08_to_12-31.png'),
    ('WMT UW EQUITY','2025-12-09',5257197,'hp_wmt_uw_2025-12-09_to_12-31.png'),
    ('WMT UW EQUITY','2025-12-31',2732141,'hp_wmt_uw_2025-12-09_to_12-31.png'),
]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def review(series, actions, output):
    """Called by offline audit; series are existing source diagnostic records."""
    for name, expected in REVIEWED_HASHES.items():
        if digest(SUPPORT/name) != expected:
            raise ValueError(f'Manually reviewed evidence changed: {name}; review images/notes again')
    records=[]
    notes=(SUPPORT/'terminal_field_notes_2026-11-02.md').read_text(encoding='utf-8')
    for security,date,value,filename in VISUAL_REVIEW:
        # Verify that the source transcript still contains the reviewed row.
        if not any(date in line and f'{value:,}' in line and filename in line for line in notes.splitlines()):
            raise ValueError(f'Transcript differs from reviewed screenshot row: {security} {date}')
        symbol=security.split()[0]
        source=series.get(('action_volume',symbol),[])
        matching=[r for r in source if r['date']==date]
        if security=='WMT UW EQUITY':
            status='new venue line absent from workbook; no splice'
        else:
            if len(matching)!=1 or matching[0]['value']!=value:
                raise ValueError(f'Screenshot/workbook disagreement: {security} {date}')
            status='exact numeric match to static workbook'
        records.append({'security':security,'date_or_range':date,'displayed_value':value,
                        'screenshot':filename,'screenshot_sha256':REVIEWED_HASHES[filename],
                        'review_method':'manual visual review; not OCR','workbook_check':status,
                        'full_field_identity':'user reports PQ817; screenshot label truncated',
                        'retrieval_timestamp':'UNKNOWN'})
    records.append({'security':'WMT UN EQUITY','date_or_range':'2025-12-09 through 2025-12-31',
                    'displayed_value':'blank auction cells on in-range trading dates',
                    'screenshot':'hp_wmt_un_2025-12-08_to_12-31.png',
                    'screenshot_sha256':REVIEWED_HASHES['hp_wmt_un_2025-12-08_to_12-31.png'],
                    'review_method':'manual visual review; not OCR',
                    'workbook_check':'no dated auction records beyond 2025-12-08; not zeros',
                    'full_field_identity':'user reports PQ817; screenshot label truncated',
                    'retrieval_timestamp':'UNKNOWN'})
    with (output/'terminal_screenshot_crosscheck.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    # Audit all proprietary evidence plus the course template without altering it.
    template=BASE/'presentation/progress_update/MMF_2026_Project_Progress_Update_Template.pptx'
    files=sorted(p for p in (BASE/'data/raw_bloomberg/support').rglob('*') if p.is_file())+[template]
    provenance=[{'path':p.relative_to(BASE).as_posix(),'sha256':digest(p),'bytes':p.stat().st_size,
                 'retrieved_at':'UNKNOWN','review_type':('manual screenshot' if p.suffix=='.png' else
                 'user-transcribed FLDS/DPDF; not screenshot-verified' if p.name.startswith('terminal_field_notes') else
                 'course template XML text/notes inspection' if p.suffix=='.pptx' else 'manual support text')} for p in files]
    with (output/'terminal_evidence_provenance.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(provenance[0]));w.writeheader();w.writerows(provenance)
    # Include speaker notes: timing and policy prompts are not just visible slides.
    parts=[]
    with ZipFile(template,'r') as z:
        for part in sorted(z.namelist()):
            if re.fullmatch(r'ppt/(slides/slide|notesSlides/notesSlide)\d+\.xml',part):
                parts.append({'part':part,'text':[t.text or '' for t in ET.fromstring(z.read(part)).findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t')]})
    (output/'progress_template_review.json').write_text(json.dumps(parts,indent=2),encoding='utf-8')
    if max(a['events'] for a in actions)>=275:
        raise ValueError('DVD_HIST_ALL count reaches 275-record cap: completeness review required')
    return {'numeric_rows_visually_verified':10,'workbook_matches':8,'new_WMT_UW_rows':2,
            'WMT_UN_blank_range_visually_verified':True,'max_events':max(a['events'] for a in actions),
            'at_275_cap':False,'full_field_identity_screenshot_verified':False}
