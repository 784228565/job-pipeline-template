# -*- coding: utf-8 -*-
"""
画像校验器：按 docs/prompts_template.md 附B「新用户接入契约」规则校验 candidate_profile.json。
用法：
  python setup/validate_profile.py <profile.json> [--taxonomy contracts/taxonomy.json] [--no-file-check]
退出码：0=通过，1=失败。
"""
import json, re, sys, os, hashlib, argparse


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def validate(profile_path, taxonomy_path=None, check_file=True):
    errors, warnings = [], []

    # 0. JSON 可解析
    try:
        with open(profile_path, encoding='utf-8') as f:
            p = json.load(f)
    except Exception as e:
        return [f'JSON 解析失败: {e}'], warnings

    # 1. schema_version
    if p.get('schema_version') != '1.0':
        errors.append('schema_version 缺失或不等于 "1.0"')

    # 2. resume_source
    rs = p.get('resume_source') or {}
    rfile = rs.get('file', '')
    rhash = rs.get('sha256', '')
    if check_file:
        if not rfile or not os.path.isfile(rfile):
            errors.append(f'resume_source.file 不存在或不可读: {rfile!r}')
        elif not re.fullmatch(r'[0-9a-f]{64}', rhash or ''):
            errors.append('resume_source.sha256 不是 64 位小写十六进制')
        else:
            actual = sha256_of(rfile)
            if actual != rhash:
                errors.append(f'简历哈希不匹配: 文件实际={actual[:12]}… profile 记录={rhash[:12]}…（换了简历必须重建画像）')
    else:
        if not re.fullmatch(r'[0-9a-f]{64}', rhash or ''):
            errors.append('resume_source.sha256 不是 64 位小写十六进制')

    # 3. identity
    ident = p.get('identity') or {}
    name_cn, name_en = ident.get('name_cn', ''), ident.get('name_en', '')
    if not name_cn.strip():
        errors.append('identity.name_cn 为空')
    if not name_en.strip():
        errors.append('identity.name_en 为空')
    elif len(name_en.split()) < 2:
        errors.append('identity.name_en 需为 "名 姓" 两段式（登录检测正则要用）')
    phone = ident.get('phone', '')
    if phone and not re.fullmatch(r'1[3-9]\d{9}', str(phone)):
        errors.append(f'identity.phone 格式不正确（需大陆 11 位手机号）: {phone!r}')
    if not ident.get('email'):
        errors.append('identity.email 为空')
    elif not re.fullmatch(r'[\w.+-]+@[\w-]+\.[\w.]+', str(ident['email'])):
        errors.append(f'identity.email 格式不正确: {ident["email"]!r}')

    # 4. education
    edu = p.get('education') or []
    if not edu:
        errors.append('education 至少需要 1 条')
    for i, e in enumerate(edu):
        if e.get('degree_level') not in (1, 2, 3):
            errors.append(f'education[{i}].degree_level 必须是 1/2/3（本科/硕士/博士）')
        if not str(e.get('status', '')).strip():
            errors.append(f'education[{i}].status 为空')

    # 5. graduation_identity
    gi = p.get('graduation_identity') or {}
    canon = gi.get('canonical', '')
    if not re.search(r'20\d\d\s*届', canon):
        errors.append('graduation_identity.canonical 必须包含届次年份（如 "2026届"）')
    if not str(gi.get('social_insurance', '')).strip():
        errors.append('graduation_identity.social_insurance 为空（应届认定关键项：填 "从未缴纳" 或 "缴纳过"）')

    # 5b. 工作年限与地点
    hc0 = p.get('hard_constraints') or {}
    ye = hc0.get('years_of_experience')
    if ye is not None and (not isinstance(ye, int) or ye < 0):
        errors.append('hard_constraints.years_of_experience 必须是非负整数')

    # 5c. 链接格式（选填，但填了就必须合法）
    for k, u in ((p.get('links') or {}).items()):
        if u and not re.fullmatch(r'https?://\S+', str(u)):
            errors.append(f'links.{k} 格式不正确（需以 http(s):// 开头）: {u!r}')

    # 6. skills + taxonomy 归一化
    skills = p.get('skills_canonical') or []
    if len(skills) < 3:
        errors.append('skills_canonical 至少需要 3 条')
    if taxonomy_path and os.path.isfile(taxonomy_path):
        tax = json.load(open(taxonomy_path, encoding='utf-8'))
        syn = tax.get('skill_synonyms') or {}
        known = set(syn.keys()) | {a.lower() for vs in syn.values() for a in vs}
        for s in skills:
            if s not in syn and s.lower() not in known:
                errors.append(f'技能 "{s}" 无法被 taxonomy.json 归一化（请先补录 skill_synonyms）')
        # 7. locations
        loc_canon = tax.get('location_canonical') or {}
        known_loc = set(loc_canon.keys()) | {a for vs in loc_canon.values() for a in vs}
    else:
        known_loc = None
        if taxonomy_path:
            warnings.append(f'taxonomy 未找到({taxonomy_path})，跳过技能/地点归一化校验')

    hc = p.get('hard_constraints') or {}
    locs = hc.get('target_locations') or []
    if not locs:
        errors.append('hard_constraints.target_locations 至少需要 1 个')
    elif known_loc is not None:
        for loc in locs:
            if loc not in known_loc:
                errors.append(f'目标地点 "{loc}" 不在 taxonomy.json 的 location_canonical 中')

    if not str(hc.get('overseas_rule', '')).strip():
        errors.append('hard_constraints.overseas_rule 为空（无海外需求时填 "无海外方向需求"）')
    if not str(hc.get('company_origin_rule', '')).strip():
        errors.append('hard_constraints.company_origin_rule 为空（如 "美/欧/中大型企业，排除日企韩企"）')

    # 8. 选填字段类型提示
    for opt in ('experience', 'publications', 'languages', 'directions'):
        if opt in p and not isinstance(p[opt], list):
            errors.append(f'选填字段 {opt} 必须是数组（可空数组）')

    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('profile')
    ap.add_argument('--taxonomy', default=None)
    ap.add_argument('--no-file-check', action='store_true', help='跳过简历文件存在性与哈希校验（CI 用）')
    a = ap.parse_args()
    errors, warnings = validate(a.profile, a.taxonomy, check_file=not a.no_file_check)
    for w in warnings:
        print('⚠️ ', w)
    if errors:
        print(f'❌ 校验失败（{len(errors)} 项）:')
        for e in errors:
            print('  -', e)
        sys.exit(1)
    print('✅ 画像校验通过:', a.profile)
    sys.exit(0)


if __name__ == '__main__':
    main()
