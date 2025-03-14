from django import template
from django.utils.safestring import mark_safe
from markdown2 import markdown
from django.template.defaultfilters import linebreaksbr

register = template.Library()

@register.filter(name='markdown_linebreaks')
def markdown_linebreaks(value):
    # Convert Markdown to HTML
    html = markdown(value, extras=["break-on-newline"])
    # Mark the output as safe HTML
    return mark_safe(html)