from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image as PILImage, ImageDraw
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path('E:/ASTC_Compression')
WORK = ROOT / 'tmp/pdfs/chat-export-20261113'
OUT = ROOT / 'output/chat/20261113'
PDF = ROOT / 'output/pdf/Unity-ASTC-聊天记录与总结-20261113.pdf'
MD = OUT / 'Unity-ASTC-聊天记录与总结-20261113.md'
WIDTH = A4[0] - 88


def clean_user(text: str) -> str:
    result: list[str] = []
    annotation = re.search(r'<response-annotations>\s*(.*?)\s*</response-annotations>', text, re.S)
    if annotation:
        for row in json.loads(annotation.group(1)):
            result.append('选中的原文\n\n> ' + row['text'])
    if '## My request:' in text:
        text = text.split('## My request:', 1)[1]
    text = text.strip()
    if text:
        result.append(text)
    return '\n\n'.join(result)


def inline(text: str) -> str:
    text = re.sub(r':codex-annotation\{index="(\d+)"\}', r'〔回复所选原文 \1〕', text)
    text = re.sub(r':codex-file-citation\{path="([^"]+)" purpose="[^"]+"\}', r'文件链接：\1', text)
    text = re.sub(r'\[([^\]]+)\]\(<([^>]+)>\)', r'\1（\2）', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1（\2）', text)
    text = html.escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<font color="#48576A">\1</font>', text)
    return text


def render_markdown(text: str, styles: dict[str, ParagraphStyle]) -> list[object]:
    flow: list[object] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith('```'):
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].startswith('```'):
                code.append(lines[index])
                index += 1
            flow.append(Paragraph('<br/>'.join(html.escape(x) or ' ' for x in code), styles['code']))
            index += 1
            continue
        if line.startswith('|'):
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith('|'):
                cells = lines[index].strip().strip('|').split('|')
                if not all(re.fullmatch(r'[:\s-]+', cell) for cell in cells):
                    rows.append([cell.strip() for cell in cells])
                index += 1
            ncol = max(len(row) for row in rows)
            widths = ([WIDTH * .25, WIDTH * .75] if ncol == 2 else [WIDTH / ncol] * ncol)
            table = Table([[Paragraph(inline(cell), styles['table']) for cell in row] for row in rows], colWidths=widths, repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8EEF5')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LINEBELOW', (0, 0), (-1, -1), .35, colors.HexColor('#CAD4DF')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            flow.extend([table, Spacer(1, 8)])
            continue
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            key = 'h1' if level <= 1 else 'h2' if level == 2 else 'h3'
            flow.append(Paragraph(inline(line.lstrip('#').strip()), styles[key]))
        elif re.fullmatch(r'[-*]{3,}', line):
            flow.append(Spacer(1, 9))
        else:
            key = 'quote' if line.startswith('> ') else 'body'
            if line.startswith('> '):
                line = line[2:]
            flow.append(Paragraph(inline(line), styles[key]))
        index += 1
    return flow


def footer(canvas: object, doc: object) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#D2DAE4'))
    canvas.line(44, 37, A4[0] - 44, 37)
    canvas.setFont('YaHei', 8)
    canvas.setFillColor(colors.HexColor('#65768A'))
    canvas.drawString(44, 24, 'Unity ASTC | 聊天记录与总结 | 2026-11-13')
    canvas.drawRightString(A4[0] - 44, 24, str(doc.page))
    canvas.restoreState()


def main() -> None:
    source = json.loads((WORK / 'visible-messages.json').read_text(encoding='utf-8'))
    transcriptions = json.loads((WORK / 'screenshot-transcriptions.json').read_text(encoding='utf-8'))
    OUT.mkdir(parents=True, exist_ok=True)
    PDF.parent.mkdir(parents=True, exist_ok=True)
    (OUT / 'images').mkdir(exist_ok=True)
    image_rows: list[dict[str, str]] = []
    for message in source['messages']:
        for item in message.get('content', []):
            if item['type'] == 'localImage':
                original = Path(item['path'])
                number = len(image_rows) + 1
                dest = OUT / 'images' / f'screenshot-{number:02}.png'
                shutil.copyfile(original, dest)
                assert hashlib.sha256(original.read_bytes()).digest() == hashlib.sha256(dest.read_bytes()).digest()
                image_rows.append({'original': str(original), 'path': str(dest), 'relative': f'images/screenshot-{number:02}.png'})

    intro = '\n\n'.join([
        '# Unity ASTC 聊天记录与总结',
        '2026-11-13 · 当前聊天“创建V2实验报告”',
        '本文件收录本次聊天的 9 条用户消息、7 条助手答复、10 条助手过程更新，以及 7 张截图。记录按先后顺序排列，截止于用户提出本次导出请求和助手的首次整理说明。`[verified: 聊天导出快照，hasMore=false；26条用户可见消息及7个图片附件]`',
        '历史答复及其中的引用按原文保留，表示当时的回答，不表示本次重新执行了实验或复核了全部技术结论。截图转录按气泡颜色区分说话方，重复截图保留。`[opinion]`',
        '阅读顺序：本次聊天原文 → 截图与讨论转录 → 最终六点总结。',
        '## 本次聊天原文',
    ])
    chunks: list[str] = [intro]
    image_index = 0
    preserved: list[dict[str, str]] = []
    for number, message in enumerate(source['messages'], 1):
        if message['role'] == 'user':
            label = '用户'
            texts = [clean_user(item['text']) for item in message['content'] if item['type'] == 'text']
            body = '\n\n'.join(part for part in texts if part)
            attachments: list[str] = []
            for item in message['content']:
                if item['type'] == 'localImage':
                    image_index += 1
                    attachments.append(f'截图 {image_index}')
            if attachments:
                body += '\n\n附件：' + '、'.join(attachments) + '，见“截图与讨论转录”。'
        else:
            label = '助手答复' if message['phase'] == 'final_answer' else '助手过程更新'
            body = message['text'].strip()
            preserved.append({'id': message['id'], 'body': body})
        chunks.append(f'### 消息 {number:02} · {label}\n\n{body.strip()}')
    chat_md = '\n\n'.join(chunks)
    summary = next(message['text'].strip() for message in reversed(source['messages']) if message.get('phase') == 'final_answer')
    summary_md = '\n\n'.join([
        '## 最终六点总结',
        '以下保留最后一次总结原文，其中“图1～图4”依次对应本文件截图4～截图7。`[verified: 最后一次用户总结请求附4张截图；其后助手答复]`',
        summary,
        '### 执行边界',
        '当前讨论明确了“先统计耗时、准确率优先”，未规定耗时硬门槛；直接使用未导入 Unity 的原图、移除 exhaustive 后是否提高准确率，仍需验证。特殊贴图的通道语义和专门误差规则暂缓细化。`[verified: 截图7“这个需要你评估下”“可能可以提高准确率”“准确率为优先”“那就先统计耗时”；截图6“目前不需要管这个”]`',
    ])
    screenshot_md = ['## 截图与讨论转录']
    for index, row in enumerate(image_rows, 1):
        screenshot_md.append(f"### 截图 {index}\n\n原附件：`{Path(row['original']).name}`\n\n![截图 {index}]({row['relative']})")
        transcript = transcriptions.get(str(index))
        if transcript:
            screenshot_md.append(transcript)
    all_md = chat_md + '\n\n' + '\n\n'.join(screenshot_md) + '\n\n' + summary_md + '\n'
    MD.write_text(all_md, encoding='utf-8')
    assert all(row['body'] in all_md for row in preserved)
    assert summary in all_md

    pdfmetrics.registerFont(TTFont('YaHei', 'C:/Windows/Fonts/msyh.ttc', subfontIndex=0))
    pdfmetrics.registerFont(TTFont('YaHeiBold', 'C:/Windows/Fonts/msyhbd.ttc', subfontIndex=0))
    pdfmetrics.registerFontFamily('YaHei', normal='YaHei', bold='YaHeiBold', italic='YaHei', boldItalic='YaHeiBold')
    base = ParagraphStyle('body', fontName='YaHei', fontSize=9.4, leading=15, wordWrap='CJK', splitLongWords=True, textColor=colors.HexColor('#203044'), spaceAfter=7)
    styles = {'body': base}
    styles['h1'] = ParagraphStyle('h1', parent=base, fontName='YaHeiBold', fontSize=21, leading=28, spaceAfter=16)
    styles['h2'] = ParagraphStyle('h2', parent=base, fontName='YaHeiBold', fontSize=15, leading=22, spaceBefore=15, spaceAfter=12, keepWithNext=True)
    styles['h3'] = ParagraphStyle('h3', parent=base, fontName='YaHeiBold', fontSize=10.8, leading=17, spaceBefore=13, spaceAfter=7, keepWithNext=True, textColor=colors.HexColor('#245880'))
    styles['table'] = ParagraphStyle('table', parent=base, fontSize=8.3, leading=12.8, spaceAfter=0)
    styles['code'] = ParagraphStyle('code', parent=base, fontSize=8.4, leading=13, backColor=colors.HexColor('#F1F4F8'), borderPadding=7, spaceBefore=5, spaceAfter=10)
    styles['quote'] = ParagraphStyle('quote', parent=base, leftIndent=10, borderColor=colors.HexColor('#C8D6E5'), borderWidth=.5, borderPadding=6)
    styles['caption'] = ParagraphStyle('caption', parent=base, fontSize=8, leading=11, alignment=TA_CENTER)
    story = render_markdown(chat_md, styles)
    for index, row in enumerate(image_rows, 1):
        story.append(PageBreak())
        heading = '截图与讨论转录 · 截图 ' + str(index)
        story.append(Paragraph(heading, styles['h2']))
        with PILImage.open(row['path']) as source_image:
            width, height = source_image.size
        scale = min(WIDTH / width, 645 / height, 1.0)
        story.append(Image(row['path'], width=width * scale, height=height * scale))
        story.append(Spacer(1, 9))
        story.append(Paragraph(html.escape(Path(row['original']).name), styles['caption']))
        transcript = transcriptions.get(str(index))
        if transcript:
            story.extend(render_markdown(transcript, styles))
    story.append(PageBreak())
    story.extend(render_markdown(summary_md, styles))
    doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=44, rightMargin=44, topMargin=40, bottomMargin=49, title='Unity ASTC 聊天记录与总结', author='Codex')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    reader = PdfReader(str(PDF))
    texts = [page.extract_text() or '' for page in reader.pages]
    assert all(text.strip() for text in texts)
    combined = re.sub(r'\s+', '', '\n'.join(texts))
    for keyword in ['不需要完善报告，给我回答即可', '86.9%', '93.6%', 'unity_astc_quality.dll', '最终六点总结', '那就先统计耗时']:
        assert keyword in combined, keyword
    (WORK / 'extracted.txt').write_text('\n\n'.join(texts), encoding='utf-8')
    rendered = pdfium.PdfDocument(str(PDF))
    page_paths: list[Path] = []
    for index in range(len(rendered)):
        bitmap = rendered[index].render(scale=1.15)
        dest = WORK / f'page-{index + 1:02}.png'
        bitmap.to_pil().save(dest)
        page_paths.append(dest)
    for start in range(0, len(page_paths), 9):
        group = page_paths[start:start + 9]
        sheet = PILImage.new('RGB', (1080, 1560), '#DCE3EB')
        draw = ImageDraw.Draw(sheet)
        for offset, path in enumerate(group):
            with PILImage.open(path) as page:
                page.thumbnail((345, 490))
                x, y = (offset % 3) * 360 + 7, (offset // 3) * 520 + 24
                sheet.paste(page, (x, y))
                draw.text((x, y - 18), f'Page {start + offset + 1}', fill='black')
        sheet.save(WORK / f'contact-{start // 9 + 1}.png')
    receipt = {
        'status': 'content_checks_passed_visual_pending',
        'chat_title': source['thread']['title'],
        'complete_history_received': source['completeHistory'],
        'visible_messages': len(source['messages']),
        'user_messages': sum(x['role'] == 'user' for x in source['messages']),
        'assistant_answers': sum(x.get('phase') == 'final_answer' for x in source['messages']),
        'assistant_updates': sum(x.get('phase') == 'commentary' for x in source['messages']),
        'assistant_bodies_preserved': len(preserved),
        'screenshots_verified_by_sha256': len(image_rows),
        'screenshots_transcribed': len(transcriptions),
        'summary_verbatim_preserved': True,
        'pages': len(reader.pages),
        'pdf': str(PDF),
        'markdown': str(MD),
        'pdf_sha256': hashlib.sha256(PDF.read_bytes()).hexdigest(),
        'markdown_sha256': hashlib.sha256(MD.read_bytes()).hexdigest(),
    }
    (WORK / 'verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
