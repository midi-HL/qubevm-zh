#!/usr/bin/env python3
"""SAF / 存储权限 / QEMU_VERSION 门禁。

锁死本轮三个真机实测故障的修复。每一条断言都可反向验证：
把对应修复删掉/改回，本脚本必须 FAIL。

   1. QEMU_VERSION 打进 assets
      （缺失 -> QubeApplication.setupEnv 抛 IllegalStateException，
        弹 "Could not load version information: ... QEMU_VERSION"）

   2. SAF 路径不得被降级成裸绝对路径
      （降级 -> targetSdk 37 下 requestLegacyExternalStorage 已失效，
        原生 QEMU 用进程自身 UID open() 共享存储被 SELinux 拒绝：
        Could not open '...': Permission denied）

   3. 存储权限不得依赖 许可弹窗->Help 回调链
      （依赖 -> 链上任何一环中断就整条跳过，系统设置显示
        「未请求任何权限」）

用法:  python3 tools/gate-storage-saf.py
退出码 0 = 全部通过；1 = 有断言失败。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

failures = []
passed = 0


def check(name, cond, detail=''):
    global passed
    if cond:
        passed += 1
        print("PASS  %s" % name)
    else:
        failures.append(name)
        print("FAIL  %s  %s" % (name, detail))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def strip_comments(src):
    """剥掉 /* */ 块注释与 // 行注释。

    注意：不能简单地把 // 之后全删 —— Java 字符串字面量
    "content://" 本身就含 "//"，一刀切会把代码里的字符串切断，
    让断言误报（曾因此把正确代码判成 FAIL）。所以先把字符串
    字面量整体抽出占位，剥完注释再放回。
    """
    lits = []

    def stash(m):
        lits.append(m.group(0))
        return '\x00STR%d\x00' % (len(lits) - 1)

    # 先保护字符串与字符字面量（含转义）
    src = re.sub(r'"(?:\\.|[^"\\])*"', stash, src, flags=re.S)
    src = re.sub(r"'(?:\\.|[^'\\])*'", stash, src, flags=re.S)

    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)

    for i, lit in enumerate(lits):
        src = src.replace('\x00STR%d\x00' % i, lit)
    return src


ASSET = 'qube-android-lib/src/main/assets/QEMU_VERSION'
VMEXEC = 'qube-android-lib/src/main/java/com/max2idea/android/qube/jni/VMExecutor.java'
QACT = 'qube-android-lib/src/main/java/com/max2idea/android/qube/main/QubeActivity.java'

# ------------------------------------------------ 1. QEMU_VERSION 打进 assets
check('assets/QEMU_VERSION 存在', os.path.isfile(os.path.join(ROOT, ASSET)),
      '(缺失 -> setupEnv 抛 IllegalStateException)')
if os.path.isfile(os.path.join(ROOT, ASSET)):
    ver = read(ASSET).strip()
    check('QEMU_VERSION 形如 major.minor.patch',
          re.fullmatch(r'\d+\.\d+\.\d+', ver) is not None, '(got %r)' % ver)
    check('QEMU_VERSION 恰好三段（QubeApplication 按三段 parseInt）',
          len(ver.split('.')) == 3, '(got %r)' % ver)

# ------------------------------------ 2. SAF 路径不得降级成裸绝对路径
vm = strip_comments(read(VMEXEC))

m = re.search(r'public String getDriveFilePath\(String driveFilePath\)\s*\{.*?\n    \}',
              vm, flags=re.S)
check('getDriveFilePath 可定位', m is not None)
if m:
    body = m.group(0)
    check('getDriveFilePath 有 SAF 早退分支（/content// 或 content://）',
          ('startsWith("/content//")' in body)
          or ('startsWith("content://")' in body),
          '(裸路径降级 -> Permission denied)')
    idx_saf = body.find('getQemuFilePath')
    idx_real = body.find('getRealPathForFile')
    check('SAF 早退分支先于 getRealPathForFile 求值',
          idx_saf != -1 and idx_real != -1 and idx_saf < idx_real,
          '(idx_saf=%s idx_real=%s)' % (idx_saf, idx_real))

compat_h = read('qube-android-lib/src/main/jni/compat/qube_compat_filesystem.h')
check('native compat 层 ENABLE_ASF 仍为 1（FD 桥启用）',
      re.search(r'#define\s+ENABLE_ASF\s+1', compat_h) is not None)

# ------------------------------------- 3. 存储权限不得依赖许可弹窗回调链
qa = strip_comments(read(QACT))
m = re.search(r'private void checkFirstLaunch\(\)\s*\{.*?\n    \}', qa, flags=re.S)
check('checkFirstLaunch 可定位', m is not None)
if m:
    body = m.group(0)
    check('checkFirstLaunch 无条件调用 checkStoragePermission',
          'checkStoragePermission();' in body,
          '(只在 else 分支调 -> 首启回调链断了就跳过)')
    check('checkFirstLaunch 未把 checkStoragePermission 关在 else 里',
          not re.search(r'\belse\s*\{\s*checkStoragePermission\(\)', body),
          '(首启时权限请求被整条跳过)')

# ------------------------------------------ 4. 既有门禁未被破坏
for g in ('gate-zh.py', 'gate-minsdk29.py'):
    check('既有门禁 %s 仍存在' % g,
          os.path.isfile(os.path.join(ROOT, 'tools', g)))

# ------------------------------------------------------------------- 汇总
print()
print('=' * 62)
print('storage/SAF gate: %d passed, %d failed' % (passed, len(failures)))
if failures:
    print('FAILED:')
    for f in failures:
        print('  - %s' % f)
    print('=' * 62)
    sys.exit(1)
print('=' * 62)
sys.exit(0)
