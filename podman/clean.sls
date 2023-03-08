# -*- coding: utf-8 -*-
# vim: ft=sls

{%- set tplroot = tpldir.split('/')[0] %}
{%- from tplroot ~ "/map.jinja" import mapdata as podman with context %}

include:
  - .containers.clean
{%- if podman.salt_compat or podman.service_enable %}
  - .service.clean
{%- endif %}
  - .config.clean
  - .package.clean
