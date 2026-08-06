import os

from django.shortcuts import render, redirect
from django.http import Http404
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.utils.translation import gettext_lazy as _

from bugsink.app_settings import get_settings
from bugsink.conf_utils import deduce_mcp_url
from bugsink.decorators import atomic_for_request_method

from .models import AuthToken


# matches the run_mcp_server default; the Docker image overrides both via MCP_PORT
MCP_PORT = os.environ.get("MCP_PORT", "8100")


@atomic_for_request_method
@user_passes_test(lambda u: u.is_superuser)
def auth_token_list(request):
    auth_tokens = AuthToken.objects.all()

    if request.method == 'POST':
        full_action_str = request.POST.get('action')
        action, pk = full_action_str.split(":", 1)
        if action == "delete":
            AuthToken.objects.filter(pk=pk).delete()

            messages.success(request, _('Token deleted'))
            return redirect('auth_token_list')

        elif action == "update_description":
            auth_token = AuthToken.objects.get(pk=pk)
            auth_token.description = request.POST.get(f'description-{pk}', '')[:255]
            auth_token.save()

            messages.success(request, _('Description updated'))
            return redirect('auth_token_list')

    return render(request, 'bsmain/auth_token_list.html', {
        'auth_tokens': auth_tokens,
    })


@user_passes_test(lambda u: u.is_superuser)
def mcp_connect(request):
    return render(request, 'bsmain/mcp_connect.html', {
        'mcp_url': deduce_mcp_url(get_settings().BASE_URL, get_settings().MCP_URL, MCP_PORT),
    })


@atomic_for_request_method
@user_passes_test(lambda u: u.is_superuser)
def auth_token_create(request):
    if request.method != 'POST':
        raise Http404("Invalid request method")

    AuthToken.objects.create()

    return redirect("auth_token_list")
