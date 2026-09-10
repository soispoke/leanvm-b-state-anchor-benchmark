"""Independent checks of note/state binding and unchanged trie semantics."""
import ast
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from eth_utils import keccak
import analyze_fixtures as reference
from owner_state import relation
from real_state import statement


class OwnerRelationTests(unittest.TestCase):
    def test_inclusion_code_matches_preserved_relation(self):
        def code(path):
            tree=ast.parse(Path(path).read_text())
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='inclusion')
            return ast.dump(node,include_attributes=False)
        self.assertEqual(code(relation.__file__),code(statement.__file__))

    def test_rejects_wrong_secret_lengths_before_compilation(self):
        for length in (0,1,31,33,64):
            with self.subTest(length=length),self.assertRaisesRegex(ValueError,'exactly 32'):
                relation.build('direct',{},secret=bytes(length))

    def test_exact_public_encoding_and_same_address_binding_in_small_fixture(self):
        # A native-generated one-account, one-storage-leaf tree. Both owner
        # openings use the same shape and therefore must compile identically.
        from real_state.test_statement import compact,key_nibbles
        address=bytes(range(20));slot=bytes(32);value=b'\x01'
        storage=reference.rlp_encode([compact(key_nibbles(keccak(slot))),reference.rlp_encode(value)])
        storage_root=keccak(storage)
        record=reference.rlp_encode([b'',b'',storage_root,keccak(b'')])
        account=reference.rlp_encode([compact(key_nibbles(keccak(address))),record])
        state_root=keccak(account)
        fixture={'block':{'stateRoot':'0x'+state_root.hex()}}
        ap={'address':'0x'+address.hex(),'accountProof':['0x'+account.hex()]}
        sp={'key':'0x0','value':'0x1','proof':['0x'+storage.hex()]}
        profile={
            'account':{'nodes':[statement.shape(reference.rlp_decode(account))],'odd_paths':[False]},
            'storage':{'nodes':[statement.shape(reference.rlp_decode(storage))],'odd_paths':[False]},
            'account_value':statement.shape(reference.rlp_decode(record)),
            'storage_value':statement.shape(value),
        }
        for variant in ('baseline','cse_dce','hybrid'):
            first_ops=None
            with patch.object(relation,'load_fixture',return_value=(fixture,ap,sp)):
                for secret in (bytes(32),bytes([255])*32):
                    c,meta=relation.build('direct',profile,variant=variant,secret=secret)
                    note=keccak(address+secret)
                    expected=keccak(b'LVMOWNER1'+b'\0'+state_root+note+slot)
                    self.assertEqual(meta['note_commitment'],'0x'+note.hex())
                    self.assertEqual(meta['public_digest'],'0x'+expected.hex())
                    c.finalize()
                    self.assertEqual(b''.join(v.to_bytes(16,'little') for v in c.values[:2]),expected)
                    if first_ops is None:first_ops=bytes(c.ops)
                    else:self.assertEqual(first_ops,c.ops)


if __name__=='__main__':unittest.main()
