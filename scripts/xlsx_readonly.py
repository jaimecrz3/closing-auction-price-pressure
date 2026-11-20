"""Minimal OOXML reader. Parses ZIP/XML only; never evaluates or refreshes Excel."""
from datetime import datetime,timedelta
from pathlib import PurePosixPath
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import re

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def colnum(ref):
    n=0
    for c in re.match('[A-Z]+',ref)[0]:n=n*26+ord(c)-64
    return n


def colname(n):
    out=''
    while n:n,r=divmod(n-1,26);out=chr(65+r)+out
    return out


def read_workbook(path):
    result={}
    with ZipFile(path,'r') as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS):strings.append(''.join(si.itertext()))
        styles=ET.fromstring(z.read('xl/styles.xml'))
        formats={int(x.attrib['numFmtId']):x.attrib['formatCode'] for x in styles.findall('s:numFmts/s:numFmt',NS)}
        xfs=[int(x.attrib.get('numFmtId','0')) for x in styles.findall('s:cellXfs/s:xf',NS)]
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        props=wb.find('s:workbookPr',NS);date1904=props is not None and props.attrib.get('date1904') in ['1','true']
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet in wb.findall('s:sheets/s:sheet',NS):
            rid=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target=rels[rid];part=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            tree=ET.fromstring(z.read(part));cells={}
            for c in tree.findall('.//s:sheetData/s:row/s:c',NS):
                ref=c.attrib['r'];typ=c.attrib.get('t','n');v=c.find('s:v',NS);f=c.find('s:f',NS)
                raw=v.text if v is not None else None
                value=raw
                if typ=='s' and raw is not None:value=strings[int(raw)]
                elif typ=='inlineStr':value=''.join(c.find('s:is',NS).itertext())
                style=int(c.attrib.get('s','0'));fmt=xfs[style] if style<len(xfs) else 0
                is_date=fmt in range(14,23) or fmt in [45,46,47] or bool(re.search(r'[dy]',re.sub(r'"[^"]*"|\[[^\]]*\]','',formats.get(fmt,'')).lower()))
                date_value=None
                if is_date and typ=='n' and raw:
                    try:date_value=(datetime(1904,1,1) if date1904 else datetime(1899,12,30))+timedelta(days=float(raw))
                    except (ValueError,OverflowError):pass
                cells[ref]={'value':value,'raw_value':raw,'type':typ,'formula':f.text if f is not None else None,'has_formula':f is not None,'formula_attributes':dict(f.attrib) if f is not None else {},'style':style,'number_format':formats.get(fmt,str(fmt)),'date':date_value.isoformat() if date_value else None}
            dimension=tree.find('s:dimension',NS)
            result[sheet.attrib['name']]={'xml_part':part,'declared_dimension':dimension.attrib['ref'] if dimension is not None else None,'cells':cells,'merged_ranges':[m.attrib['ref'] for m in tree.findall('s:mergeCells/s:mergeCell',NS)],'date1904':date1904}
        core=ET.fromstring(z.read('docProps/core.xml')) if 'docProps/core.xml' in z.namelist() else None
        metadata={x.tag.split('}')[-1]:x.text for x in core} if core is not None else {}
        return result,metadata
