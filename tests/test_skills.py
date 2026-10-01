from pathlib import Path
import tempfile
import unittest

from sparkle_coder.agent import Agent
from sparkle_coder.config import Config
from sparkle_coder.efficiency import task_profile
from sparkle_coder.skills import render_skills, select_skills
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


class SkillRoutingTests(unittest.TestCase):
    def test_photo_studio_selects_design_domain_and_quality_skills(self):
        goal='build a static website for a photo studio'
        profile=task_profile(goal)
        self.assertEqual(profile['name'],'simple_web')
        self.assertLessEqual(profile['max_total_tokens'],50000)
        selected=select_skills(goal,task_profile=profile['name'])
        self.assertEqual(selected[:5],['photography_portfolio','composition_mastery','typography_mastery','image_art_direction','portfolio_curation'])
        self.assertIn('asset_sourcing',selected)
        self.assertIn('responsive_web',selected)
        self.assertIn('conversion_journey',selected)
        self.assertIn('content_integrity',selected)
        self.assertIn('visual_qa',selected)
        self.assertLessEqual(len(selected),10)

    def test_skill_payload_is_bounded_and_rejects_placeholder_design(self):
        selected=select_skills('build a static website for a photo studio',task_profile='simple_web')
        text=render_skills(selected,char_budget=16000)
        self.assertLessEqual(len(text),16000)
        for skill in selected:self.assertIn('SKILL: '+skill,text)
        self.assertIn('search_assets',text)
        self.assertIn('via.placeholder.com',text)
        self.assertIn('visual composition',text)
        self.assertIn('Typography Mastery',text)
        self.assertNotIn('database',text.lower())

    def test_small_skill_budget_still_represents_every_selected_skill(self):
        selected=select_skills('build a static website for a photo studio',task_profile='simple_web')
        text=render_skills(selected,char_budget=2200)
        self.assertLessEqual(len(text),2200)
        for skill in selected:self.assertIn('SKILL: '+skill,text)

    def test_agent_context_injects_only_selected_skills(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace=Workspace(Path(folder))
            session=Session.create(workspace,'build a static website for a photo studio',[],{})
            agent=Agent(workspace,session,Config(auto_approve=True),object(),lambda _:True,lambda _:None)
            system=agent.context()[0]['content']
            self.assertIn('SELECTED TASK SKILLS',system)
            self.assertIn('SKILL: photography_portfolio',system)
            self.assertIn('technical solution small',system)
            self.assertNotIn('SKILL: database',system)
            self.assertEqual(session.state['skills'],agent.skills)

    def test_engineering_prompts_route_to_specialist_mastery(self):
        cases={
            'fix a Python parsing bug':['debugging_mastery','python_mastery','testing_mastery'],
            'review and secure the backend API authentication':['backend_api_mastery','security_mastery'],
            'optimize slow PostgreSQL database queries':['database_mastery','performance_engineering'],
            'refactor a TypeScript frontend with failing tests':['javascript_typescript_mastery','refactoring_mastery','testing_mastery'],
            'redeploy the Cloudflare worker and verify production':['deployment_mastery'],
        }
        for prompt,expected in cases.items():
            with self.subTest(prompt=prompt):
                selected=select_skills(prompt,task_profile='standard')
                for skill in expected:self.assertIn(skill,selected)
                self.assertLessEqual(len(selected),10)

    def test_vertical_web_prompts_route_to_domain_specific_skills(self):
        cases={
            'build a landing page for a SaaS analytics platform':'saas_landing',
            'build a website for an Italian restaurant':'restaurant_hospitality',
            'build an ecommerce storefront for a fashion shop':'ecommerce_storefront',
            'build a website for a creative agency':'agency_portfolio',
            'build a real estate website for property listings':'real_estate',
            'build a personal portfolio for a designer':'personal_portfolio',
        }
        for prompt,skill in cases.items():
            with self.subTest(prompt=prompt):
                selected=select_skills(prompt,task_profile='simple_web')
                self.assertIn(skill,selected)
                self.assertIn('visual_qa',selected)
                self.assertLessEqual(len(selected),10)


if __name__=='__main__': unittest.main()
