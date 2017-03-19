# -*- coding: utf-8 -*-
"""Public section, including homepage and signup."""
# pylint: disable=no-name-in-module,import-error
from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.ext.login import login_required, login_user, logout_user
from sqlalchemy import Numeric
from sqlalchemy.orm import aliased

from tegenaria_web.extensions import db, login_manager
from tegenaria_web.flask_table_ex import Col, DateCol, Table
from tegenaria_web.models import Apartment, Distance, Opinion, Pin
from tegenaria_web.public.forms import ApartmentSearchForm, LoginForm
from tegenaria_web.user.forms import RegisterForm
from tegenaria_web.user.models import User
from tegenaria_web.utils import flash_errors

blueprint = Blueprint('public', __name__, static_folder="../static")  # pylint: disable=invalid-name
MAPS_PLACE_URL = 'https://www.google.de/maps/place/{address}/'
MAPS_DIRECTIONS_URL = 'https://www.google.de/maps/dir/{origin}/{destination}/'


@login_manager.user_loader
def load_user(id):  # pylint: disable=redefined-builtin
    """Load user by ID."""
    return User.get_by_id(int(id))


@blueprint.route("/", methods=["GET", "POST"])
def home():
    """Home page."""
    form = LoginForm(request.form)
    # Handle logging in
    if request.method == 'POST':
        if form.validate_on_submit():
            login_user(form.user)
            flash("You are logged in.", 'success')
            redirect_url = request.args.get("next") or url_for("user.members")
            return redirect(redirect_url)
        else:
            flash_errors(form)
    return render_template("public/home.html", form=form)


@blueprint.route('/logout/')
@login_required
def logout():
    """Logout page."""
    logout_user()
    flash('You are logged out.', 'info')
    return redirect(url_for('public.home'))


@blueprint.route("/register/", methods=['GET', 'POST'])
def register():
    """Register user page."""
    form = RegisterForm(request.form, csrf_enabled=False)
    if form.validate_on_submit():
        User.create(username=form.username.data, email=form.email.data,
                    password=form.password.data, active=True)
        flash("Thank you for registering. You can now log in.", 'success')
        return redirect(url_for('public.home'))
    else:
        flash_errors(form)
    return render_template('public/register.html', form=form)


@blueprint.route("/about/")
def about():
    """About page."""
    form = LoginForm(request.form)
    return render_template("public/about.html", form=form)


class ApartmentTable(Table):

    """An HTML table for the apartments."""

    classes = ['table-bordered', 'table-striped']
    allow_sort = True
    opinions = {}

    title = Col(
        'Title',
        cell=lambda row, col, value: '<a href="{}" target="_blank">{}</a>'.format(row.url, value))
    address = Col(
        'Address',
        cell=lambda row, col, value: '<a href="{href}" target="_blank">{text}</a>'.format(
            href=MAPS_PLACE_URL.format(address=value.replace(' ', '+')), text=value))
    neighborhood = Col('Neighborhood')
    rooms = Col('Rooms')
    cold_rent = Col('Cold Rent')
    warm_rent = Col('Warm Rent', allow_sort=True)
    warm_rent_notes = Col('Warm Rent Notes')
    opinion_id = Col('Opinion', cell=lambda row, col, value: render_template(
        'public/opinion.html', apartment_id=row.id, opinion_id=value,
        opinions=ApartmentTable.opinions))  # pylint: disable=undefined-variable
    created_at = DateCol('Created')
    updated_at = DateCol('Updated')

    def sort_url(self, col_key, reverse=False):
        """Sort the table by clicking its headers."""
        args = request.args.copy()
        if 'order_by' in args:
            args.pop('order_by')
        return url_for('public.apartments', order_by=col_key, **args)


