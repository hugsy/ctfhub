from typing import Union
from django.test import SimpleTestCase
from ctfhub.forms import ChallengeCreateForm, ChallengeUpdateForm


class TestForms(SimpleTestCase):
    def test_challenge_create_required_fields(self):
        required_fields: dict[str, Union[str, int]] = {
            "name": "fake name",
            "points": 100,
        }

        optional_fields: dict[str, Union[str, int]] = {
            "description": "fake",
            "category": "fake",
        }

        for required_field, _ in required_fields.items():
            data = optional_fields | required_fields
            del data[required_field]
            form = ChallengeCreateForm(data=data)
            self.assertFalse(form.is_valid())

    def test_challenge_create_manual_has_no_note_id(self):
        """
        @ref #91
        """
        form = ChallengeCreateForm()
        self.assertNotIn("note_id", form.fields)

    def test_challenge_update_has_always_note_id(self):
        """
        @ref #91
        """
        form = ChallengeUpdateForm()
        self.assertIn("note_id", form.fields)
