# -*- coding: utf-8 -*-
"""
新用户引导工具（onboarding wizard）。
交互式收集个人信息 + 简历 PDF，生成并校验：
  1. contracts/candidate_profile.json   —— 筛选画像 IR（真实数据，被 .gitignore 排除）
  2. local_tokens.json                  —— prompt 模板占位符替换表（真实数据，被 .gitignore 排除）
随后运行 setup/apply_tokens.py 即可生成个人版 prompt 文档。

用法：
  python setup/onboard.py                     # 交互式
  python setup/onboard.py --answers a.json    # 从答案文件读取（测试/自动化用）
"""
import json, os, re, sys, hashlib, argparse, datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ask(q, default=None, required=True):
    while True:
        suffix = f' [{default}]' if default is not None else ''
        v = input(f'{q}{suffix}: ').strip()
        if not v and default is not None:
            return default
        if v or not required:
            return v
        print('  （必填，请重新输入）')


def ask_list(q, hint='逗号分隔'):
    v = ask(f'{q}（{hint}）', required=False)
    return [x.strip() for x in re.split(r'[,，]', v) if x.strip()]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def collect(a=None):
    """a 为 None 时交互式提问；否则从 dict 取答案。"""
    g = (lambda k, q, d=None, r=True: a.get(k, d) if a is not None else ask(q, d, r))
    gl = (lambda k, q: a.get(k, []) if a is not None else ask_list(q))

    print('=== 基础信息 ===')
    name_cn = g('name_cn', '中文名')
    name_en = g('name_en', '英文名（名 姓，如 Shili Zhang）')
    email = g('email', '通知/投递用邮箱')
    if not re.fullmatch(r'[\w.+-]+@[\w-]+\.[\w.]+', email or ''):
        raise SystemExit(f'❌ 邮箱格式不正确: {email!r}')
    phone = g('phone', '手机号（中国大陆 11 位，如 13812345678）')
    if not re.fullmatch(r'1[3-9]\d{9}', phone or ''):
        raise SystemExit(f'❌ 手机号格式不正确（需大陆 11 位手机号）: {phone!r}')
    citizenship = g('citizenship', '国籍/身份', '中国公民')
    current_location = g('current_location', '现居城市（填表与地点闸门用）', '上海')
    available_start = g('available_start', '可到岗时间（如 随时 / 2026-10-01）', '随时')

    print('=== 简历文件 ===')
    while True:
        resume = g('resume_pdf', '简历 PDF 完整路径')
        if a is not None or os.path.isfile(resume):
            break
        print('  文件不存在，请重新输入')
    rhash = sha256_of(resume) if os.path.isfile(resume) else '0' * 64

    print('=== 教育经历（至少 1 条）===')
    edu = g('education', None, r=False)
    if edu is None:
        edu = []
        while True:
            print(f'-- 第 {len(edu)+1} 条（学校留空结束）--')
            school = ask('学校', required=False)
            if not school:
                break
            lv = ask('学历：1=本科 2=硕士 3=博士')
            edu.append({
                'degree_level': int(lv), 'degree': {'1': '本科', '2': '硕士', '3': '博士'}[lv],
                'school': school,
                'field': ask('专业方向'),
                'period': ask('起止（如 2021-2024）'),
                'status': ask('状态（已毕业/在读/肄业）'),
            })
    if not edu:
        raise SystemExit('❌ 教育经历不能为空')

    print('=== 届次身份 ===')
    canon = g('graduation_identity',
              '届次身份一句话（必须含"20XX届"，如 "2026届应届（毕业2年内、未缴社保）"）')
    social_insurance = g('social_insurance', '是否缴纳过社保（从未缴纳/缴纳过，影响应届认定）', '从未缴纳')

    print('=== 技能与方向 ===')
    skills = g('skills', None, r=False)
    if skills is None:
        skills = ask_list('核心技能（至少 3 个，英文 canonical 名，如 Python, SQL, Deep Learning）')
    industries = gl('industries', '目标行业（如 农业科技, 数据分析服务, 外企500强）')
    directions = gl('directions', '求职方向/岗位类型（如 数据分析, 机器学习）')

    print('=== 地点与签证 ===')
    locations = gl('target_locations', '目标城市（如 上海, 东京）')
    years_exp = int(g('years_of_experience', '正式工作年限（用于排除超出你年限的社招岗，0=应届无经验）', '0'))
    company_origins = g('company_origins', '目标公司国籍规则（如 "美/欧/中大型企业，排除日企韩企"）', '美/欧/中大型企业，排除日企韩企')
    overseas_rule = g('overseas_rule', '是否考虑海外岗位？（不考虑填"无海外方向需求"；考虑则写明国家/地区与签证需求，如 "新加坡：需雇主担保 EP 签证"）', '无海外方向需求')
    china_auth = g('china_auth', '本国工作许可说明', '中国公民，无需担保')
    overseas_auth = g('overseas_auth', '海外工作许可说明', '需雇主担保当地工作签证' if '无海外' not in overseas_rule else '不适用')

    print('=== 选填（可直接回车跳过）===')
    languages = gl('languages', '语言（如 中文:native, 英语:IELTS 6.0）')
    publications = gl('publications', '论文（如 一作 EI：XXX 2025）')
    github_url = g('github_url', 'GitHub 地址（选填）', '', r=False)
    portfolio_url = g('portfolio_url', '作品集地址（选填）', '', r=False)
    linkedin_url = g('linkedin_url', 'LinkedIn 地址（选填）', '', r=False)
    salary_note = g('salary_note', '期望薪资口径（选填，如 "实习薪资可谈"）', '', r=False)
    for label, u in (('GitHub', github_url), ('作品集', portfolio_url), ('LinkedIn', linkedin_url)):
        if u and not re.fullmatch(r'https?://\S+', u):
            raise SystemExit(f'❌ {label} 地址格式不正确（需以 http(s):// 开头）: {u!r}')

    profile = {
        'schema_version': '1.0',
        'purpose': '筛选 Agent 的候选人画像契约（CandidateProfile IR）。',
        'resume_source': {
            'file': os.path.abspath(resume),
            'sha256': rhash,
            'parsed_at': datetime.date.today().isoformat(),
            'rule': '简历文件变更后须重新运行 onboard.py 重建本文件。',
        },
        'identity': {
            'name_cn': name_cn, 'name_en': name_en,
            'phone': phone, 'email': email,
            'citizenship': citizenship,
            'current_location': current_location,
            'home_work_auth': china_auth, 'overseas_work_auth': overseas_auth,
        },
        'education': edu,
        'graduation_identity': {'canonical': canon, 'social_insurance': social_insurance},
        'availability': {'start': available_start, 'notice_period': 'None' if available_start == '随时' else '按约定'},
        'links': {'github': github_url, 'portfolio': portfolio_url, 'linkedin': linkedin_url},
        'compensation': {'note': salary_note},
        'skills_canonical': skills,
        'languages': [{'lang': x.split(':')[0], 'level': x.split(':')[1]} if ':' in x else {'lang': x, 'level': ''} for x in languages],
        'publications': publications,
        'hard_constraints': {
            'target_locations': locations,
            'target_industries': industries,
            'company_origin_rule': company_origins,
            'years_of_experience': years_exp,
            'exclude_experience_years_min': years_exp + 1,
            'overseas_rule': overseas_rule,
            'exclude_experience_years_min': 3,
            'exclude_degree_requirement': ['要求博士在读或博士学位', '硕士及以上且明确不接受应届的社招'],
            'exclude_title_seniority': ['Manager', 'Senior', 'Lead', 'Principal'],
            'visa_dealbreakers': [],
        },
        'directions': directions,
    }

    first, last = name_en.split()[0], name_en.split()[-1]
    edu_summary = '; '.join(f"{e['school']} {e['degree']} ({e['period']})" for e in edu)
    tokens = {
        '{{ROOT}}': os.path.dirname(os.path.abspath(resume)),
        '{{ROOT_JS}}': os.path.dirname(os.path.abspath(resume)).replace('\\', '\\\\'),
        '{{WB_ROOT}}': os.path.expanduser(r'~\WorkBuddy'),
        '{{CANDIDATE_NAME_CN}}': name_cn,
        '{{CANDIDATE_NAME_EN}}': name_en,
        '{{CANDIDATE_NAME}}': re.sub(r'\s+', '', name_en).lower(),
        '{{NAME_EN_REGEX}}': f'{first}\\s?{last}',
        '{{NOTIFY_EMAIL}}': email,
        '{{PHONE}}': phone,
        '{{CURRENT_LOCATION}}': current_location,
        '{{COMPANY_ORIGIN_RULE}}': company_origins,
        '{{JOB_FOCUS}}': '、'.join(list(industries) + list(directions)) or '(待填写)',
        '{{RESUME_PDF}}': os.path.basename(resume),
        '{{CANDIDATE_EDUCATION_SUMMARY}}': edu_summary,
        '{{CANDIDATE_STATUS}}': g('candidate_status', '一句话身份状态', canon),
    }
    return profile, tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--answers', help='答案 JSON 文件（跳过交互）')
    a = ap.parse_args()
    answers = json.load(open(a.answers, encoding='utf-8')) if a.answers else None

    profile, tokens = collect(answers)

    prof_path = os.path.join(REPO, 'contracts', 'candidate_profile.json')
    tok_path = os.path.join(REPO, 'local_tokens.json')
    json.dump(profile, open(prof_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    json.dump(tokens, open(tok_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'\n已写入: {prof_path}')
    print(f'已写入: {tok_path}')

    # 立即按附B契约校验
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from validate_profile import validate
    errors, warnings = validate(prof_path, os.path.join(REPO, 'contracts', 'taxonomy.json'))
    for w in warnings:
        print('⚠️ ', w)
    if errors:
        print(f'❌ 校验未通过（{len(errors)} 项），请修正后重跑 onboard.py：')
        for e in errors:
            print('  -', e)
        sys.exit(1)

    print('\n✅ 画像创建并校验通过！下一步：')
    print('  1. python setup/apply_tokens.py        # 生成个人版 prompt 文档到 build/')
    print('  2. 把 build/prompts_personalized.md 中 5 段 prompt 粘贴进你的调度器（WorkBuddy 等）')
    print('  3. 按 docs/prompts_template.md 附A 检查 3 处结构性定制段落')


if __name__ == '__main__':
    main()
