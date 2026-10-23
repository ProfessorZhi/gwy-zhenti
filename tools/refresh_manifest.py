#!/usr/bin/env python3
"""刷新 catalog/manifest.jsonl 的字节数与 sha256。

任何一次正文改写（重排、补字段、修错字）之后都必须跑一次，否则清单与磁盘对不上，
下游按 sha256 做的完整性校验会全部失败。

用法：
    python3 tools/refresh_manifest.py --check     # 只报告哪些行过期
    python3 tools/refresh_manifest.py --write     # 就地更新
"""

import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, 'catalog/manifest.jsonl')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', default=DEFAULT)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--check', action='store_true', help='只检查（默认行为）')
    args = parser.parse_args()

    records, stale, missing = [], [], []
    with open(args.manifest, encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            full = os.path.join(ROOT, record['path'])
            if not os.path.exists(full):
                missing.append(record['path'])
                records.append((record, line, False))
                continue
            data = open(full, 'rb').read()
            digest, size = hashlib.sha256(data).hexdigest(), len(data)
            changed = record.get('sha256') != digest or record.get('bytes') != size
            if changed:
                stale.append(record['path'])
                record['sha256'], record['bytes'] = digest, size
            records.append((record, line, changed))

    print(f'共 {len(records)} 行 · 需刷新 {len(stale)} · 文件缺失 {len(missing)}')
    if stale[:5]:
        print('样例', stale[:5])
    if missing:
        print('缺失', missing[:10])
    if args.write and stale:
        with open(args.manifest, 'w', encoding='utf-8') as handle:
            for record, original, changed in records:
                # 未变的行原样保留，避免整份清单产生无意义的格式 diff
                handle.write((json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
                             if changed else original)
        print('已写回', args.manifest)
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
