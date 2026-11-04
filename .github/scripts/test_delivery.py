import unittest
from unittest.mock import patch
from deliver import INTERNAL_IMAGE, argo_ready, fetch_vault_credentials, require_promotion


class PromotionSafety(unittest.TestCase):
    def test_unbuilt_main_tree_cannot_be_promoted(self):
        with self.assertRaisesRegex(RuntimeError, 'differs'):
            require_promotion({'sourceTree':'develop-tree','verified':True,'digest':'sha256:'+'a'*64}, 'different-main-tree')

    def test_failed_develop_rollout_cannot_be_promoted(self):
        with self.assertRaisesRegex(RuntimeError, 'verification'):
            require_promotion({'sourceTree':'same-tree','verified':False,'digest':'sha256:'+'a'*64}, 'same-tree')

    def test_successful_promotion_preserves_exact_digest(self):
        digest = 'sha256:'+'a'*64
        self.assertEqual(require_promotion({'sourceTree':'same-tree','verified':True,'digest':digest}, 'same-tree'), INTERNAL_IMAGE+'@'+digest)

    def test_healthy_old_version_does_not_complete_new_deployment(self):
        application={'status':{'sync':{'status':'Synced'},'health':{'status':'Healthy'},'summary':{'images':['old-image']}}}
        self.assertFalse(argo_ready(application, 'new-image'))


class VaultAccess(unittest.TestCase):
    def setUp(self):
        self.environment=patch.dict('os.environ',{'VAULT_ADDR':'https://vault.apps.okd.lab.home.arpa','ACTIONS_ID_TOKEN_REQUEST_URL':'https://github.invalid/token?job=check','ACTIONS_ID_TOKEN_REQUEST_TOKEN':'test-request-token'},clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @patch('deliver.mask')
    @patch('deliver.request_json')
    def test_main_reads_only_shared_credentials_and_revokes_token(self, request, mask):
        request.side_effect=[{'value':'signed-jwt'},{'auth':{'client_token':'vault-token'}},{'data':{'data':{'infra_ssh_key':'test-key','argo_read_token':'read-only-token'}}},{}]
        fetch_vault_credentials('main')
        urls=[call.args[0] for call in request.call_args_list]
        self.assertFalse(any('/ci/testhttp/develop' in url for url in urls))
        self.assertTrue(urls[-1].endswith('/auth/token/revoke-self'))
        self.assertEqual(request.call_args_list[1].args[1]['role'],'testhttp-main')

    @patch('deliver.mask')
    @patch('deliver.request_json')
    def test_vault_token_is_revoked_even_when_secret_read_fails(self, request, mask):
        request.side_effect=[{'value':'signed-jwt'},{'auth':{'client_token':'vault-token'}},RuntimeError('HTTP 403'),{}]
        with self.assertRaisesRegex(RuntimeError,'403'):
            fetch_vault_credentials('develop')
        self.assertTrue(request.call_args_list[-1].args[0].endswith('/auth/token/revoke-self'))


if __name__ == '__main__':
    unittest.main()
