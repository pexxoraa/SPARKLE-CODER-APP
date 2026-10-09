"""Conversation identity, revisions, fork isolation and automatic chat titles."""
import tempfile
import unittest
from pathlib import Path

from sparkle_coder.chat_titles import chat_title
from sparkle_coder.state import Session
from sparkle_coder.workspace import Workspace


class ChatBranchingTests(unittest.TestCase):
    def test_useful_titles_without_provider_calls(self):
        self.assertEqual(chat_title('Please build a static website for a photo studio.'), 'Static website for a photo studio')
        self.assertEqual(chat_title('What are SQLite tradeoffs?'), 'SQLite tradeoffs')
        self.assertEqual(chat_title(''), 'New conversation')
        self.assertLessEqual(len(chat_title('Develop a project ' + 'feature ' * 500)), 62)
        self.assertNotIn('https://', chat_title('Check https://example.com private endpoint'))

    def test_revise_turn_preserves_session_identity_and_file_journal(self):
        with tempfile.TemporaryDirectory() as root:
            workspace=Workspace(Path(root))
            session=Session.create(workspace,'Build a photo studio website',[],{})
            session.state['messages'].extend([
                {'role':'assistant','content':'First response'},
                {'role':'user','content':'Add a gallery'},
                {'role':'assistant','content':'Second response'}])
            session.state['user_requests'].append('Add a gallery')
            session.state['visible_message_indices']=[1,3]
            session.state['journal']=[{'path':'index.html','applied':True,'before':None,'after':'hash','backup':None}]
            session.state['usage']['calls']=12
            session.save()
            old_id=session.id
            session.revise_message(2,'Add a gallery','Add a gallery with filters')
            self.assertEqual(session.id,old_id)
            self.assertEqual(session.state['messages'][-1],{'role':'user','content':'Add a gallery with filters'})
            self.assertEqual(len(session.state['messages']),3)
            self.assertEqual(session.state['user_requests'],['Build a photo studio website','Add a gallery with filters'])
            self.assertEqual(session.state['visible_message_indices'],[1])
            self.assertEqual(session.state['usage']['calls'],12)
            self.assertEqual(len(session.state['journal']),1)
            self.assertEqual(len(session.state['message_revisions']),1)
            with self.assertRaisesRegex(ValueError,'message changed'):
                session.revise_message(2,'Add a gallery','Send a duplicate revision')
            loaded=Session.load(workspace,old_id)
            self.assertEqual(loaded.state['messages'][-1]['content'],'Add a gallery with filters')
            loaded.revise_message(0,'Build a photo studio website','Build a bakery ecommerce site')
            self.assertEqual(loaded.state['title'],'Bakery ecommerce site')
            self.assertEqual(len(loaded.state['journal']),1)
            self.assertEqual(loaded.state['goal'],'Build a bakery ecommerce site')

    def test_invalid_indices_and_assistant_revisions_denied(self):
        with tempfile.TemporaryDirectory() as root:
            s=Session.create(Workspace(Path(root)),'Start project',[],{})
            with self.assertRaises(ValueError):s.revise_message(99,'Start project','New')
            with self.assertRaises(ValueError):s.revise_message(True,'Start project','New')
            s.state['messages'].append({'role':'assistant','content':'Hi'})
            s.state['visible_message_indices']=[1]
            with self.assertRaisesRegex(ValueError,'message changed'):
                s.revise_message(1,'Hi','Rewrite another author')
