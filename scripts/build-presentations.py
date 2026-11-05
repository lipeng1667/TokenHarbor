#!/usr/bin/env python3
"""Assemble editable HTML text and original presentation artwork into offline pages."""
from pathlib import Path
from html import escape
from html.parser import HTMLParser
import base64
import mimetypes
import re

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'docs/presentation-source'

class ChapterIndex(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chapters = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section' and 'chapter' in attrs.get('class', '').split():
            self.chapters.append((attrs['id'], attrs['data-title']))

def embed_media(content):
    """Keep editable source paths; package original artwork for single-file delivery."""
    media_root = (SRC / 'media').resolve()
    def replace(match):
        relative = match.group(1)
        path = (SRC / relative).resolve()
        assert path.is_relative_to(media_root), relative
        assert path.is_file(), f'Missing presentation artwork: {relative}'
        mime = mimetypes.guess_type(path.name)[0]
        assert mime in ('image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'), relative
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        return f'src="data:{mime};base64,{encoded}" data-source="{escape(relative)}"'
    return re.sub(r'src="(media/[^"<>]+)"', replace, content)

def build(filename, include_platform):
    content = (SRC / 'team-sections.html').read_text()
    if include_platform:
        content += '\n' + (SRC / 'platform-sections.html').read_text()
    parser = ChapterIndex()
    parser.feed(content)
    expected = 17 if include_platform else 7
    assert [i for i, _ in parser.chapters] == [f'slide-{i}' for i in range(1, expected + 1)]
    assert not re.search(r'<(?:canvas|iframe)\b|data:image|小悟', content)
    content = embed_media(content)
    toc = []
    for i, (anchor, title) in enumerate(parser.chapters, 1):
        if i in (1, 8):
            toc.append('<li class="toc-group">' + ('团队技术背景' if i == 1 else 'TokenHarbor 产品与技术规划') + '</li>')
        toc.append(f'<li><a href="#{anchor}"><span>{i:02}</span>{escape(title)}</a></li>')
    title = '团队技术背景与 TokenHarbor 规划' if include_platform else '团队技术背景与工程能力'
    heading = '团队技术背景<br><span>与 AI 服务规划</span>' if include_platform else '团队技术背景<br><span>与工程能力</span>'
    intro = ('围绕能力开放、数据处理与可靠交付，展示团队既往技术经验，以及 TokenHarbor 的产品与技术方向。' if include_platform else '梳理通信网关、身份校验、数据服务与高可用系统的核心设计，展示业务系统背后的工程思路。')
    secondary = '<a class="text-link" href="#slide-8">了解 TokenHarbor</a>' if include_platform else '<a class="text-link" href="#slide-6">查看架构设计</a>'
    platform_nav = '<a class="nav-platform" href="#slide-8">TokenHarbor</a>' if include_platform else ''
    final_anchor = 'slide-17' if include_platform else 'slide-7'
    footer_text = ('团队历史项目与 TokenHarbor 产品技术规划。' if include_platform else '团队历史项目与系统工程经验。')
    css = (SRC / 'viewer.css').read_text()
    if include_platform:
        css += '\n' + (SRC / 'platform-visuals.css').read_text()
    js = (SRC / 'viewer.js').read_text()
    output = f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="申行科技企业交流资料。{escape(intro)}">
<meta name="theme-color" content="#f6f7f4">
<title>申行科技｜{escape(title)}</title>
<style>{css}</style>
</head>
<body id="top">
<a class="skip-link" href="#content">跳转正文</a>
<header class="masthead"><div class="wrap masthead-inner">
<a class="wordmark" href="#top" aria-label="申行科技 返回页首">申行科技</a><span class="brand-context">企业技术交流<br>能力与架构</span>
<nav class="nav" aria-label="主要导航"><a href="#slide-1">团队背景</a><a class="nav-architecture" href="#slide-6">架构设计</a>{platform_nav}<details class="contents"><summary>目录</summary><div class="toc-panel"><p class="toc-label">{escape(title)}</p><ol class="toc">{''.join(toc)}</ol></div></details><button class="print-button" type="button" aria-label="打印完整页面">打印</button></nav>
</div></header>
<section class="cover" aria-labelledby="page-title"><div class="wrap">
<div class="cover-meta"><p class="eyebrow">申行科技 企业技术交流</p><span>技术背景 / 架构 / 产品方向</span></div>
<div class="cover-grid"><div><h1 id="page-title">{heading}</h1></div><div><p class="cover-intro">{intro}</p><div class="cover-actions"><a class="primary-link" href="#slide-1">了解团队技术背景 <span aria-hidden="true">↓</span></a>{secondary}</div></div></div>
<div class="pathway"><div class="pathway-top"><span>围绕业务运行的四个环节</span><span>系统工程视角</span></div><div class="pathway-flow">
<div class="path-step"><span class="path-number">01</span><h2>能力接入</h2><p>整理接口与协议差异</p></div><div class="path-step"><span class="path-number">02</span><h2>业务调度</h2><p>明确规则与处理职责</p></div><div class="path-step"><span class="path-number">03</span><h2>用量计量</h2><p>记录可核查的业务证据</p></div><div class="path-step"><span class="path-number">04</span><h2>可靠交付</h2><p>管理状态与异常恢复</p></div>
</div></div><p class="cover-foot">通信系统经验　 /　 数据工程　 /　 平台化设计{'　 /　 AI 服务规划' if include_platform else ''}</p>
</div></section>
<main id="content">{content}</main>
<footer class="page-footer"><div class="wrap"><div class="footer-top"><div><h2>申行科技</h2><p>{footer_text}</p></div><a href="#{final_anchor}">{'回顾实施路径' if include_platform else '回顾系统工程设计'} <span aria-hidden="true">↗</span></a></div><div class="footer-bottom"><span>企业技术交流资料</span><span>团队经验与产品规划分别说明</span></div></div></footer>
<a class="back-top" href="#top" aria-label="返回页首">↑</a>
<script>{js}</script>
</body></html>
'''
    target = ROOT / 'docs' / filename
    target.write_text(output)
    print(f'{target.relative_to(ROOT)}: {expected} native HTML sections, {target.stat().st_size:,} bytes')

build('team-background.html', False)
build('tokenharbor-presentation.html', True)
