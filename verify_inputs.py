"""Verify delivered calculation inputs against their recorded SHA-256 digests."""
from pathlib import Path
import hashlib
import json


def main():
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'results'/'source_manifest.json').read_text(encoding='utf-8'))
    failed=[]
    for item in manifest['inputs']:
        path=root/item['file']
        if not path.exists():
            failed.append(item['file']+': missing')
            continue
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=item['sha256']:
            failed.append(item['file']+': checksum mismatch')
    if failed:
        raise SystemExit('\n'.join(failed))
    print(f"Verified {len(manifest['inputs'])} saved inputs.")


if __name__=='__main__':
    main()
