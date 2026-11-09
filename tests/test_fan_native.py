import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'packages/resmonpro/app'))
import fan_native

class NativeFanTests(unittest.TestCase):
    def test_unknown_frontend_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            web=Path(directory);(web/'assets').mkdir()
            (web/'index.html').write_text('<script src="/assets/index-test.js"></script>')
            (web/'assets/index-test.js').write_text('export const unknown=true;')
            with self.assertRaises(ValueError):fan_native.module(web)
    def test_control_protocol(self):
        # Test our appended adapter only, without including or executing fnOS code.
        tree=ast.parse(Path(fan_native.__file__).read_text())
        fragment=next(node.value.value for node in ast.walk(tree) if isinstance(node,ast.AugAssign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str) and 'function fanResult' in node.value.value)
        fragment=fragment[fragment.index('function fanResult'):]
        with tempfile.TemporaryDirectory() as directory:
            module=Path(directory)/'contract.mjs'
            module.write_text('let client;export function useClient(c){client=c;}async function fanClient(){return client;}\n'+fragment)
            subprocess.run(['node',str(Path(__file__).with_name('fan_native_contract.mjs'))],env={**os.environ,'FAN_CONTRACT':module.as_uri()},check=True)

if __name__=='__main__':unittest.main()
