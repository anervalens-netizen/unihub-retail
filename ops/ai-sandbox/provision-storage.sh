#!/bin/bash
# Host-only provisioning. Never format an existing image, including partial ones.
# Local tests: mktemp -d /tmp/unihub-ai-storage.XXXXXXXX (as root), then
# --local-test-root PATH --uid 1000 --gid 1000; same args + --teardown to remove.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C
exec /usr/bin/python3 - "$@" <<'PY'
import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

SIZE = 8 * 1024**3


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def trusted(path, directory=True, mode=None):
    s = path.lstat()
    require(not stat.S_ISLNK(s.st_mode), f"symlink: {path}")
    require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode),
            f"unexpected type: {path}")
    require(s.st_uid == 0 and s.st_gid == 0, f"not root-owned: {path}")
    require(not s.st_mode & 0o022 or (path == Path('/tmp') and s.st_mode & stat.S_ISVTX),
            f"writable ancestor: {path}")
    if mode is not None:
        require(stat.S_IMODE(s.st_mode) == mode, f"unexpected mode: {path}")
    if not directory:
        require(s.st_nlink == 1, f"hardlink: {path}")
    return s


def mounts():
    rows = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ')
        a, b = left.split(), right.split()
        decode = lambda text: re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), text)
        rows.append(dict(target=decode(a[4]), root=decode(a[3]), dev=a[2],
                         options=set(a[5].split(',')), type=b[0], source=decode(b[1])))
    return rows


def loops(image):
    return json.loads(run('losetup', '--json', '--list', '--associated', str(image),
                          '--output', 'NAME,BACK-FILE,OFFSET,SIZELIMIT,RO,AUTOCLEAR'))['loopdevices'] or []


def image_check(image):
    s = trusted(image, False, 0o600)
    require(s.st_size == SIZE, f"wrong image capacity: {image}")
    # extents metadata may consume a few additional physical blocks. Never sparse.
    require(SIZE <= s.st_blocks * 512 <= SIZE + 1024**2, f"not physically reserved: {image}")
    require(run('blkid', '-p', '-s', 'TYPE', '-o', 'value', str(image)) == 'ext4',
            f"not ext4: {image}")
    header = run('dumpe2fs', str(image))
    groups = [line for line in header.splitlines() if re.match(r'^Group [0-9]+:', line)]
    require(groups and all('ITABLE_ZEROED' in line for line in groups),
            f"unsafe lazy inode initialization: {image}")
    fields = dict(line.split(':', 1) for line in header.splitlines() if ':' in line)
    require(int(fields['Block count']) * int(fields['Block size']) == SIZE,
            f"wrong ext4 capacity: {image}")
    require(int(fields['Reserved block count']) == 0, f"reserved ext4 blocks: {image}")


def slot_check(image, target, uid, gid):
    rows = mounts()
    exact = [m for m in rows if m['target'] == str(target)]
    require(len(exact) <= 1, f"stacked mounts: {target}")
    devices = loops(image) if image.exists() else []
    if not exact:
        require(not devices, f"unexpected attached loop: {image}")
        if target.exists():
            trusted(target, mode=0o755)
            require(not any(target.iterdir()), f"nonempty unmounted target: {target}")
        return
    require(image.exists(), f"mounted target without image: {target}")
    require(len(devices) == 1, f"unexpected loop count: {image}")
    loop, m = devices[0], exact[0]
    require(loop['back-file'] == str(image) and int(loop['offset']) == 0
            and int(loop['sizelimit']) == 0 and not loop['ro'] and loop['autoclear'],
            f"unexpected loop configuration: {image}")
    dev = os.stat(loop['name']).st_rdev
    require(m['source'] == loop['name'] and m['dev'] == f'{os.major(dev)}:{os.minor(dev)}'
            and m['root'] == '/' and m['type'] == 'ext4'
            and {'rw', 'nosuid', 'nodev', 'noatime'} <= m['options']
            and 'discard' not in m['options'],
            f"unexpected mount: {target}")
    trusted(target, mode=0o755)
    workspace = target / 'workspace'
    s = workspace.lstat()
    require(stat.S_ISDIR(s.st_mode) and not workspace.is_symlink()
            and (s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) == (uid, gid, 0o770),
            f"unexpected workspace: {workspace}")
    fs = os.statvfs(workspace)
    require(7 * 1024**3 < fs.f_blocks * fs.f_frsize <= SIZE,
            f"unexpected mounted capacity: {target}")


