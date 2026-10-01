import unittest
from tests import test_web


class SkillWebTests(unittest.TestCase):
    setUp=test_web.WebTests.setUp
    close=test_web.WebTests.close
    request=test_web.WebTests.request
    api=test_web.WebTests.api

    def test_project_skill_routes_are_authenticated_private_and_roundtrip(self):
        project_id=self.app.data['selected_project']
        path='/api/projects/'+project_id+'/skills'
        self.assertEqual(self.request(path,auth=False)[0],401)
        initial=self.api(path)
        self.assertTrue(initial['skills']);self.assertIn('overrides',initial);self.assertIn('vision',initial)
        custom=self.api(path,{'action':'save_custom','id':'brand_rules','title':'Brand rules','triggers':['brand copy'],
                              'body':'Use concise premium brand copy and preserve the established visual voice without invented claims.'})
        self.assertTrue(any(item['id']=='brand_rules' for item in custom['skills']))
        configured=self.api(path,{'action':'overrides','enabled':['brand_rules'],'disabled':['visual_design'],'vision_review':False})
        self.assertEqual(configured['overrides']['enabled'],['brand_rules'])
        self.assertEqual(configured['overrides']['disabled'],['visual_design'])
        self.assertNotIn('api_key',str(configured).lower())
        deleted=self.api(path,{'action':'delete_custom','id':'brand_rules'})
        self.assertFalse(any(item['id']=='brand_rules' for item in deleted['skills']))


if __name__=='__main__': unittest.main()
