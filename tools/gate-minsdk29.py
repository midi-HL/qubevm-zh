#!/usr/bin/env python3
"""minSdk 29 (Android 10) 适配门禁。

锁死本次为降到 Android 10 所做的全部改动。每一条断言都可反向验证：
把对应修复删掉/改回，本脚本必须 FAIL。

用法:  python3 tools/gate-minsdk29.py
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


# ---------------------------------------------------------------- 1. minSdk
GRADLE_MODULES = [
    'qube-android-lib/build.gradle',
    'qube-android-arm/build.gradle',
    'qube-android-x86/build.gradle',
    'qube-android-ppc/build.gradle',
    'qube-android-m68k/build.gradle',
]
for mod in GRADLE_MODULES:
    txt = read(mod)
    m = re.search(r'minSdk\s*=\s*(\d+)', txt)
    check('%s minSdk == 29' % mod,
          m is not None and m.group(1) == '29',
          '(got %s)' % (m.group(1) if m else 'missing'))

# ------------------------------------------------- 2. isExternalStorageManager
# 唯一的真阻塞点：API 30 才有的框架方法。必须被 SDK_INT < R 守护，
# 否则 Android 10 上调用直接 NoSuchMethodError 崩溃。
act = read('qube-android-lib/src/main/java/com/max2idea/android/qube/main/QubeActivity.java')
m = re.search(r'private void checkStoragePermission\(\)\s*\{(.*?)\n    \}', act, re.S)
check('checkStoragePermission() 存在', m is not None)
if m:
    # 先剥掉注释，否则「注释里提到 SDK_INT」会被误判成已守护
    body = re.sub(r'//[^\n]*', '', m.group(1))
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    # 守护必须是 if (SDK_INT < R) return; 这种早退形式，且位于调用之前
    guard_re = re.compile(
        r'if\s*\(\s*Build\.VERSION\.SDK_INT\s*<\s*Build\.VERSION_CODES\.R\s*\)\s*'
        r'(?:\{\s*)?return', re.S)
    gm = guard_re.search(body)
    call_pos = body.find('isExternalStorageManager()')
    check('isExternalStorageManager() 之前有 if(SDK_INT < R) return 早退守护',
          gm is not None and call_pos != -1 and gm.start() < call_pos,
          '(guard@%s call@%s)' % (gm.start() if gm else -1, call_pos))
    check('守护条件判断的是 VERSION_CODES.R',
          gm is not None and 'VERSION_CODES.R' in gm.group(0), '(低版本会直接崩溃)')

# ------------------------------------------------ 3. setNavigationBarContrast
e2e = read('qube-android-lib/src/main/java/com/max2idea/android/qube/utils/EdgeToEdgeUtils.java')
check('setNavigationBarContrastEnforced 调用仍存在（功能未被误删）',
      'setNavigationBarContrastEnforced(false)' in e2e)

# ------------------------------------------------------ 4. startForeground 类型
svc = read('qube-android-lib/src/main/java/com/max2idea/android/qube/machine/MachineService.java')
check('startForeground 已改为 ServiceCompat.startForeground',
      'ServiceCompat.startForeground(' in svc,
      '(裸 startForeground 在 API 29+ 会抛 ForegroundServiceTypeNotDefinedException)')
check('传入了 FOREGROUND_SERVICE_TYPE_DATA_SYNC',
      'FOREGROUND_SERVICE_TYPE_DATA_SYNC' in svc)
check('ServiceInfo 已 import',
      'import android.content.pm.ServiceInfo;' in svc)
check('ServiceCompat 已 import',
      'import androidx.core.app.ServiceCompat;' in svc)
check('没有残留裸 service.startForeground(notifID',
      'service.startForeground(notifID' not in svc)

# -------------------------------------------- 5. manifest 的 legacy 存储开关
mf = read('qube-android-lib/src/main/AndroidManifest.xml')
check('requestLegacyExternalStorage 仍然保留（Android 10 必需）',
      'requestLegacyExternalStorage' in mf)
check('MANAGE_EXTERNAL_STORAGE 权限仍保留（Android 11+ 必需）',
      'MANAGE_EXTERNAL_STORAGE' in mf)

# ------------------------------------------------- 6. 既有汉化门禁未被破坏
check('既有汉化门禁 gate-zh.py 仍存在',
      os.path.isfile(os.path.join(ROOT, 'tools', 'gate-zh.py')))

# ------------------------------------------------------------------- 汇总
print()
print('=' * 62)
print('minSdk29 gate: %d passed, %d failed' % (passed, len(failures)))
if failures:
    print('FAILED:')
    for f in failures:
        print('  - %s' % f)
    print('=' * 62)
    sys.exit(1)
print('=' * 62)
sys.exit(0)