def main():
    parser = argparse.ArgumentParser(description='Provision two fully reserved host ext4 slots')
    parser.add_argument('--local-test-root')
    parser.add_argument('--uid', type=int)
    parser.add_argument('--gid', type=int)
    parser.add_argument('--teardown', action='store_true')
    args = parser.parse_args()
    require(os.geteuid() == 0, 'must run as root')
    os.umask(0o077)
    local = args.local_test_root is not None
    if local:
        require(re.fullmatch(r'/tmp/unihub-ai-storage\.[A-Za-z0-9]{8,}', args.local_test_root),
                'local root must be a direct mktemp /tmp/unihub-ai-storage.XXXXXXXX directory')
        require(args.uid == 1000 and args.gid == 1000, 'local mode requires explicit uid/gid 1000')
        base, uid, gid = Path(args.local_test_root), args.uid, args.gid
        trusted(base)
        require(stat.S_IMODE(base.stat().st_mode) in (0o700, 0o755), 'unexpected local root mode')
    else:
        require(not args.teardown and args.uid is None and args.gid is None,
                'production has no teardown or identity overrides')
        account = pwd.getpwnam('unihub-web')
        base, uid, gid = Path('/var/lib/unihub-retail'), account.pw_uid, account.pw_gid
    for ancestor in reversed((base, *base.parents)):
        if ancestor.exists() or ancestor.is_symlink():
            trusted(ancestor)
        else:
            ancestor.mkdir(mode=0o755)
            ancestor.chmod(0o755)
    images, slots = base / 'ai-storage-images', base / 'ai-sandbox-slots'
    pairs = [(images / f'slot-{i}.ext4', slots / f'slot-{i}') for i in range(2)]
    # Reject nested/bind/stacked mounts before following any managed path.
    allowed = {str(target) for _, target in pairs}
    for m in mounts():
        if m['target'] == str(base) or m['target'].startswith(str(images)) or m['target'].startswith(str(slots)):
            require(m['target'] in allowed, f"unexpected managed mount: {m['target']}")
        if str(base).startswith(m['target'].rstrip('/') + '/'):
            require(m['root'] == '/', f"bind-mounted ancestor: {m['target']}")
    marker = base / '.unihub-ai-storage-local'
    marker_text = f'unihub-ai-storage-v1\n{base}\n{base.stat().st_dev}:{base.stat().st_ino}\n1000:1000\n'
    if local:
        if marker.exists() or marker.is_symlink():
            trusted(marker, False, 0o600)
            require(marker.read_text() == marker_text, 'invalid local ownership marker')
        else:
            require(not args.teardown and not any(base.iterdir()), 'local root must be empty or marked')
            marker.write_text(marker_text)
        base.chmod(0o755)
    lock = base / '.ai-storage-provision.lock'
    if lock.exists() or lock.is_symlink():
        trusted(lock, False, 0o600)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for directory, names in ((images, {'slot-0.ext4', 'slot-1.ext4'}),
                             (slots, {'slot-0', 'slot-1'})):
        if directory.exists() or directory.is_symlink():
            trusted(directory, mode=0o711 if directory == images else 0o755)
            require({p.name for p in directory.iterdir()} <= names, f"unexpected entries: {directory}")
        elif not args.teardown:
            directory.mkdir(mode=0o711 if directory == images else 0o755)
            directory.chmod(0o711 if directory == images else 0o755)
    # Preflight BOTH slots before formatting or unmounting either.
    for image, target in pairs:
        if image.exists() or image.is_symlink():
            image_check(image)
        slot_check(image, target, uid, gid)
    if args.teardown:
        require({p.name for p in base.iterdir()} <= {
            images.name, slots.name, marker.name, lock.name}, 'unexpected local root entries')
        for image, target in pairs:
            devices = loops(image) if image.exists() else []
            if any(m['target'] == str(target) for m in mounts()):
                run('umount', str(target))
            for device in devices:
                remaining = loops(image)
                if remaining:
                    require(len(remaining) == 1 and remaining[0] == device, 'loop changed during teardown')
                    run('losetup', '--detach', device['name'])
            require(not loops(image) if image.exists() else True, 'loop remains attached')
            if image.exists():
                image.unlink()
            if target.exists():
                target.rmdir()
        for directory in (images, slots):
            if directory.exists():
                directory.rmdir()
        lock.unlink()
        marker.unlink()
        base.rmdir()
        print('LOCAL_TEARDOWN_OK')
        return
    for image, target in pairs:
        if not image.exists():
            # O_EXCL prevents accidental replacement. Any failed partial image requires
            # explicit operator inspection; a retry will NEVER reformat it.
            image_fd = os.open(image, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(image_fd)
            run('fallocate', '-l', str(SIZE), str(image))
            # Lazy inode-table zeroing through a loop device can punch holes AFTER
            # mkfs, even with nodiscard. Initialize both tables and journal upfront.
            run('mkfs.ext4', '-F', '-m', '0', '-E',
                'nodiscard,lazy_itable_init=0,lazy_journal_init=0', str(image))
            image_check(image)
        if not target.exists():
            target.mkdir(mode=0o755)
            target.chmod(0o755)
        if not any(m['target'] == str(target) for m in mounts()):
            run('mount', '-t', 'ext4', '-o', 'loop,nosuid,nodev,noatime', str(image), str(target))
            workspace = target / 'workspace'
            if not workspace.exists() and not workspace.is_symlink():
                workspace.mkdir(mode=0o770)
                os.chown(workspace, uid, gid)
                workspace.chmod(0o770)
        slot_check(image, target, uid, gid)
        image_check(image)
        print(f'SLOT_OK image={image} workspace={target}/workspace logical={SIZE} physical={image.stat().st_blocks * 512}')


try:
    main()
except (OSError, RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
    print(f'ai-storage: FAIL CLOSED: {exc}', file=sys.stderr)
    sys.exit(1)
PY
