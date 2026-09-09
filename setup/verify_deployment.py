# -*- coding: utf-8 -*-
"""
部署验证器：回答"定时任务真的建好了吗"。

校验内容：
  A. 本地产物：画像存在且契约校验通过、token 表存在、个人版 prompt 零残留占位符；
  B. 调度器任务：自动探测 WorkBuddy 数据库（~/.workbuddy/workbuddy.db），
     检查 5 个阶段的 ACTIVE 定时任务是否存在、rrule 是否为预期的每日时间。

用法：
  python setup/verify_deployment.py [--db <workbuddy.db 路径>]
退出码：0=全部通过；1=有失败项；2=无法验证调度器（非 WorkBuddy 环境，转人工清单）。
"""
import json, os, re, sqlite3, sys, argparse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 每个阶段的识别签名（prompt 中稳定存在的子串）与期望调度
STAGES = [
    ('搜索', ['跨国初级岗位猎手'], 6, 0),
    ('筛选', ['投递队列筛选'], 11, 37),
    ('预检', ['投递前登录检查', 'platform_login_status'], 12, 30),
    ('投递', ['Phase 0', '预检消费'], 13, 0),
    ('通知', ['job-delivery-notify'], 15, 0),
]


def check_local_artifacts():
    errs = []
    prof = os.path.join(REPO, 'contracts', 'candidate_profile.json')
    toks = os.path.join(REPO, 'local_tokens.json')
    build = os.path.join(REPO, 'build', 'prompts_personalized.md')

    if not os.path.isfile(prof):
        errs.append('缺少 contracts/candidate_profile.json（先跑 setup/onboard.py）')
    else:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from validate_profile import validate
        e, _ = validate(prof, os.path.join(REPO, 'contracts', 'taxonomy.json'))
        errs += [f'画像校验: {x}' for x in e]

    if not os.path.isfile(toks):
        errs.append('缺少 local_tokens.json（先跑 setup/onboard.py）')

    if not os.path.isfile(build):
        errs.append('缺少 build/prompts_personalized.md（先跑 setup/apply_tokens.py）')
    else:
        left = set(re.findall(r'\{\{[A-Z_]+\}\}', open(build, encoding='utf-8').read()))
        if left:
            errs.append(f'个人版 prompt 残留占位符: {sorted(left)}（重跑 setup/apply_tokens.py）')
    return errs


def check_workbuddy(db_path):
    if not os.path.isfile(db_path):
        return None, None
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT id, name, prompt, status, rrule FROM automations "
        "WHERE deleted_at IS NULL AND status='ACTIVE'").fetchall()
    con.close()
    return rows, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=os.path.expanduser(r'~\.workbuddy\workbuddy.db'))
    a = ap.parse_args()

    print('== A. 本地产物检查 ==')
    errs = check_local_artifacts()
    if errs:
        for e in errs:
            print('  ❌', e)
    else:
        print('  ✅ 画像 / token 表 / 个人版 prompt 全部就绪且校验通过')

    print('\n== B. 调度器任务检查（WorkBuddy）==')
    rows, _ = check_workbuddy(a.db)
    if rows is None:
        print(f'  ⚠️  未找到 WorkBuddy 数据库（{a.db}），无法自动验证。')
        print('  请人工确认调度器中已创建以下 5 个每日任务：')
        for name, _, h, m in STAGES:
            print(f'    - {name}: 每天 {h:02d}:{m:02d}')
        print('\n结果: 本地产物 %s；调度器需人工核对' % ('✅' if not errs else '❌'))
        sys.exit(2 if not errs else 1)

    failed = False
    for name, sigs, hh, mm in STAGES:
        hit = None
        for rid, rname, prompt, status, rrule in rows:
            text = f'{rname}\n{prompt or ""}'
            if all(s in text for s in sigs):
                hit = (rid, rname, rrule)
                break
        if not hit:
            print(f'  ❌ {name}: 未找到 ACTIVE 任务（签名: {sigs}）')
            failed = True
            continue
        rid, rname, rrule = hit
        expect = f'FREQ=DAILY;BYHOUR={hh};BYMINUTE={mm}'
        if rrule and 'FREQ=DAILY' in rrule and f'BYHOUR={hh}' in rrule and f'BYMINUTE={mm}' in rrule:
            print(f'  ✅ {name}: {rname} ({rid}) @ {rrule}')
        else:
            print(f'  ⚠️  {name}: 任务存在但调度不符预期（期望 {expect}，实际 {rrule}）')
            failed = True

    print('\n结果: 本地产物 %s；定时任务 %s' % (
        '✅' if not errs else '❌', '✅ 5/5' if not failed else '❌ 有缺失/时间错误'))
    sys.exit(0 if not errs and not failed else 1)


if __name__ == '__main__':
    main()
