# -*- coding: utf-8 -*-
"""Views of the app."""
# pylint: disable=no-name-in-module,import-error
from flask import Blueprint, render_template
from flask.ext.login import login_required

blueprint = Blueprint("user", __name__, url_prefix='/users', static_folder="../static")  # pylint: disable=invalid-name


@blueprint.route("/")
@login_required
def members():
    """List members."""
    return render_template("users/members.html")
