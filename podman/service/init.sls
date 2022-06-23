# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
{%- if podman.service_enable or podman.salt_compat %}
  - .running
{%- else %}
  - .clean
{%- endif %}
