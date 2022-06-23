# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - .package
  - .config
{%- if podman.salt_compat %}
  - .service
{%- endif %}