@blueprint.route("/apartments/")
def apartments():
    """List all apartments."""
    # pylint: disable=no-member
    ApartmentTable.opinions = [(opinion.id, opinion.title) for opinion in Opinion.query.order_by(Opinion.title).all()]
    query = db.session.query(
        Apartment.title, Apartment.url, Apartment.address, Apartment.neighborhood, Apartment.rooms,
        Apartment.cold_rent, Apartment.warm_rent, Apartment.warm_rent_notes,
        Apartment.created_at, Apartment.updated_at, Apartment.id, Apartment.opinion_id)

    for pin in Pin.query.order_by(Pin.id).all():
        pin_address_field = 'pin_address_{}'.format(pin.id)

        duration_text_field = 'duration_text_{}'.format(pin.id)
        duration_value_field = 'duration_value_{}'.format(pin.id)
        ApartmentTable.add_column(duration_text_field, Col('Time to {}'.format(pin.name), allow_sort=True))

        def show_directions(row, col, value):
            """Show the Google Maps link with directions from the address to the pin."""
            pin_address = getattr(row, 'pin_address_' + col.field.split('_')[-1])
            return '<a href="{href}" target="_blank">{text}</a>'.format(
                href=MAPS_DIRECTIONS_URL.format(
                    origin=row.address.replace(' ', '+'),
                    destination=pin_address.replace(' ', '+')),
                text=value)

        distance_text_field = 'distance_text_{}'.format(pin.id)
        distance_value_field = 'distance_value_{}'.format(pin.id)
        ApartmentTable.add_column(distance_text_field,
                                  Col('Distance to {}'.format(pin.name), cell=show_directions))

        distance_alias = aliased(Distance)
        pin_alias = aliased(Pin)
        query = query.join(
            distance_alias, Apartment.id == distance_alias.apartment_id
        ).join(
            pin_alias, distance_alias.pin_id == pin_alias.id
        ).add_columns(
            distance_alias.duration_text.label(duration_text_field),
            distance_alias.duration_value.label(duration_value_field),
            distance_alias.distance_text.label(distance_text_field),
            distance_alias.distance_value.label(distance_value_field),
            pin_alias.address.label(pin_address_field)
        ).filter(distance_alias.pin_id == pin.id)
    query = query.filter(Apartment.active.is_(True))

    search_form = ApartmentSearchForm(request.args, csrf_enabled=False)
    if search_form.days.data:
        past_date = datetime.now() - timedelta(int(search_form.days.data))
        query = query.filter(Apartment.created_at >= past_date)

    search_form.opinion.choices = [(-1, '(all)'), (0, '(none)')] + ApartmentTable.opinions
    if search_form.opinion.data is not None:
        opinion_id = int(search_form.opinion.data)
        if opinion_id > -1:
            if opinion_id == 0:
                query = query.filter(Apartment.opinion_id.is_(None))
            else:
                query = query.filter(Apartment.opinion_id == opinion_id)

    order_by = search_form.order_by.data or 'warm_rent'

    if order_by.startswith('duration_text'):
        query = query.order_by('duration_value_{} {}'.format(order_by.split('_')[-1], 'asc'))
    elif order_by == 'warm_rent':
        query = query.order_by(Apartment.warm_rent.cast(Numeric), Apartment.cold_rent.cast(Numeric))

    table = ApartmentTable(query.all())
    return render_template("public/apartments.html", table=table, search_form=search_form, count=query.count())


@blueprint.route('/apartments/opinion/', methods=['POST'])
def apartments_opinion():
    """Set an opinion for an apartment."""
    apartment = Apartment.get_by_id(request.json.get('apartment_id', 0))
    """:type: Apartment"""
    opinion_id = int(request.json.get('opinion_id', 0))
    if opinion_id <= 0:
        opinion_id = None
    apartment.opinion_id = opinion_id
    db.session.add(apartment)
    db.session.commit()
    return 'Opinion updated'


@blueprint.route("/pins/")
def pins():
    """List all pins."""
    class PinTable(Table):

        """An HTML table for the pins."""

        name = Col('Name')
        address = Col('Address')

        def sort_url(self, col_id, reverse=False):
            """Sort the table by clicking its headers."""
            pass

    # pylint: disable=no-member
    items = Pin.query.all()
    table = PinTable(items, classes=['table-bordered', 'table-striped'])
    return render_template("public/pins.html", table=table)
