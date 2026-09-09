# -*- coding: utf-8 -*-
"""
占位符替换：docs/prompts_template.md + local_tokens.json → build/prompts_personalized.md
用法：python setup/apply_tokens.py
"""
import json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(REPO, 'docs', 'prompts_template.md')
TOKENS = os.path.join(REPO, 'local_tokens.json')
OUT_DIR = os.path.join(REPO, 'build')
OUT = os.path.join(OUT_DIR, 'prompts_personalized.md')


def main():
    if not os.path.isfile(TOKENS):
        sys.exit('❌ 未找到 local_tokens.json，请先运行 python setup/onboard.py')
    text = open(TEMPLATE, encoding='utf-8').read()
    tokens = json.load(open(TOKENS, encoding='utf-8'))

    # 长 token 优先，避免 {{ROOT}} 先于 {{ROOT_JS}} 被替换
    for k in sorted(tokens, key=len, reverse=True):
        text = text.replace(k, str(tokens[k]))

    leftover = sorted(set(re.findall(r'\{\{[A-Z_]+\}\}', text)))
    os.makedirs(OUT_DIR, exist_ok=True)
    open(OUT, 'w', encoding='utf-8').write(text)
    print(f'✅ 已生成: {OUT}')
    if leftover:
        print(f'⚠️  仍有 {len(leftover)} 个占位符未替换: {", ".join(leftover)}')
        print('   请在 local_tokens.json 中补齐后重跑本脚本。')


if __name__ == '__main__':
    main()
