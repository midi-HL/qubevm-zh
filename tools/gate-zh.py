#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QubeVM 中文本地化门禁（可红可绿）"""
import sys, re, os
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES  = os.path.join(BASE, "qube-android-lib", "src", "main", "res")
EN   = os.path.join(RES, "values", "strings.xml")
ZH   = os.path.join(RES, "values-zh", "strings.xml")
ENARR= os.path.join(RES, "values", "array.xml")

FORBIDDEN = {"Default"}          # translatable=false, 值是 QEMU 参数
LOGIC_COUPLED = {"title_load_defaults"}  # 两侧同源比较，翻可，登记审计

fails, passes = [], []
ok  = lambda m: passes.append(m)
bad = lambda m: fails.append(m)

def parse(path):
    root = ET.parse(path).getroot()
    s, a = {}, {}
    for c in root:
        if c.tag == "string":
            s[c.get("name")] = {"text": "".join(c.itertext()),
                                "raw": ET.tostring(c, encoding="unicode"),
                                "attrs": dict(c.attrib)}
        elif c.tag == "string-array":
            a[c.get("name")] = [i.text or "" for i in c]
    return s, a

def raw_key_count(path):
    """统计源码里 name= 出现次数（用于查重复 key）"""
    return len(re.findall(r'<string\s+name="', open(path, encoding="utf-8").read()))

def main():
    if not os.path.exists(ZH):
        bad("values-zh/strings.xml 不存在"); return report()
    try:
        en_s, en_a = parse(EN); zh_s, zh_a = parse(ZH)
        ok("XML 解析成功（values-zh 语法合法）")
    except ET.ParseError as e:
        bad(f"XML 解析失败: {e}"); return report()

    # 1 重复 key
    n_raw, n_uniq = raw_key_count(ZH), len(zh_s)
    if n_raw != n_uniq:
        bad(f"存在重复 key: 源码 {n_raw} 条 vs 去重 {n_uniq} 条")
    else:
        ok(f"无重复 key（{n_raw} 条 string + {sum(len(v) for v in zh_a.values())} 个 array item）")

    # 2 禁译项
    if FORBIDDEN & set(zh_s):
        for k in FORBIDDEN & set(zh_s): bad(f"禁译项被翻译: {k}（会破坏 QEMU 参数）")
    else:
        ok(f"禁译项零侵入（{len(FORBIDDEN)} 项）")

    # 3 translatable=false
    nt = {k for k,v in en_s.items() if v["attrs"].get("translatable") == "false"}
    if nt & set(zh_s):
        for k in nt & set(zh_s): bad(f"translatable=false 被翻译: {k}")
    else:
        ok(f"translatable=false 零侵入（{len(nt)} 项）")

    # 4 未知 key
    unk = set(zh_s) - set(en_s)
    if unk:
        for k in sorted(unk): bad(f"未知 key: {k}")
    else:
        ok(f"全部 {len(zh_s)} 个 key 均存在于英文资源")

    # 5 占位符
    ph = re.compile(r"%(?:\d+\$)?[sdf]")
    n = 0
    for k,v in zh_s.items():
        if k not in en_s: continue
        if sorted(ph.findall(en_s[k]["text"])) != sorted(ph.findall(v["text"])):
            bad(f"占位符不一致: {k}"); n += 1
    if n == 0: ok("占位符全部一致")

    # 6 换行总数：只统计 <string> 标签内部的语义换行（\\n 转义 + 字面换行），
    #   不含 XML 源码自身的缩进换行
    n = 0
    inner_en = inner_zh = None
    def inner_map(path):
        src = open(path, encoding="utf-8").read()
        m = {}
        for mm in re.finditer(r'<string\s+name="([^"]+)"[^>]*>(.*?)</string>', src, re.S):
            m[mm.group(1)] = mm.group(2)
        return m
    inner_en, inner_zh = inner_map(EN), inner_map(ZH)
    for k in zh_s:
        if k not in en_s or k not in inner_en or k not in inner_zh: continue
        e = inner_en[k].count(r"\n") + inner_en[k].count("\n")
        z = inner_zh[k].count(r"\n") + inner_zh[k].count("\n")
        if e != z: bad(f"换行数不一致: {k} en={e} zh={z}"); n += 1
    if n == 0: ok("换行数量全部一致（\\n 转义与字面换行等价计算）")

    # 7 CDATA / HTML
    tag = re.compile(r"</?[a-zA-Z][^>]*>")
    n = 0
    for k,v in zh_s.items():
        if k not in en_s: continue
        if ("<![CDATA[" in en_s[k]["raw"]) != ("<![CDATA[" in v["raw"]):
            bad(f"CDATA 不一致: {k}"); n += 1
        if sorted(tag.findall(en_s[k]["text"])) != sorted(tag.findall(v["text"])):
            bad(f"HTML 标签不一致: {k}"); n += 1
    if n == 0: ok("CDATA 与 HTML 标签完整保留")

    # 8 array 长度
    n = 0
    for name, items in zh_a.items():
        if name not in en_a: bad(f"未知 array: {name}"); n += 1; continue
        if len(items) != len(en_a[name]):
            bad(f"array 长度不一致: {name}"); n += 1
    if n == 0: ok(f"string-array 长度一致（{len(zh_a)} 个）")

    # 9 空值
    e = [k for k,v in zh_s.items() if not v["text"].strip()]
    if e:
        for k in e: bad(f"翻译为空: {k}")
    else: ok("无空翻译")

    # 10 覆盖度
    tr = {k for k,v in en_s.items() if v["attrs"].get("translatable") != "false"}
    cov = tr & set(zh_s)
    ok(f"覆盖度 {len(cov)}/{len(tr)} = {len(cov)/len(tr)*100:.1f}%（未译项安全回退英文）")

    # 11 关键 GUI 项必须在
    must = ["close","reset","shutdown","Settings","Cancel","Ok","Create",
            "section_board","section_disks","section_boot","section_graphics",
            "section_audio","section_network" if "section_network" in en_s else "section_advanced",
            "hard_disk_a_label","boot_from_label","video_display_label",
            "sound_card_label","diskCache","RefreshRate"]
    miss = [k for k in must if k not in zh_s and k in en_s]
    if miss: bad(f"关键 GUI 项缺失: {miss}")
    else: ok(f"关键 GUI 项齐全（{len(must)} 项）")

    return report()

def report():
    print("="*70); print("QubeVM 中文本地化门禁"); print("="*70)
    for p in passes: print(f"  \033[32mPASS\033[0m  {p}")
    for f in fails:  print(f"  \033[31mFAIL\033[0m  {f}")
    print("-"*70)
    if fails:
        print(f"\033[31m门禁失败\033[0m — {len(fails)} 项失败 / {len(passes)} 项通过"); return 1
    print(f"\033[32m门禁全绿\033[0m — {len(passes)} 项全部通过"); return 0

if __name__ == "__main__":
    sys.exit(main())
