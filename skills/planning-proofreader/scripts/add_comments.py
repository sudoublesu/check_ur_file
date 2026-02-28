#!/usr/bin/env python3
"""
add_comments.py - 向 .docx 文件添加 Word 批注（审阅意见）

Usage:
    python add_comments.py input.docx issues.json [output.docx]

issues.json 格式:
[
  {
    "para_index": 2,
    "comment": "「绿化率」应改为「绿地率」，符合规划术语规范",
    "severity": "error"
  }
]

severity 取值:
  error      - 错误（必须修改）
  warning    - 警告（建议修改）
  suggestion - 建议（可考虑修改）

未指定 output.docx 时，输出为 input_批注.docx
"""

import sys
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
COMMENT_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'
COMMENTS_CONTENT_TYPE = (
    'application/vnd.openxmlformats-officedocument'
    '.wordprocessingml.comments+xml'
)


def w(tag):
    return f'{{{W}}}{tag}'


SEVERITY_PREFIX = {
    'error':      '[错误]',
    'warning':    '[警告]',
    'suggestion': '[建议]',
}

COMMENTS_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:comments xmlns:w="{W}"></w:comments>'
)


def add_comments_to_docx(input_path: str, issues: list, output_path: str):
    tmpdir = tempfile.mkdtemp()
    try:
        # 解压 docx
        with zipfile.ZipFile(input_path, 'r') as z:
            z.extractall(tmpdir)

        doc_path = os.path.join(tmpdir, 'word', 'document.xml')
        rels_path = os.path.join(tmpdir, 'word', '_rels', 'document.xml.rels')
        comments_path = os.path.join(tmpdir, 'word', 'comments.xml')

        # 解析 document.xml
        parser = etree.XMLParser(remove_blank_text=False)
        doc_tree = etree.parse(doc_path, parser)
        doc_root = doc_tree.getroot()

        # 获取所有段落：仅 body 的直接子 w:p，与 python-docx doc.paragraphs 编号一致
        # 注意：不能用 .//{w("p")} —— 那会把表格内的段落也计入，导致编号偏移
        body = doc_root.find(f'.//{w("body")}')
        paragraphs = [child for child in body if child.tag == w('p')]

        # 解析或创建 comments.xml
        if os.path.exists(comments_path):
            comments_tree = etree.parse(comments_path, parser)
            comments_root = comments_tree.getroot()
            # 找最大已有 ID
            existing_ids = [
                int(c.get(w('id'), -1))
                for c in comments_root.findall(w('comment'))
            ]
            next_id = max(existing_ids, default=-1) + 1
        else:
            comments_root = etree.fromstring(COMMENTS_TEMPLATE.encode('utf-8'))
            next_id = 0

        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        added = 0

        for issue in issues:
            para_idx = issue.get('para_index', 0)
            text = issue.get('comment', '').strip()
            severity = issue.get('severity', 'warning')

            if para_idx >= len(paragraphs) or not text:
                continue
            if para_idx < 0:
                para_idx = 0  # 回退到第一段（表格问题在 table_positions 不可用时的保底）

            prefix = SEVERITY_PREFIX.get(severity, '[备注]')
            full_text = f'{prefix} {text}'
            cid = str(next_id)
            next_id += 1

            # 1. 向 comments.xml 添加 w:comment
            comment_el = etree.SubElement(comments_root, w('comment'))
            comment_el.set(w('id'), cid)
            comment_el.set(w('author'), '校对系统')
            comment_el.set(w('date'), now)
            comment_el.set(w('initials'), 'AI')
            cp = etree.SubElement(comment_el, w('p'))
            cr = etree.SubElement(cp, w('r'))
            ct = etree.SubElement(cr, w('t'))
            ct.text = full_text

            # 2. 向段落插入 commentRangeStart / End / Reference
            para_el = paragraphs[para_idx]

            crs = etree.Element(w('commentRangeStart'))
            crs.set(w('id'), cid)
            para_el.insert(0, crs)

            cre = etree.Element(w('commentRangeEnd'))
            cre.set(w('id'), cid)
            para_el.append(cre)

            run = etree.SubElement(para_el, w('r'))
            rpr = etree.SubElement(run, w('rPr'))
            rs = etree.SubElement(rpr, w('rStyle'))
            rs.set(w('val'), 'CommentReference')
            cref = etree.SubElement(run, w('commentReference'))
            cref.set(w('id'), cid)

            added += 1

        # 写回 document.xml
        doc_tree.write(doc_path, xml_declaration=True, encoding='UTF-8',
                       standalone=True, pretty_print=False)

        # 写回 comments.xml
        ct = etree.ElementTree(comments_root)
        ct.write(comments_path, xml_declaration=True, encoding='UTF-8',
                 standalone=True, pretty_print=False)

        # 更新 .rels：添加 comments 关系（如不存在）
        rels_tree = etree.parse(rels_path, parser)
        rels_root = rels_tree.getroot()
        has_rel = any(
            rel.get('Type') == COMMENT_REL
            for rel in rels_root
        )
        if not has_rel:
            rel_el = etree.SubElement(rels_root, f'{{{R_NS}}}Relationship')
            rel_el.set('Id', 'rIdComments')
            rel_el.set('Type', COMMENT_REL)
            rel_el.set('Target', 'comments.xml')
            rels_tree.write(rels_path, xml_declaration=True, encoding='UTF-8',
                            standalone=True)

        # 更新 [Content_Types].xml：确保 word/comments.xml 有正确的 Override
        ct_path = os.path.join(tmpdir, '[Content_Types].xml')
        if os.path.exists(ct_path):
            ct_tree = etree.parse(ct_path, parser)
            ct_root = ct_tree.getroot()
            has_ct = any(
                el.get('PartName') in ('/word/comments.xml', 'word/comments.xml')
                for el in ct_root
            )
            if not has_ct:
                override = etree.SubElement(ct_root, f'{{{CT_NS}}}Override')
                override.set('PartName', '/word/comments.xml')
                override.set('ContentType', COMMENTS_CONTENT_TYPE)
                ct_tree.write(ct_path, xml_declaration=True, encoding='UTF-8',
                              standalone=True)

        # 重新打包为 docx
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for dirpath, _, files in os.walk(tmpdir):
                for fname in files:
                    fpath = os.path.join(dirpath, fname)
                    arcname = os.path.relpath(fpath, tmpdir)
                    zout.write(fpath, arcname)

        print(f'完成：已添加 {added} 条批注 → {output_path}')

    finally:
        shutil.rmtree(tmpdir)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    input_path = sys.argv[1]
    issues_path = sys.argv[2]

    if len(sys.argv) >= 4:
        output_path = sys.argv[3]
    else:
        base, ext = os.path.splitext(input_path)
        output_path = f'{base}_批注{ext}'

    with open(issues_path, 'r', encoding='utf-8') as f:
        issues = json.load(f)

    add_comments_to_docx(input_path, issues, output_path)


if __name__ == '__main__':
    main()
