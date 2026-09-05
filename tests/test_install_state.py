import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('install_state', ROOT / 'scripts/install_state.py')
state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state)
SOURCE = 'a' * 40
IMAGE = 'sha256:' + 'b' * 64
ASSEMBLY = 'c' * 64


def document(source=SOURCE):
    value = {'schema': 'mcpgit.offline-release.v1', 'source_sha': source,
             'release_id': 'git-' + source, 'created_unix': 1, 'layers': []}
    for kind in ('base_image', 'tools_volume', 'program'):
        value['layers'].append({'kind': kind, 'file': kind + '.tar.gz', 'sha256': 'd' * 64,
                                'bytes': 1, 'version': 'v1'})
    value['layers'][0].update(image_tag='mcpgit-base:v1', image_id=IMAGE)
    value['layers'][2]['target'] = state.TARGETS['linux-amd64']
    return value


class InstallStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, MCPGIT_STATE_DIR=str(self.root / 'state'))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.path = self.root / 'manifest.json'
        self.value = document()
        self.path.write_text(json.dumps(self.value))
        self.hashes = {key: 'e' * 64 for key in state.PROGRAM.keys() | state.TOOLS.keys()}
        self.saved = {'schema': 'mcpgit.install-state.v1', 'instance': 'ddtry', 'docker_id': 'docker-1',
                      'image_id': IMAGE, 'foundation_image_id': IMAGE, 'foundation_hashes': self.hashes,
                      'hashes': self.hashes, 'manifest': self.value,
                      'manifest_sha256': state.sha(self.path), 'assembly_sha256': ASSEMBLY}

    def save(self):
        state.atomic(state.state_path('ddtry'), self.saved)

    def plan(self, strict=False, full=False, active=IMAGE):
        with patch.object(state, 'run', return_value='docker-1'), \
             patch.object(state, 'inspect', side_effect=lambda kind, name: {'Image': active} if kind == 'container' else {'Id': name}), \
             patch.object(state, 'probe') as probe:
            result = state.plan(self.path, 'ddtry', ASSEMBLY, strict, full)
            return result, probe.call_count

    def test_pointer_binds_both_architectures_to_source_and_manifest(self):
        pointer = json.loads((ROOT / 'offline-latest.json').read_text())
        self.assertEqual(state.select(pointer, 'linux-amd64'), pointer['architectures']['linux-amd64'])
        for change in ('source', 'target', 'digest', 'missing'):
            bad = copy.deepcopy(pointer)
            entry = bad['architectures']['linux-amd64']
            if change == 'source': entry['source_sha'] = 'f' * 40
            elif change == 'target': entry['target'] = state.TARGETS['linux-arm64']
            elif change == 'digest': entry['manifest_sha256'] = 'wrong'
            else: del bad['architectures']['linux-arm64']
            with self.subTest(change=change), self.assertRaises(state.InstallError):
                state.select(bad, 'linux-amd64')

    def test_manifest_pin_rejects_before_manifest_paths_are_used(self):
        selected = {'source_sha': SOURCE, 'target': state.TARGETS['linux-amd64'], 'manifest_sha256': state.sha(self.path)}
        self.assertEqual(state.manifest(self.path, selected), self.value)
        self.path.write_text('{"layers":[{"file":"../../sensitive"}]}')
        with patch.object(state.offline, 'load_manifest') as load, self.assertRaisesRegex(state.InstallError, 'differs from selected'):
            state.manifest(self.path, selected)
        load.assert_not_called()

    def test_manifest_source_and_target_are_checked_even_with_matching_digest(self):
        selected = {'source_sha': 'f' * 40, 'target': state.TARGETS['linux-amd64'], 'manifest_sha256': state.sha(self.path)}
        with self.assertRaisesRegex(state.InstallError, 'source or target'):
            state.manifest(self.path, selected)

    def test_first_install_is_full_but_strict_upgrade_refuses_missing_receipt(self):
        answer, calls = self.plan()
        self.assertEqual(answer['mode'], 'full')
        self.assertEqual(calls, 0)
        with self.assertRaisesRegex(state.InstallError, 'Program-only requires'):
            self.plan(strict=True)

    def test_exact_image_replay_needs_no_archives(self):
        self.save()
        answer, calls = self.plan(strict=True)
        self.assertEqual(answer['mode'], 'exact')
        self.assertEqual(calls, 2)
        self.assertFalse((self.root / 'program.tar.gz').exists())

    def test_program_change_reuses_fixed_foundation(self):
        self.save()
        self.value = document('f' * 40)
        self.path.write_text(json.dumps(self.value))
        answer, calls = self.plan(strict=True)
        self.assertEqual(answer['mode'], 'program')
        self.assertEqual(answer['foundation_image_id'], IMAGE)
        self.assertEqual(calls, 1)

    def test_one_hundred_program_selections_do_not_chain_parents(self):
        for i in range(100):
            self.saved['image_id'] = 'sha256:' + format(i + 1, '064x')
            self.save()
            self.path.write_text(json.dumps(document(format(i + 1, '040x'))))
            answer, _ = self.plan(strict=True, active=self.saved['image_id'])
            self.assertEqual(answer['foundation_image_id'], IMAGE)

    def test_cold_layer_or_assembly_change_cannot_silently_program_upgrade(self):
        for layer in (0, 1):
            self.save()
            value = copy.deepcopy(self.value)
            value['layers'][layer]['sha256'] = 'f' * 64
            self.path.write_text(json.dumps(value))
            with self.assertRaisesRegex(state.InstallError, 'unchanged Base/Tools'):
                self.plan(strict=True)
            self.assertEqual(self.plan()[0]['mode'], 'full')
        self.assertFalse(state.compatible(self.saved, self.value, 'f' * 64))

    def test_changed_active_image_and_missing_foundation_are_not_adopted(self):
        self.save()
        with self.assertRaisesRegex(state.InstallError, 'current image differs'):
            self.plan(active='sha256:' + 'f' * 64)
        with patch.object(state, 'run', return_value='docker-1'), \
             patch.object(state, 'inspect', side_effect=[{'Image': IMAGE}, {'Id': 'wrong'}]), \
             self.assertRaisesRegex(state.InstallError, 'foundation missing'):
            state.plan(self.path, 'ddtry', ASSEMBLY)

    def test_wrong_daemon_public_receipt_and_symlink_fail(self):
        self.save()
        with patch.object(state, 'run', return_value='other'), self.assertRaisesRegex(state.InstallError, 'another Docker'):
            state.plan(self.path, 'ddtry', ASSEMBLY)
        path = state.state_path('ddtry')
        path.chmod(0o644)
        with self.assertRaises(state.InstallError): self.plan()
        path.unlink()
        path.symlink_to(self.path)
        with self.assertRaises(state.InstallError): self.plan()

    def test_explicit_full_bypasses_receipt_but_not_strict_program_contract(self):
        self.assertEqual(self.plan(full=True)[0]['mode'], 'full')
        with self.assertRaises(state.InstallError): self.plan(strict=True, full=True)

    def test_receipt_atomicity_and_shell_values(self):
        self.save()
        path = state.state_path('ddtry')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        answer, _ = self.plan()
        lines = state.shell_plan(answer)
        self.assertIn('install_mode=exact', lines)
        self.assertNotIn('credential_file=', lines)
        with self.assertRaises(state.InstallError): state.state_path('../ddtry')

    def test_archive_hashing_checks_executable_shape(self):
        path = self.root / 'program.tar.gz'
        with tarfile.open(path, 'w:gz') as tar:
            for name in ('mcpgit', 'mcpgitgw'):
                data = ('binary-' + name).encode()
                item = tarfile.TarInfo('program/bin/' + name)
                item.size, item.mode = len(data), 0o755
                tar.addfile(item, io.BytesIO(data))
        result = state.executable_hashes(path, 'program', state.PROGRAM)
        self.assertEqual(result['mcpgit'], hashlib.sha256(b'binary-mcpgit').hexdigest())
        self.assertEqual(result['safe'], '')

    def test_backup_and_uninstalled_upgrade_exit_nonzero(self):
        for command in ('backup', 'upgrade'):
            result = subprocess.run(['sh', str(ROOT / 'deploy/mcpgitctl'), '--instance', 'ddtry', command], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_existing_smoke_paths_survive_rejection(self):
        config = self.root / '.mcpgit/instances/ddtry.toml'
        config.parent.mkdir(parents=True)
        config.write_text('do not delete')
        env = {**os.environ, 'HOME': str(self.root), 'TMPDIR': str(self.root)}
        result = subprocess.run(['bash', str(ROOT / 'scripts/new_agent_public_install_smoke.sh'), '--instance', 'ddtry', '--keep'], env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_text(), 'do not delete')

    def test_shell_rejects_bad_input_without_download(self):
        for args in (['--instance'], ['--instance', '../x'], ['--port', '70000'], ['--program-only', '--download-only']):
            result = subprocess.run(['sh', str(ROOT / 'deploy/novice-install.sh'), *args], capture_output=True,
                env={**os.environ, 'HOME': str(self.root)})
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(b'fetching', result.stdout)

    def test_public_control_paths_preserve_readiness_and_program_scope(self):
        shell = (ROOT / 'deploy/novice-install.sh').read_text()
        self.assertLess(shell.index('manifest --manifest "$control_dir/manifest.json"'), shell.index('make_install_plan\n'))
        self.assertIn('"$install_mode" = full', shell)
        self.assertIn('--read-only', (ROOT / 'scripts/install_state.py').read_text())
        self.assertIn('no layer download or unpack', shell)
        self.assertIn('record_installation ||', shell)
        self.assertIn('if ! record_installation;', shell)
        self.assertNotIn('docker rm -f "$rollback_container" >/dev/null 2>&1 || true', shell)
        self.assertIn('refusing to delete an unowned container', shell)
        self.assertIn('install-transaction=$transaction_id', shell)
        self.assertIn('replacement_started=true', shell)
        self.assertIn('replacement.json', shell)
        self.assertIn('evidence_root=', shell)

    def test_custom_environment_and_resources_cannot_be_silently_dropped(self):
        image = {'Config': {'Env': ['PATH=/usr/bin'], 'Cmd':['run'],'Entrypoint':['init'],'User':'','WorkingDir':''}}
        current = {'Config': copy.deepcopy(image['Config']), 'HostConfig': {}}
        current['Config']['Env'] += ['MCPGIT_BOOTSTRAP_REMOTE_REPOS=', 'MCPGIT_BOOTSTRAP_REPO_SOURCES=none',
                                    'MCPGIT_ALLOWED_HOSTS=localhost,127.0.0.1,::1']
        state.supported_configuration(current, image)
        for change in ('environment','user','memory','security'):
            bad = copy.deepcopy(current)
            if change == 'environment': bad['Config']['Env'].append('MY_CUSTOM_SETTING=preserve-me')
            elif change == 'user': bad['Config']['User']='1000'
            elif change == 'memory': bad['HostConfig']['Memory']=512*1024*1024
            else: bad['HostConfig']['SecurityOpt']=['no-new-privileges']
            with self.subTest(change=change), self.assertRaises(state.InstallError):
                state.supported_configuration(bad,image)


if __name__ == '__main__':
    unittest.main()
