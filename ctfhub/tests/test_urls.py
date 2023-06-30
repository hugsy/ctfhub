from django.test import SimpleTestCase
from django.urls import resolve
from ctfhub.views import (
    index,
    teams,
    users,
    dashboard,
    search,
    generate_stats,
    ctfs,
    challenges,
    files,
    categories,
    tags,
)


class UrlsTest(SimpleTestCase):
    def test_home_url_resolves(self):
        url = "/"
        self.assertEqual(resolve(url).func, index)

    def test_teams_register_url_resolves(self):
        url = "/teams/register/"
        self.assertEqual(resolve(url).func.view_class, teams.TeamCreateView)

    def test_teams_edit_url_resolves(self):
        url = "/teams/edit/1"
        self.assertEqual(resolve(url).func.view_class, teams.TeamUpdateView)

    # Add tests for other team URLs

    def test_users_list_url_resolves(self):
        url = "/users/"
        self.assertEqual(resolve(url).func.view_class, users.MemberListView)

    def test_users_add_url_resolves(self):
        url = "/users/add/"
        self.assertEqual(resolve(url).func.view_class, users.MemberCreateView)

    # Add tests for other user URLs

    def test_dashboard_url_resolves(self):
        url = "/dashboard/"
        self.assertEqual(resolve(url).func, dashboard)

    def test_search_url_resolves(self):
        url = "/search/"
        self.assertEqual(resolve(url).func, search)

    def test_stats_url_resolves(self):
        url = "/stats/"
        self.assertEqual(resolve(url).func, generate_stats)

    # Add tests for other stats URLs

    def test_ctfs_list_url_resolves(self):
        url = "/ctfs/"
        self.assertEqual(resolve(url).func.view_class, ctfs.CtfListView)

    # Add tests for other CTF URLs

    def test_challenges_list_url_resolves(self):
        url = "/challenges/"
        self.assertEqual(resolve(url).func.view_class, challenges.ChallengeListView)

    # Add tests for other challenge URLs

    def test_files_add_url_resolves(self):
        url = "/challenges/<uuid:challenge_id>/files/add/"
        self.assertEqual(resolve(url).func.view_class, files.ChallengeFileCreateView)

    # Add tests for other file URLs

    def test_categories_create_url_resolves(self):
        url = "/categories/create/"
        self.assertEqual(resolve(url).func.view_class, categories.CategoryCreateView)

    def test_tags_list_url_resolves(self):
        url = "/tags/"
        self.assertEqual(resolve(url).func.view_class, tags.TagListView)

    # Add tests for other tag URLs

    # Add more tests for other URLs in your `urls.py` file
