import unittest
from deliver import INTERNAL_IMAGE, argo_ready, require_promotion


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


if __name__ == '__main__':
    unittest.main()
