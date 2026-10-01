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
        self.assertEqual(selected[:3],['static_web','visual_design','photography_portfolio'])
        self.assertIn('responsive_web',selected)
        self.assertIn('visual_qa',selected)
        self.assertLessEqual(len(selected),6)

    def test_skill_payload_is_bounded_and_rejects_placeholder_design(self):
        selected=select_skills('build a static website for a photo studio',task_profile='simple_web')
        text=render_skills(selected,char_budget=9000)
        self.assertLessEqual(len(text),9000)
        self.assertIn('via.placeholder.com',text)
        self.assertIn('One excellent core page',text)
        self.assertNotIn('database',text.lower())

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


if __name__=='__main__': unittest.main()
