"""Host storage contract; privileged lifecycle is explicit opt-in, never CI auto-root.

UNIHUB_AI_STORAGE_ROOT_TEST=1 python3 backend/tests/test_ai_assistant_storage_provisioner.py
Run via the existing authorized root executor on a development host, not production.
"""
import errno
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'ops/ai-sandbox/provision-storage.sh'
SIZE = 8 * 1024**3


class StorageContractTests(unittest.TestCase):
    def test_shell_and_embedded_python_syntax(self):
        subprocess.run(['bash', '-n', str(SCRIPT)], check=True)
        source = SCRIPT.read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        compile(source, str(SCRIPT), 'exec')
        self.assertIn("'nodiscard,lazy_itable_init=0,lazy_journal_init=0'", source)
        self.assertNotIn('docker', source.lower())

    def test_units_keep_mounts_in_host_namespace(self):
        storage = (REPO / 'ops/systemd/unihub-ai-storage.service').read_text()
        directives = [line for line in storage.splitlines() if line and not line.startswith('#')]
        self.assertIn('PrivateMounts=no', directives)
        for forbidden in ('ProtectSystem=', 'ProtectHome=', 'PrivateTmp=', 'PrivateDevices=',
                          'ReadWritePaths=', 'ExecStop='):
            self.assertFalse(any(line.startswith(forbidden) for line in directives))
        ai = (REPO / 'ops/systemd/unihub-ai.service').read_text().splitlines()
        self.assertIn('Requires=docker.service unihub-ai-storage.service', ai)
        self.assertIn('After=network-online.target docker.service unihub-ai-storage.service', ai)
        self.assertEqual([line for line in ai if line.startswith('ReadWritePaths=')], [
            f'ReadWritePaths=/var/lib/unihub-retail/ai-sandbox-slots/slot-{i}/workspace'
            for i in range(2)])
        self.assertIn('StateDirectory=unihub-retail/ai-assistant', ai)

    def test_production_teardown_and_bad_local_arguments_rejected(self):
        for args in (['--teardown'], ['--local-test-root', '/var/lib/docker'],
                     ['--local-test-root', '/tmp/unihub-ai-storage.abcdefgh']):
            result = subprocess.run(['bash', str(SCRIPT), *args], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('FAIL CLOSED', result.stderr)

    @unittest.skipUnless(os.environ.get('UNIHUB_AI_STORAGE_ROOT_TEST') == '1' and os.geteuid() == 0,
                         'explicit disposable host-root test only')
    def test_actual_two_slots_lifecycle_failclosed_and_enospc(self):
        self.assertGreater(shutil.disk_usage('/tmp').free, 28 * 1024**3)
        base = Path(tempfile.mkdtemp(prefix='unihub-ai-storage.', dir='/tmp'))
        args = ['bash', str(SCRIPT), '--local-test-root', str(base), '--uid', '1000', '--gid', '1000']
        images = [base / f'ai-storage-images/slot-{i}.ext4' for i in range(2)]
        targets = [base / f'ai-sandbox-slots/slot-{i}' for i in range(2)]

        def invoke(ok=True, extra=()):
            result = subprocess.run([*args, *extra], capture_output=True, text=True)
            if ok:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('FAIL CLOSED', result.stderr)
            return result

        def identity(image):
            return (image.stat().st_ino, image.stat().st_size,
                    image.stat().st_blocks * 512,
                    subprocess.check_output(['blkid', '-p', '-s', 'UUID', '-o', 'value', str(image)], text=True))

        try:
            print(invoke().stdout, flush=True)
            identities = [identity(image) for image in images]
            for i, target in enumerate(targets):
                (target / 'workspace/persist').write_text(f'slot-{i}')
            invoke()  # already mounted idempotence
            self.assertEqual(identities, [identity(image) for image in images])
            # Malformed workspace, image permissions, marker, symlink and nested mount.
            workspace = targets[1] / 'workspace'
            workspace.chmod(0o777)
            try:
                invoke(False)
                invoke(False, ['--teardown'])
            finally:
                workspace.chmod(0o770)
            images[1].chmod(0o644)
            try:
                invoke(False)
            finally:
                images[1].chmod(0o600)
            marker = base / '.unihub-ai-storage-local'
            original = marker.read_text()
            marker.write_text('not-owned\n')
            try:
                invoke(False, ['--teardown'])
            finally:
                marker.write_text(original)
            extra = base / 'ai-storage-images/unexpected'
            extra.symlink_to('/etc/passwd')
            try:
                invoke(False)
            finally:
                extra.unlink()
            subprocess.run(['mount', '-t', 'tmpfs', '-o', 'size=1m', 'tmpfs', str(workspace)], check=True)
            try:
                invoke(False)
                invoke(False, ['--teardown'])
            finally:
                subprocess.run(['umount', str(workspace)], check=True)
            # Reboot/restart equivalent: clean unmount, no format, same filesystem/data.
            for target in targets:
                subprocess.run(['umount', str(target)], check=True)
            # Wrong-size, sparse and fully allocated non-ext4 existing images must
            # be rejected without ever formatting them. Preserve the genuine image.
            saved = base / 'saved.ext4'
            images[1].rename(saved)
            try:
                images[1].write_bytes(b'not-a-filesystem')
                images[1].chmod(0o600)
                invoke(False)
                with images[1].open('r+b') as bad:
                    bad.truncate(SIZE)
                invoke(False)
                subprocess.run(['fallocate', '-l', str(SIZE), str(images[1])], check=True)
                invoke(False)
                with images[1].open('rb') as bad:
                    self.assertEqual(bad.read(16), b'not-a-filesystem')
                images[1].unlink()
                images[1].symlink_to(saved)
                invoke(False)
            finally:
                images[1].unlink()
                saved.rename(images[1])
            invoke()
            self.assertEqual(identities, [identity(image) for image in images])
            for i, target in enumerate(targets):
                self.assertEqual((target / 'workspace/persist').read_text(), f'slot-{i}')
            # Actual unprivileged near-limit allocation + ENOSPC on each fixed disk.
            for target in targets:
                pid = os.fork()
                if pid == 0:
                    try:
                        os.setgroups([])
                        os.setgid(1000)
                        os.setuid(1000)
                        path = target / 'workspace/allocation-proof'
                        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                        fs = os.statvfs(path)
                        near = fs.f_bavail * fs.f_frsize - 64 * 1024**2
                        os.posix_fallocate(fd, 0, near)
                        os.pwrite(fd, b'proof', 0)
                        os.fsync(fd)
                        try:
                            os.posix_fallocate(fd, near, 128 * 1024**2)
                        except OSError as exc:
                            if exc.errno != errno.ENOSPC:
                                raise
                        else:
                            raise AssertionError('capacity exceeded')
                        os.close(fd)
                        path.unlink()
                        os._exit(0)
                    except BaseException:
                        import traceback
                        traceback.print_exc()
                        os._exit(1)
                self.assertEqual(os.waitpid(pid, 0)[1], 0)
                subprocess.run(['sync', '-f', str(target)], check=True)
            self.assertEqual(identities, [identity(image) for image in images])
            # Regression: default lazy inode initialization punched 128MiB holes
            # after the original fast smoke had passed. All groups are checked by
            # the provisioner; also leave the real mounts idle across writeback.
            time.sleep(15)
            invoke()
            self.assertEqual(identities, [identity(image) for image in images])
            print('TWO_SLOT_IDEMPOTENCE_RESTART_ENOSPC_DELAYED_RESERVATION_PASS', identities, flush=True)
        finally:
            result = invoke(extra=['--teardown'])
            print(result.stdout, flush=True)
            self.assertFalse(base.exists())
            for image in images:
                self.assertEqual(subprocess.check_output(['losetup', '-j', str(image)], text=True), '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
