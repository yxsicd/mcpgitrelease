//! Run with rustc --test tests/exact_activation_reuse.rs.
use std::process::Command;
use std::{fs, os::unix::fs::PermissionsExt};

const CHECK: &str = r#"
import argparse,copy,importlib.util,pathlib,sys
spec=importlib.util.spec_from_file_location('state','scripts/install_state.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
current={'Id':'owned-id','Image':'owned-image','Config':{'Labels':{
 s.PREFIX+'manifest-sha256':'manifest',s.PREFIX+'instance-name':'agentlab-test',
 s.PREFIX+'instance-id':'organization'},'Env':['PRIVATE=not-printed']},
 'HostConfig':{'PortBindings':{'8001/tcp':[{'HostIp':'127.0.0.1','HostPort':'18105'}]},'Memory':0},
 'Mounts':[{'Destination':'/data'},{'Destination':'/config/mcpgit.toml'}], 'NetworkSettings':{'Networks':{'bridge':{}}},
 'State':{'Status':'running','Health':{'Status':'healthy'}},'RestartCount':0}
saved={'data_volume':'agentlab-test-data','port':'18105','netrc':'',
 'executable_build_repository':'tablegit','image_id':'owned-image','manifest_sha256':'manifest',
 'organization_id':'organization','config':str(pathlib.Path('config').resolve()),'credential_file':str(pathlib.Path('credential').resolve()),'hashes':{},
 'activation':{'container_id':'owned-id','configuration_sha256':s.activation_fingerprint(current),
 'config_sha256':'config-hash','credential_sha256':'credential-hash'}}
plan={'mode':'exact','saved':copy.deepcopy(saved)}
args=argparse.Namespace(plan='plan',instance='agentlab-test',volume='agentlab-test-data',port='18105',
 binding='127.0.0.1:18105:8001',netrc='',executable_build_repository='tablegit',organization_id='',config='config',credential='credential')
variant=sys.argv[1];digests={'config':'config-hash','credential':'credential-hash'}
if variant=='mount-order': current['Mounts'].reverse()
elif variant=='empty-bind':
    current['HostConfig']['PortBindings']['8001/tcp'][0]['HostIp']=''
    saved['activation']['configuration_sha256']=s.activation_fingerprint(current)
    plan['saved']=copy.deepcopy(saved);args.binding='18105:8001'
elif variant=='adoption': saved.pop('activation');plan['saved']=copy.deepcopy(saved)
elif variant=='program': plan['mode']='program'
elif variant=='port': args.port='18106';args.binding='127.0.0.1:18106:8001'
elif variant=='bind': args.binding='0.0.0.0:18105:8001'
elif variant=='volume': args.volume='another-volume'
elif variant=='credential': digests['credential']='changed'
elif variant=='config': digests['config']='changed'
elif variant=='container': current['Id']='replacement'
elif variant=='stopped': current['State']['Status']='exited'
elif variant=='unhealthy': current['State']['Health']['Status']='unhealthy'
elif variant=='restart': current['RestartCount']=1
elif variant=='resource': current['HostConfig']['Memory']=128
elif variant=='netrc': args.netrc='/unexpected'
elif variant=='build': args.executable_build_repository='other'
elif variant=='organization': current['Config']['Labels'][s.PREFIX+'instance-id']='wrong'
elif variant=='receipt': plan['saved']['port']='wrong'
elif variant=='requested-org': args.organization_id='other'
elif variant=='config-path': args.config='elsewhere'
elif variant=='credential-path': args.credential='elsewhere'
s.private_json=lambda path: plan if str(path)=='plan' else saved
s.inspect=lambda *args: current
s.sha=lambda path: digests[pathlib.Path(path).name]
s.private_credential=lambda path: None
s.run=lambda *args,**kwargs: 'organization'
s.probe=lambda *args,**kwargs: None
try: print('reuse' if s.reusable(args) else 'activate')
except s.InstallError: print('reject')
"#;

fn check(variant: &str, expected: &str) {
    let out = Command::new("python3")
        .args(["-c", CHECK, variant])
        .output()
        .unwrap();
    assert!(out.status.success(), "{variant}: {:?}", out);
    assert_eq!(
        String::from_utf8(out.stdout).unwrap().trim(),
        expected,
        "{variant}"
    );
}

#[test]
fn unchanged_healthy_qualified_activation_is_reused() {
    check("exact", "reuse");
    check("mount-order", "reuse");
    check("empty-bind", "reuse");
}

#[test]
fn changed_requested_or_effective_state_is_not_noop() {
    for variant in [
        "adoption",
        "program",
        "port",
        "bind",
        "volume",
        "credential",
        "config",
        "container",
        "stopped",
        "unhealthy",
        "restart",
        "resource",
        "netrc",
        "build",
    ] {
        check(variant, "activate");
    }
}

#[test]
fn identity_or_receipt_drift_rejects_before_activation() {
    for variant in [
        "organization",
        "receipt",
        "requested-org",
        "config-path",
        "credential-path",
    ] {
        check(variant, "reject");
    }
}

#[test]
fn real_credential_mode_is_required_not_just_unchanged_bytes() {
    struct Owned(std::path::PathBuf);
    impl Drop for Owned {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
    let owned =
        Owned(std::env::temp_dir().join(format!("mcpgit-private-mode-{}", std::process::id())));
    fs::create_dir(&owned.0).unwrap();
    fs::set_permissions(&owned.0, fs::Permissions::from_mode(0o700)).unwrap();
    let file = owned.0.join("dummy-credential");
    fs::write(&file, b"not-a-real-key").unwrap();
    for (mode, expected) in [(0o600, true), (0o644, false)] {
        fs::set_permissions(&file, fs::Permissions::from_mode(mode)).unwrap();
        let out = Command::new("python3").args(["-c", "import importlib.util,sys; spec=importlib.util.spec_from_file_location('state','scripts/install_state.py'); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s); s.private_credential(sys.argv[1])"]).arg(&file).output().unwrap();
        assert_eq!(out.status.success(), expected, "{mode:o}");
        assert!(out.stdout.is_empty());
        assert!(!String::from_utf8_lossy(&out.stderr).contains("not-a-real-key"));
    }
}
