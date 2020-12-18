from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from django.contrib.staticfiles.storage import staticfiles_storage

from ctfpad import views


app_name = "ctfpad"

urlpatterns = [
    # /
    path("", views.index, name="home"),
    path("favicon.ico", RedirectView.as_view(url=staticfiles_storage.url('static/images/favicon.ico'))),

    # team
    ## create
    path("teams/register/", views.teams.TeamCreateView.as_view(), name="team-register"),
    path("teams/edit/<int:pk>", views.teams.TeamUpdateView.as_view(), name="team-edit"),
    path("teams/delete/", views.teams.TeamDeleteView.as_view(), name="team-delete"),

    # user
    path("users/", views.users.MemberListView.as_view(), name="users-list"),
    path("users/add/", views.users.MemberCreateView.as_view(), name="users-register"),
    path("users/delete/<int:pk>/", views.users.MemberDeleteView.as_view(), name="users-delete"),
    path("users/edit/<int:pk>/", views.users.MemberUpdateView.as_view(), name="users-update"),
    path("users/edit/advanced/<int:pk>/", views.users.UserUpdateView.as_view(), name="users-update-advanced"),
    path("users/edit/change-password/", views.users.UserPasswordUpdateView.as_view(), name="users-update-password"),
    path("users/<int:pk>/", views.users.MemberDetailView.as_view(), name="users-detail"),
    path("users/<int:pk>/select-ctf/", views.users.MemberMarkAsSelectedView.as_view(), name="users-select"),

    path("users/login/", views.users.CtfpadLogin.as_view(), name="user-login"),
    path("users/logout/", views.users.logout, name="user-logout"),
    path("users/reset/", views.users.UserResetPassword.as_view(), name="user-password-reset"),
    path("users/reset/confirm/<str:uidb64>/<str:token>/", views.users.UserChangePassword.as_view(), name="user-password-change"),

    # dashboard
    path("dashboard/", views.dashboard, name="dashboard"),

    # search
    path("search/", views.search, name="search"),

    # stats
    path("stats/", views.generate_stats, name="stats-detail"),

    # toggle dark mode
    path("toggle-theme/", views.toggle_dark_mode, name="set-dark-mode"),

    # ctf
    path("ctfs/", views.ctfs.CtfListView.as_view(), name="ctfs-list"),
    path("ctfs/create/", views.ctfs.CtfCreateView.as_view(), name="ctfs-create"),
    path("ctfs/import/", views.ctfs.CtfImportView.as_view(), name="ctfs-import"),
    path("ctfs/<uuid:pk>/", views.ctfs.CtfDetailView.as_view(), name="ctfs-detail"),
    path("ctfs/<uuid:pk>/edit/", views.ctfs.CtfUpdateView.as_view(), name="ctfs-edit"),
    path("ctfs/<uuid:pk>/delete/", views.ctfs.CtfDeleteView.as_view(), name="ctfs-delete"),
    path("ctfs/<uuid:pk>/export-notes/", views.ctfs.CtfExportNotesView.as_view(), name="ctfs-export-notes"),

    # challenges
    path("challenges/", views.challenges.ChallengeListView.as_view(), name="challenges-list"),
    path("challenges/create/", views.challenges.ChallengeCreateView.as_view(), name="challenges-create"),
    path("challenges/create/<uuid:ctf>/", views.challenges.ChallengeCreateView.as_view(), name="challenges-create"),
    path("challenges/<uuid:pk>/", views.challenges.ChallengeDetailView.as_view(), name="challenges-detail"),
    path("challenges/<uuid:pk>/edit/", views.challenges.ChallengeUpdateView.as_view(), name="challenges-edit"),
    path("challenges/<uuid:pk>/delete/", views.challenges.ChallengeDeleteView.as_view(), name="challenges-delete"),
    path("challenges/<uuid:pk>/score/", views.challenges.ChallengeSetFlagView.as_view(), name="challenges-score"),

    # files
    path("challenges/<uuid:challenge_id>/files/add/", views.files.ChallengeFileCreateView.as_view(), name="challenge-files-add"),
    path("challenges/<uuid:challenge_id>/files/<uuid:pk>/", views.files.ChallengeFileDetailView.as_view(), name="challenge-files-detail"),
    path("challenges/<uuid:challenge_id>/files/<uuid:pk>/delete/", views.files.ChallengeFileDeleteView.as_view(), name="challenge-files-delete"),

    # categories
    path("categories/create/", views.categories.CategoryCreateView.as_view(), name="categories-create"),

    # tags
    path("tags/create/", views.tags.TagCreateView.as_view(), name="tags-create"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.CTF_CHALLENGE_FILE_URL, document_root=settings.CTF_CHALLENGE_FILE_ROOT)