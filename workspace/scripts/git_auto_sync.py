"""Manual Git synchronization; only explicitly published or already tracked files.

The local authoring project projects a portable release into a separate checkout.
A normal clone publishes tracked source files once. No credentials are stored here.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'workspace/cache'
ENV = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
REPO = 'https://github.com/yw2001-as/-ashare-industry-dashboard.git'


def run(args, cwd, check=True):
    result = subprocess.run(args, cwd=cwd, env=ENV, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=180,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or str(args[0]))
    return result


def git(folder, *args, check=True):
    return run(['git', '-c', 'core.quotepath=false', *args], folder, check)


def allowed(path):
    p = Path(path)
    if p.is_absolute() or '..' in p.parts or path.startswith(('.git/', '.venv/', 'venv/')):
        return False
    if path.startswith(('收盘数据/', 'workspace/cache/', 'workspace/validation/')):
        return path == 'workspace/cache/.gitkeep'
    if path in ('snapshot.html', 'index.html', 'dashboard.fragment.html'):
        return False
    if p.suffix.lower() in ('.log', '.tmp', '.zip', '.sqlite', '.db') or p.name.startswith('.env'):
        return False
    if path.startswith('workspace/data/'):
        return p.name in ('communications_watch.json', 'exchange_holidays.json')
    return True


def plan():
    manifest = ROOT / 'workspace/release/publish-files.json'
    projection = manifest.is_file() and (ROOT / 'workspace/scripts/prepare_release.py').is_file()
    if projection:
        paths = json.loads(manifest.read_text(encoding='utf-8'))['files']
        checkout = ROOT / '发布准备/github-sync'
        public = ROOT / '发布准备/github/ashare-industry-dashboard'
        sources = {ROOT / 'dashboard.fragment.html', ROOT / 'requirements.txt', manifest,
                   ROOT / 'workspace/scripts/prepare_release.py'}
        for path in paths:
            p = Path(path)
            if len(p.parts) == 1:
                sources.add(ROOT / 'workspace/release' / p)
            elif path == 'workspace/scripts/demo-data.js':
                sources.add(ROOT / 'workspace/release/demo-data.js')
            elif path.startswith(('workspace/scripts/', 'workspace/data/', 'workspace/templates/', 'workspace/vendor/')):
                sources.add(ROOT / p)
            elif path.startswith('docs/images/'):
                sources.add(public / p)
    else:
        checkout = ROOT
        paths = git(ROOT, 'ls-files', '-z').stdout.rstrip('\0').split('\0')
        paths = [p for p in paths if p and allowed(p)]
        sources = {ROOT / p for p in paths}
        public = None
    if not paths or any(not allowed(p) for p in paths):
        raise ValueError('Publish list contains a runtime/private path or is empty.')
    return projection, checkout, public, sorted(set(paths)), sources



def scan(path):
    data = path.read_bytes()
    if len(data) > 5_000_000:
        raise ValueError('File exceeds publish limit: ' + path.name)
    if path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
        return
    text = data.decode('utf-8-sig')
    if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{24,}', text):
        raise ValueError('Possible credential in ' + path.name)
    if re.search(r'[A-Za-z]:[\\/]Users[\\/]|[A-Za-z]:[\\/]Stock Report|' + 'xwechat' + '_files', text):
        raise ValueError('Personal absolute path in ' + path.name)


def sync_once():
    projection, checkout, public, paths, _ = plan()
    if projection:
        run([sys.executable, '-X', 'utf8', str(ROOT / 'workspace/scripts/prepare_release.py')], ROOT)
        run([sys.executable, '-X', 'utf8', str(public / 'workspace/scripts/build_preview.py')], public)
        # Verify every candidate before touching the checkout.
        for path in paths:
            candidate = public / path
            if not candidate.is_file():
                raise ValueError('Missing published file: ' + path)
            scan(candidate)
        if not (checkout / '.git').exists():
            run(['git', 'clone', '--branch', 'main', '--single-branch', REPO, str(checkout)], ROOT)
    remote = git(checkout, 'remote', 'get-url', 'origin').stdout.strip()
    if projection and remote != REPO:
        raise ValueError('Unexpected origin; refusing publication.')
    branch = git(checkout, 'branch', '--show-current').stdout.strip()
    if not branch:
        raise ValueError('Detached HEAD; select a branch before syncing.')
    git(checkout, 'fetch', 'origin', branch)
    if projection and git(checkout, 'merge-base', '--is-ancestor', 'origin/' + branch, 'HEAD', check=False).returncode:
        raise ValueError('Remote has new commits. Reconcile them with the authoring folder before retrying.')
    # Never force push, rebase, reset or resolve conflicts automatically.
    git(checkout, 'merge', '--ff-only', 'origin/' + branch)
    if projection:
        for path in paths:
            destination = checkout / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((public / path).read_bytes())
    for path in paths:
        if (checkout / path).is_file():
            scan(checkout / path)
    staged = set(git(checkout, 'diff', '--cached', '--name-only', '-z').stdout.rstrip('\0').split('\0')) - {''}
    if staged - set(paths):
        raise ValueError('Unrelated files are staged; refusing to include them.')
    git(checkout, 'add', '--all', '--', *paths)
    changed = git(checkout, 'diff', '--cached', '--name-only').stdout.strip()
    if changed:
        git(checkout, '-c', 'user.name=Dashboard Sync', '-c', 'user.email=dashboard-sync@localhost',
            'commit', '-m', 'Sync dashboard source ' + time.strftime('%Y-%m-%d %H:%M:%S'))
    # Also retries a previous successful commit whose push failed.
    git(checkout, 'push', 'origin', 'HEAD:' + branch)
    return {'status': 'pushed' if changed else 'up_to_date', 'commit': git(checkout, 'rev-parse', 'HEAD').stdout.strip(),
            'files': changed.splitlines(), 'repository': remote}


def main():
    parser = argparse.ArgumentParser(description='Manually publish approved dashboard files once.')
    parser.add_argument('--once', action='store_true', help='Run one explicit synchronization.')
    parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    import msvcrt
    lock = (CACHE / 'github-sync.lock').open('a+b')
    lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print('Another manual synchronization is running.', flush=True)
        return
    result = sync_once()
    (CACHE / 'github-sync-status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
