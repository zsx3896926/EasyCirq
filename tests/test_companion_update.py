import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def module(name, file):
    spec=importlib.util.spec_from_file_location(name, ROOT/'design-hardware/scripts'/file)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
c=module('companion_test','companion_update.py')
u=module('companion_manager_test','skill_update.py')

class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.exe=self.root/'easyeda.exe'; self.exe.write_bytes(b'old CLI binary')
        self.home=self.root/'home'
        self.target=self.home/'.claude/skills/easyeda-agent'
        self.target.mkdir(parents=True)
        (self.target/'SKILL.md').write_text('old companion skill')
        self.ready={'mode':'check','cliVersion':'v1.14.0','target':'v1.14.0','ready':True,
                    'behind':0,'mismatched':0,'unverified':0,'connector':{'status':'compatible'}}
        self.behind=dict(self.ready,ready=False,behind=1)
        self.envpatch=patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(self.home/'.claude')})
        self.envpatch.start(); self.addCleanup(self.envpatch.stop)

    def test_native_check_is_readonly_and_does_not_start_daemon(self):
        with patch.object(c,'run',return_value=(0,self.ready)) as call:
            r=c.check('claude',self.home,self.exe)
        args=call.call_args.args
        self.assertIn('--check',args[1]); self.assertIn('--exit-code',args[1])
        self.assertEqual(args[2]['EASYEDA_NO_AUTOSTART'],'1')
        self.assertEqual(r['status'],'current')
        self.assertEqual(self.exe.read_bytes(),b'old CLI binary')

    def test_difference_exit10_is_attention_not_command_failure(self):
        with patch.object(c,'run',return_value=(10,self.behind)):
            self.assertEqual(c.check('claude',self.home,self.exe)['status'],'needs_attention')

    def test_network_failure_never_means_current(self):
        with patch.object(c,'run',return_value=(1,dict(self.ready,latestError='offline'))):
            self.assertEqual(c.check('claude',self.home,self.exe)['status'],'unverified')

    def test_ready_true_cannot_hide_missing_checks(self):
        with patch.object(c,'run',return_value=(0,dict(self.ready,unverified=1))):
            self.assertNotEqual(c.check('claude',self.home,self.exe)['status'],'current')

    def test_connector_import_remains_explicit(self):
        with patch.object(c,'run',return_value=(10,dict(self.behind,connector={'status':'behind'}))):
            r=c.check('claude',self.home,self.exe)
        self.assertTrue(r['connector_requires_manual_action'])
        self.assertFalse(r['connector_automatic_install'])

    def test_workbuddy_uses_official_config_override(self):
        native,target,env=c.client_config('workbuddy',self.home)
        self.assertEqual(native,'claude')
        self.assertEqual(target,self.home/'.workbuddy/skills/easyeda-agent')
        self.assertEqual(env['CLAUDE_CONFIG_DIR'],str(self.home/'.workbuddy'))
        self.assertNotEqual(os.environ['CLAUDE_CONFIG_DIR'],env['CLAUDE_CONFIG_DIR'])

    def test_duplicate_codex_skills_refused(self):
        for folder in ['.agents','.codex']:
            p=self.home/folder/'skills/easyeda-agent';p.mkdir(parents=True);(p/'SKILL.md').write_text('old')
        with patch.object(c,'run',side_effect=AssertionError('should not run')):
            r=c.check('codex',self.home,self.exe)
        self.assertEqual(r['status'],'unverified')

    def test_missing_cli(self):
        with patch.object(c,'executable',return_value=None):
            self.assertEqual(c.check('claude',self.home)['status'],'not_installed')

    def test_idle_required_before_mutations(self):
        with patch.object(c,'run',side_effect=AssertionError('no execution')):
            with self.assertRaises(ValueError): c.update('claude',self.home,self.root/'backups',self.exe)

    def test_successful_delegated_update_keeps_backup_and_pins_target(self):
        with patch.object(c,'run',side_effect=[(10,self.behind),(0,{'mode':'apply'}),(0,self.ready)]) as call:
            r=c.update('claude',self.home,self.root/'backups',self.exe,idle=True)
        self.assertEqual(r['status'],'complete')
        backup=Path(r['backup'])
        self.assertEqual((backup/'easyeda.exe').read_bytes(),b'old CLI binary')
        self.assertEqual((backup/'easyeda-agent/SKILL.md').read_text(),'old companion skill')
        argv=call.call_args_list[1].args[1]
        self.assertIn('--restart-daemon=false',argv)
        self.assertEqual(argv[argv.index('--version')+1],'1.14.0')
        self.assertNotIn('--force',argv)

    def test_postcheck_stale_daemon_is_not_success(self):
        with patch.object(c,'run',side_effect=[(10,self.behind),(0,{}),(10,dict(self.behind,connector={'status':'mismatch'}))]):
            r=c.update('claude',self.home,self.root/'backups',self.exe,idle=True)
        self.assertFalse(r['updated']);self.assertEqual(r['status'],'needs_attention')

    def test_timeout_keeps_backup_and_partial_record(self):
        with patch.object(c,'run',side_effect=[(10,self.behind),ValueError('timeout')]):
            r=c.update('claude',self.home,self.root/'backups',self.exe,idle=True)
        self.assertEqual(r['status'],'partial_or_unverified')
        self.assertTrue((Path(r['backup'])/'operation.json').exists())

    def test_shared_cli_lock_blocks_other_client_updates(self):
        (self.exe.parent/'.hardware-easyeda-update.lock').write_text('{"pid":123}')
        with patch.object(c,'run',side_effect=AssertionError('must not run')):
            with self.assertRaises(ValueError):
                c.update('claude',self.home,self.root/'backups',self.exe,idle=True)

    def test_unknown_preflight_prevents_mutation(self):
        with patch.object(c,'check',return_value={'status':'unverified'}):
            r=c.update('claude',self.home,self.root/'backups',self.exe,idle=True)
        self.assertEqual(r['status'],'blocked');self.assertFalse((self.root/'backups').exists())

    def test_noop_does_not_backup_or_restart(self):
        with patch.object(c,'run',return_value=(0,self.ready)) as call:
            r=c.update('claude',self.home,self.root/'backups',self.exe,idle=True)
        self.assertEqual(r['status'],'already_current');self.assertEqual(call.call_count,1)

    def test_own_release_failure_does_not_hide_companion_check(self):
        stub=unittest.mock.Mock();stub.check.return_value={'status':'current'}
        target=self.home/'.claude/skills/design-hardware'
        with patch.object(u,'check',side_effect=OSError('no formal release')),patch.object(u,'companion_module',return_value=stub):
            r=u.check_all(target,'claude',self.home,refresh=True)
        self.assertEqual(r['design_hardware']['status'],'unverified')
        self.assertEqual(r['easyeda_agent']['status'],'current');self.assertEqual(stub.check.call_count,1)

    def test_cli_partial_dependency_upgrade_has_nonzero_exit(self):
        stub=unittest.mock.Mock();stub.update.return_value={'status':'needs_attention'}
        target=self.home/'.claude/skills/design-hardware'
        with patch.object(u,'companion_module',return_value=stub):
            result=u.main(['update-agent','--client','claude','--home',str(self.home),'--target',str(target),'--idle'])
        self.assertEqual(result,1)

    def test_check_all_never_installs(self):
        stub=unittest.mock.Mock();stub.check.return_value={'status':'needs_attention'}
        target=self.home/'.claude/skills/design-hardware'
        with patch.object(u,'check',return_value={'status':'update_available'}),patch.object(u,'companion_module',return_value=stub):
            r=u.check_all(target,'claude',self.home,refresh=True)
        stub.update.assert_not_called();self.assertFalse(r['automatic_install'])

if __name__=='__main__': unittest.main()
