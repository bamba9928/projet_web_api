from django import template
register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})

# form_filters.py
from django import template
register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})

@register.filter(name='add_required')
def add_required(field):
    return field.as_widget(attrs={"required": ""})