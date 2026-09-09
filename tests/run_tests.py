# -*- coding: utf-8 -*-
"""
测试运行器：用 5 个虚构候选人 fixture 端到端验证「画像创建」流程。
  TC1 完整档案        → 期望通过
  TC2 日本签证方向    → 期望通过
  TC3 最小档案（选填全空）→ 期望通过
  TC4 非法字段        → 期望失败（degree_level/届次/技能归一化/地点/japan_rule）
  TC5 简历换了但 hash 未更新 → 期望失败（哈希不匹配）
用法：python tests/run_tests.py
"""
import json, os, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'setup'))
import onboard
from validate_profile import validate

DUMMY = os.path.join(REPO, 'tests', 'assets', 'dummy_resume.pdf')
FIX = os.path.join(REPO, 'tests', 'fixtures')
TAX = os.path.join(REPO, 'contracts', 'taxonomy.json')

CASES = [
    ('tc1_full.json', True, '完整档案'),
    ('tc2_japan.json', True, '日本签证方向'),
    ('tc3_minimal.json', True, '最小档案（选填全空）'),
    ('tc4_invalid.json', False, '非法字段'),
    ('tc5_stale_hash.json', False, '简历已更换但画像 hash 过期'),
]


def main():
    if not os.path.isfile(DUMMY):
        with open(DUMMY, 'wb') as f:
            f.write(b'%PDF-1.4 dummy resume for tests\n')

    passed = failed = 0
    for fn, expect_pass, desc in CASES:
        answers = json.load(open(os.path.join(FIX, fn), encoding='utf-8'))
        simulate = answers.pop('_simulate', None)
        answers['resume_pdf'] = DUMMY

        try:
            profile, tokens = onboard.collect(answers)
        except SystemExit as e:
            errors = [f'onboard 收集阶段拒绝: {e}']
        else:
            if simulate == 'stale_hash':
                profile['resume_source']['sha256'] = '0' * 64  # 模拟简历换了但画像没重建
            tmp = os.path.join(tempfile.gettempdir(), 'tc_profile.json')
            json.dump(profile, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
            errors, _ = validate(tmp, TAX)

        ok = (not errors) == expect_pass
        status = '✅ 符合预期' if ok else '❌ 不符合预期'
        expect_str = '应通过' if expect_pass else '应拒绝'
        print(f'{fn:<24} {desc:<28} 期望:{expect_str} → {status}')
        if errors and not expect_pass:
            for e in errors:
                print(f'    拦截原因: {e}')
        passed += ok
        failed += (not ok)

    print(f'\n结果: {passed} 通过 / {failed} 失败')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
