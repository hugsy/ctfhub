from django.contrib.auth.mixins import AccessMixin


class RequireSuperPowersMixin(AccessMixin):
    """Verify that the current user has super powers."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.member.has_superpowers:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)