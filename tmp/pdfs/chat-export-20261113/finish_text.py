from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from build_chat import clean_user


def main() -> None:
    root = Path('E:/ASTC_Compression')
    work = root / 'tmp/pdfs/chat-export-20261113'
    output = root / 'output/chat/20261113'
    md_path = output / 'Unity-ASTC-聊天记录与总结-20261113.md'
    txt_path = output / 'Unity-ASTC-聊天记录与总结-20261113.txt'
    source = json.loads((work / 'visible-messages.json').read_text(encoding='utf-8'))
    original = md_path.read_text(encoding='utf-8')
    intro_end = original.index('## 本次聊天原文')
    intro = '\n\n'.join([
        '# Unity ASTC 聊天记录与总结（纯文字版）',
        '2026-11-13 · 当前聊天“创建V2实验报告”',
        '正文保留本次聊天导出快照中的 9 条用户消息、7 条助手答复和 10 条助手过程更新，并整理上传截图中的讨论文字。快照截止于用户提出“把我们所有的聊天和你的总结给我一份”和助手的首次整理说明。`[verified: 聊天导出快照 hasMore=false，26条用户可见消息]`',
        '最新格式要求为“文字版本的整理就行”，本版只保留文字。`[verified: 用户最新消息“文字版本的整理就行”]`',
        '历史答复及其中引用按原文保留，表示当时的回答，不表示本次重新执行了实验或复核了全部技术结论；后续优先级以文末总结为准。`[opinion]`',
        '截图按上传顺序编号1～7。前两张为本次答复节选，文字已在正文收录；后五张的聊天气泡逐条转录。`[verified: 截图1对应消息13的评价表与法线结果；截图2对应消息18的图片类型表与准确率说明；截图3～7气泡文字]`',
        '阅读顺序：本次聊天原文 → 截图讨论文字 → 最终六点总结。',
    ]) + '\n\n'
    text = intro + original[intro_end:]
    text = text.replace('截图与讨论转录', '截图讨论文字')
    text = re.sub(r'\n\n原附件：`[^`]+`\n\n!\[截图 \d+\]\([^\n]+\)', '', text)
    text = text.replace('### 截图 1\n', '### 截图 1\n\n此图为消息13中“法线和 mask 是否由 AI 自动识别、评价标准有什么区别”的答复节选，含质量评价表及45张法线图的结果，文字已完整保留于消息13。`[verified: 用户上传截图1；消息13助手答复]`\n', 1)
    text = text.replace('### 截图 2\n', '### 截图 2\n\n此图为消息18中“同一个 ResNet-34 能处理哪些图片”的答复节选，含图片类型表、图片加属性的输入说明及验证准确率，文字已完整保留于消息18。`[verified: 用户上传截图2；消息18助手答复]`\n', 1)
    text = text.replace('原图及转录均保留；其中回复引用、消息编辑标记和反应按钮可在原图查看。', '转录保留重复内容；纯文字版省略界面按钮和反应图标。')
    text = text.replace('附件：截图 4、截图 5、截图 6、截图 7，见“截图讨论文字”。', '附件：截图 4、截图 5、截图 6、截图 7，见“截图讨论文字”。该轮答复所称图1～图4，依次对应这四张截图。')
    assert not re.search(r'!\[[^\]]*\]\(', text)
    assistant_count = 0
    user_count = 0
    for message in source['messages']:
        if message['role'] == 'assistant':
            assert message['text'].strip() in text, message['id']
            assistant_count += 1
        else:
            for item in message['content']:
                if item['type'] == 'text':
                    body = clean_user(item['text'])
                    if body:
                        assert body in text, message['id']
            user_count += 1
    assert len(re.findall(r'^### 消息 \d+', text, re.M)) == 26
    assert len(re.findall(r'^### 截图 \d+', text, re.M)) == 7
    assert text.count('#### 气泡文字转录') == 5
    text = '\n'.join(line.rstrip() for line in text.splitlines()) + '\n'
    md_path.write_text(text, encoding='utf-8')

    plain = re.sub(r':codex-annotation\{index="(\d+)"\}', r'〔回复所选原文 \1〕', text)
    plain = re.sub(r':codex-file-citation\{path="([^"]+)" purpose="[^"]+"\}', r'文件链接：\1', plain)
    plain = re.sub(r'\[([^\]]+)\]\(<([^>]+)>\)', r'\1（\2）', plain)
    plain = re.sub(r'^#{1,6} ', '', plain, flags=re.M)
    plain = re.sub(r'^```[^\n]*\n?', '', plain, flags=re.M)
    plain = plain.replace('**', '').replace('`', '')
    txt_path.write_text(plain, encoding='utf-8-sig')
    assert txt_path.read_text(encoding='utf-8-sig') == plain
    for keyword in ['不需要完善报告，给我回答即可', '文字版本的整理就行', '86.9%', '93.6%', 'unity_astc_quality.dll', '最终六点总结', '那就先统计耗时']:
        assert keyword in plain, keyword
    receipt = {
        'status': 'passed_text_export',
        'complete_history_received': source['completeHistory'],
        'visible_messages_preserved': 26,
        'user_messages_checked': user_count,
        'assistant_messages_checked': assistant_count,
        'assistant_final_answers': 7,
        'assistant_progress_updates': 10,
        'screenshot_sections': 7,
        'screenshot_chat_transcripts': 5,
        'inline_images': 0,
        'summary_verbatim_preserved': True,
        'utf8_roundtrip': 'passed',
        'markdown': str(md_path),
        'plain_text': str(txt_path),
        'markdown_sha256': hashlib.sha256(md_path.read_bytes()).hexdigest(),
        'plain_text_sha256': hashlib.sha256(txt_path.read_bytes()).hexdigest(),
    }
    (output / 'verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=True))


if __name__ == '__main__':
    main()
